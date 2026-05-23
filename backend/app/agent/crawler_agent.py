from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.agent.prompts import (
    CRAWLER_SYSTEM_PROMPT,
    BATCH_EXTRACTION_PROMPT_TEMPLATE,
    CHANGE_SUMMARY_PROMPT,
    DECISION_PROMPT_TEMPLATE,
    EXTRACTION_PROMPT_TEMPLATE,
    INSIGHTS_PROMPT_TEMPLATE,
    STEER_PROMPT_TEMPLATE,
)
from app.agent.tools import ALL_TOOLS, set_fetcher
from app.config import settings
from app.crawler.fetcher import Fetcher
from app.crawler.frontier import Frontier
from app.crawler.link_utils import (
    content_hash,
    is_honeypot_link,
    is_page_url,
    is_same_domain,
    normalize_url,
    should_skip_url,
)
from app.models.schemas import LinkInfo, PageData, now_iso
from app.storage.database import (
    insert_content_change,
    upsert_url_tracking,
)


class CrawlerAgent:
    """通用爬虫 Agent：编排抓取、链接发现、数据提取、LLM 决策的完整循环"""

    BATCH_SIZE = 4
    CONCURRENT_FETCH = 3
    STEER_INTERVAL = 8
    STEER_SAMPLE_SIZE = 30
    INSIGHTS_SAMPLE_SIZE = 30

    def __init__(
        self,
        seed_url: str,
        data_description: str,
        max_depth: int = 3,
        max_pages: int = 50,
        use_javascript: bool = False,
        task_data_dir: Path | None = None,
        recurring_interval_minutes: int = 0,
        task_id: str = "",
        anti_crawl_config=None,
    ):
        self.seed_url = seed_url
        self.data_description = data_description
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.use_javascript = use_javascript
        self.recurring_interval_minutes = recurring_interval_minutes
        self.task_id = task_id

        self.frontier = Frontier()
        self.fetcher = Fetcher(task_data_dir=task_data_dir, anti_crawl_config=anti_crawl_config)
        set_fetcher(self.fetcher)

        self.results: list[dict[str, Any]] = []
        self.pages_crawled = 0
        self.content_hashes: set[str] = set()
        self._should_stop = False
        self._last_steer_at = 0
        self.changes_detected = 0
        self._last_insights: list[dict[str, Any]] = []

        self.llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            openai_api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

        # 专用 LLM，开启 JSON 模式，防止输出截断
        self.extract_llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=0,
            max_tokens=settings.llm_max_tokens,
            openai_api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", CRAWLER_SYSTEM_PROMPT),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        agent = create_openai_tools_agent(self.llm, ALL_TOOLS, prompt)
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=ALL_TOOLS,
            verbose=False,
            max_iterations=20,
            handle_parsing_errors=True,
        )

    async def run(
        self,
        progress_callback: Callable | None = None,
    ) -> list[dict[str, Any]]:
        """执行爬取任务：并发抓取 + 批量 LLM 提取 + 数据洞察 + 变更检测"""
        try:
            await self._report(progress_callback, "progress", message="开始抓取种子 URL...")

            page = await self._fetch_page(self.seed_url, depth=0)
            if not page:
                return self.results
            new_links = self._discover_links(page, depth=0)
            self.frontier.enqueue_batch([(l.url, l.depth) for l in new_links])

            await self._extract_and_store(page, progress_callback)

            page_buffer: list[PageData] = []

            while self.frontier.has_pending() and self.pages_crawled < self.max_pages:
                if self._should_stop:
                    await self._report(progress_callback, "progress", message="任务被用户停止")
                    break

                batch_urls = self._dequeue_batch(self.BATCH_SIZE)
                if not batch_urls:
                    break

                pages = await self._fetch_concurrent(batch_urls)
                if not pages:
                    continue

                unique_pages = []
                for p in pages:
                    ch = content_hash(p.text_content[:2000])
                    if ch not in self.content_hashes:
                        self.content_hashes.add(ch)
                        unique_pages.append(p)
                    if self.pages_crawled < self.max_pages * 0.7:
                        links = self._discover_links(p, depth=p.depth)
                        for link in links:
                            if link.depth <= self.max_depth:
                                self.frontier.enqueue(link.url, link.depth)

                page_buffer.extend(unique_pages)

                if len(page_buffer) >= self.BATCH_SIZE:
                    await self._extract_batch(page_buffer, progress_callback)
                    page_buffer.clear()

                if self.pages_crawled - self._last_steer_at >= self.STEER_INTERVAL:
                    await self._steer_frontier()
                    self._last_steer_at = self.pages_crawled

            if page_buffer:
                await self._extract_batch(page_buffer, progress_callback)

            # 数据洞察
            if len(self.results) >= 3:
                insights = await self._generate_insights()
                if insights:
                    await self._report(progress_callback, "insights", insights=insights)

            await self._report(
                progress_callback, "completed",
                message=f"爬取完成，共 {self.pages_crawled} 页，{len(self.results)} 条记录",
            )
        except Exception as e:
            await self._report(progress_callback, "error", message=str(e))
        finally:
            await self.fetcher.close_browser()

        return self.results

    def stop(self) -> None:
        self._should_stop = True

    def _dequeue_batch(self, n: int) -> list[tuple[str, int]]:
        result = []
        for _ in range(min(n, self.frontier.pending_count())):
            item = self.frontier.dequeue()
            if item:
                result.append(item)
        return result

    async def _fetch_concurrent(self, urls: list[tuple[str, int]]) -> list[PageData]:
        async def fetch_one(url: str, depth: int) -> PageData | None:
            try:
                page = await self.fetcher.fetch(url, use_javascript=self.use_javascript)
                page.depth = depth
                self.pages_crawled += 1
                await self._detect_content_change(page)
                return page
            except Exception as e:
                print(f"[错误] 抓取失败 {url}: {e}")
                return None

        tasks = [fetch_one(url, depth) for url, depth in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, PageData)]

    async def _extract_batch(
        self, pages: list[PageData], progress_callback: Callable | None
    ) -> None:
        if not pages:
            return
        if len(pages) == 1:
            return await self._extract_and_store(pages[0], progress_callback)

        page_blocks = []
        for i, page in enumerate(pages, 1):
            page_blocks.append(
                f"--- 页面 {i} ---\n"
                f"URL: {page.url}\n"
                f"标题: {page.title}\n"
                f"内容: {page.text_content[:1500]}\n"
            )
        page_contents = "\n".join(page_blocks)

        prompt = BATCH_EXTRACTION_PROMPT_TEMPLATE.format(
            data_description=self.data_description,
            page_contents=page_contents,
        )
        try:
            items = await self._invoke_extract_llm(prompt)
            if items:
                for item in items:
                    source = item.pop("source_url", pages[0].url)
                    self.results.append({"source_url": source, "data": item})
                await self._report(
                    progress_callback, "data_extracted",
                    url=f"批量{pages[0].url}", items=items,
                )
        except Exception as e:
            print(f"[警告] 批量提取失败: {e}，回退到单页提取")
            for page in pages:
                await self._extract_and_store(page, progress_callback)

    async def _fetch_page(self, url: str, depth: int) -> PageData | None:
        try:
            page = await self.fetcher.fetch(url, use_javascript=self.use_javascript)
            page.depth = depth
            self.pages_crawled += 1
            await self._detect_content_change(page)
            return page
        except Exception as e:
            print(f"[错误] 抓取失败 {url}: {e}")
            return None

    def _discover_links(self, page: PageData, depth: int) -> list[LinkInfo]:
        links = self.fetcher.extract_links(page)

        # 蜜罐链检测
        honeypot_urls: set[str] = set()
        if settings.honeypot_detection_enabled:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page.html, "lxml")
            for a in soup.find_all("a", href=True):
                is_hp, _reason = is_honeypot_link(a)
                if is_hp:
                    honeypot_urls.add(normalize_url(a["href"].strip(), base_url=page.url))

        result = []
        for url, text in links:
            normalized = normalize_url(url, base_url=page.url)
            if normalized in honeypot_urls:
                continue
            if not is_page_url(normalized) or not is_same_domain(normalized, self.seed_url):
                continue
            if self.frontier.is_visited(normalized):
                continue
            skip, reason = should_skip_url(normalized)
            if skip:
                continue
            result.append(LinkInfo(url=normalized, text=text, depth=depth + 1))
        return result

    async def _extract_and_store(
        self, page: PageData, progress_callback: Callable | None
    ) -> None:
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            data_description=self.data_description,
            page_url=page.url,
            page_title=page.title,
            page_content=page.text_content[:3000],
        )
        try:
            items = await self._invoke_extract_llm(prompt)
            if items:
                for item in items:
                    self.results.append({"source_url": page.url, "data": item})
                await self._report(
                    progress_callback, "data_extracted",
                    url=page.url, items=items,
                )
        except Exception as e:
            print(f"[警告] 数据提取失败 {page.url}: {e}")

    async def _decide_next_urls(self) -> list[str]:
        pending = self.frontier.get_pending_urls()
        if not pending:
            return []
        if len(pending) <= 3:
            urls = [url for url, _ in pending]
            self.frontier.remove_urls(set(urls))
            return urls

        links_text = "\n".join(
            f"- [深度{d}] {url}"
            for url, d in pending[:50]
        )
        prompt = DECISION_PROMPT_TEMPLATE.format(
            data_description=self.data_description,
            pages_crawled=self.pages_crawled,
            max_pages=self.max_pages,
            max_depth=self.max_depth,
            results_count=len(self.results),
            unvisited_links=links_text,
        )
        try:
            response = await self.llm.ainvoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            decision = json.loads(text)
            next_urls = decision.get("next_urls", [])
            skip_urls = set(decision.get("skip_urls", []))
            if skip_urls:
                self.frontier.remove_urls(skip_urls)
            self.frontier.remove_urls(set(next_urls))
            return next_urls
        except Exception:
            pending.sort(key=lambda x: x[1])
            urls = [url for url, _ in pending[:3]]
            self.frontier.remove_urls(set(urls))
            return urls

    async def _steer_frontier(self) -> None:
        pending = self.frontier.get_pending_urls()
        if len(pending) <= self.STEER_SAMPLE_SIZE // 2:
            return

        sample = pending[:self.STEER_SAMPLE_SIZE]
        sample_lines = "\n".join(f"- [深度{d}] {url}" for url, d in sample)

        prompt = STEER_PROMPT_TEMPLATE.format(
            data_description=self.data_description,
            pages_crawled=self.pages_crawled,
            max_pages=self.max_pages,
            pending_count=self.frontier.pending_count(),
            sample_urls=sample_lines,
        )
        try:
            response = await self.llm.ainvoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            decision = json.loads(text)
            skip_urls = set(decision.get("skip_urls", []))
            if skip_urls:
                self.frontier.remove_urls(skip_urls)
        except Exception:
            pass

    # ─── 内容变更检测 ─────────────────────────────────────────

    async def _detect_content_change(self, page: PageData) -> None:
        if self.recurring_interval_minutes <= 0:
            return
        if not self.task_id:
            return
        try:
            ch = content_hash(page.text_content[:2000])
            changed, old_hash = await upsert_url_tracking(
                url=page.url,
                seed_url=self.seed_url,
                content_hash=ch,
                task_id=self.task_id,
                now=now_iso(),
            )
            if changed:
                self.changes_detected += 1
                summary = await self._generate_change_summary(page, old_hash)
                await insert_content_change(
                    task_id=self.task_id,
                    url=page.url,
                    old_content_hash=old_hash,
                    new_content_hash=ch,
                    change_summary=summary,
                    detected_at=now_iso(),
                )
        except Exception:
            pass

    async def _generate_change_summary(self, page: PageData, old_hash: str | None) -> str | None:
        if old_hash is None:
            return "首次发现此页面"
        try:
            prompt = CHANGE_SUMMARY_PROMPT.format(
                old_content=page.text_content[:1000],
                new_content=page.text_content[:1000],
            )
            response = await self.llm.ainvoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            return text.strip()
        except Exception:
            return f"页面内容已更新（hash: {old_hash[:8]}...）"

    # ─── 数据洞察生成 ─────────────────────────────────────────

    async def _generate_insights(self) -> list[dict[str, Any]]:
        sample = self.results[:self.INSIGHTS_SAMPLE_SIZE]
        sample_json = json.dumps(sample, ensure_ascii=False, indent=2)

        prompt = INSIGHTS_PROMPT_TEMPLATE.format(
            data_description=self.data_description,
            record_count=len(self.results),
            sample_size=len(sample),
            sample_data=sample_json,
        )
        try:
            response = await self.llm.ainvoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            insights = json.loads(text)
            if isinstance(insights, list):
                self._last_insights = insights
                return insights
        except Exception as e:
            print(f"[警告] 洞察生成失败: {e}")
        return []

    def _get_depth(self, url: str) -> int:
        from urllib.parse import urlparse
        seed_path = urlparse(self.seed_url).path.strip("/")
        url_path = urlparse(url).path.strip("/")
        if not seed_path:
            return len(url_path.split("/")) if url_path else 1
        seed_segments = len(seed_path.split("/"))
        url_segments = len(url_path.split("/"))
        return max(1, url_segments - seed_segments + 1)

    async def _invoke_extract_llm(self, prompt: str) -> list[dict]:
        """调用 extract_llm 并解析 JSON 对象中的 items 数组"""
        response = await self.extract_llm.ainvoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        data = json.loads(text)
        if isinstance(data, dict):
            return data.get("items", [])
        if isinstance(data, list):
            return data
        return []

    async def _report(
        self,
        callback: Callable | None,
        event_type: str,
        url: str | None = None,
        items: list[dict] | None = None,
        message: str | None = None,
        insights: list[dict] | None = None,
        change_summary: str | None = None,
        change_count: int = 0,
        detected_at: str | None = None,
    ) -> None:
        if callback:
            data: dict[str, Any] = {
                "type": event_type,
                "pages_crawled": self.pages_crawled,
                "pages_discovered": self.frontier.pending_count() + self.pages_crawled,
            }
            if url:
                data["url"] = url
            if items:
                data["items"] = items
            if message:
                data["message"] = message
            if insights:
                data["insights"] = insights
            if change_summary:
                data["change_summary"] = change_summary
                data["change_count"] = change_count
            if detected_at:
                data["detected_at"] = detected_at
            await callback(data)
