from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

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
    PAGE_ANALYSIS_PROMPT_TEMPLATE,
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

    # ===== 多阶段循环常量 =====
    BATCH_SIZE = 4               # 保留兼容
    CONCURRENT_FETCH = 3         # 并发抓取数
    STEER_INTERVAL = 8           # 前沿引导间隔（页数）
    STEER_SAMPLE_SIZE = 30       # 前沿引导采样数
    INSIGHTS_SAMPLE_SIZE = 30    # 数据洞察采样数

    # 时间阈值（秒）
    FETCH_INTERVAL = 2.0         # 抓取间隔
    ANALYSIS_INTERVAL = 5.0      # LLM 页面分析间隔
    PUSH_INTERVAL = 2.0          # 前端推送间隔
    LOOP_SLEEP = 0.1             # 循环空闲等待

    # 数量阈值
    FETCH_THRESHOLD = 10         # URL 队列超过此数立即抓取
    ANALYSIS_THRESHOLD = 4       # 待分析页超过此数立即分析

    # 批处理大小
    FETCH_BATCH_SIZE = 4         # 每批抓取 URL 数
    ANALYSIS_BATCH_SIZE = 4      # 每批分析页面数

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
        self.fetcher = Fetcher(task_data_dir=task_data_dir, anti_crawl_config=anti_crawl_config,
                               seed_domain=urlparse(seed_url).netloc)
        set_fetcher(self.fetcher)

        self.results: list[dict[str, Any]] = []
        self.pages_crawled = 0
        self.content_hashes: set[str] = set()# 已抓取页面内容的哈希值集合，用于快速去重
        self._should_stop = False# 是否应该停止任务
        self.changes_detected = 0# 变更检测到的页面数量
        self._last_insights: list[dict[str, Any]] = []

        # 多阶段循环状态
        self.page_queue: list[PageData] = []        # 已抓取待 LLM 分析的页面
        self._analyzed_urls: set[str] = set()       # 已分析过的页面 URL，避免重复
        self._last_fetch: float = 0.0               # 上次抓取时间
        self._last_analysis: float = 0.0            # 上次分析时间
        self._last_push: float = 0.0                # 上次推送时间
        self._last_push_result_count: int = 0       # 上次推送时的结果数

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
        """多阶段循环：抓取 → LLM 分析 → 推送，时间/阈值双触发"""
        try:
            await self._report(progress_callback, "progress", message="开始抓取种子 URL...")

            # 种子 URL 抓取 → 加入 page_queue 等待 LLM 分析
            page = await self._fetch_page(self.seed_url, depth=0)
            if not page:
                return self.results
            self.page_queue.append(page)

            # 初始化各 Phase 时钟
            t = time.monotonic()
            self._last_fetch = 0.0
            self._last_analysis = 0.0
            self._last_push = t

            # ===== 主循环：3 阶段协作 =====
            while not self._should_stop:
                if self._is_done():
                    print(f"[完成] 队列清空: url={self.frontier.pending_count()}, "
                          f"page={len(self.page_queue)}, 结果={len(self.results)}")
                    break
                if self.pages_crawled >= self.max_pages and len(self.page_queue) == 0:
                    print(f"[完成] 达到最大页数: {self.pages_crawled}/{self.max_pages}")
                    break

                now = time.monotonic()

                # Phase 1: URL 队列 → 抓取页面
                if self._should_fetch(now):
                    await self._phase_fetch()
                    self._last_fetch = time.monotonic()

                # Phase 2: 页面 → LLM 分析（发现链接 + 提取数据）
                if self._should_analyze(now):
                    await self._phase_analyze_page(progress_callback)
                    self._last_analysis = time.monotonic()

                # Phase 3: 定期推送进度到前端
                if self._should_push(now):
                    await self._phase_push(progress_callback)
                    self._last_push = time.monotonic()

                await asyncio.sleep(self.LOOP_SLEEP)

            # 清空残余 page_queue
            while self.page_queue:
                await self._phase_analyze_page(progress_callback)

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

    # ─── 多阶段循环：退出条件 ─────────────────────────────────

    def _is_done(self) -> bool:
        """URL 队列和页面队列都为空时退出"""
        return not self.frontier.has_pending() and len(self.page_queue) == 0

    # ─── 多阶段循环：触发条件 ─────────────────────────────────

    def _should_fetch(self, now: float) -> bool:
        return (
            self.frontier.has_pending()
            and self.pages_crawled < self.max_pages
            and (
                now - self._last_fetch >= self.FETCH_INTERVAL
                or self.frontier.pending_count() > self.FETCH_THRESHOLD
            )
        )

    def _should_analyze(self, now: float) -> bool:
        return len(self.page_queue) > 0 and (
            now - self._last_analysis >= self.ANALYSIS_INTERVAL
            or len(self.page_queue) >= self.ANALYSIS_THRESHOLD
        )

    def _should_push(self, now: float) -> bool:
        return (
            len(self.results) > self._last_push_result_count
            and now - self._last_push >= self.PUSH_INTERVAL
        )

    # ─── 多阶段循环：Phase 方法 ──────────────────────────────

    async def _phase_fetch(self) -> None:
        """Phase 1: URL 队列出队 → 并发抓取 → 去重后加入 page_queue"""
        # 清理被熔断器封锁的域名 URL
        for domain in self.fetcher.blocked_domains:
            removed = self.frontier.remove_by_domain(domain)
            if removed > 0:
                print(f"[断路器] 已从队列移除 {removed} 个来自域名 {domain} 的 URL")

        batch = self._dequeue_batch(self.FETCH_BATCH_SIZE)
        if not batch:
            return
        pages = await self._fetch_concurrent(batch)
        for p in pages:
            ch = content_hash(p.text_content[:2000])
            if ch not in self.content_hashes:
                self.content_hashes.add(ch)
                self.page_queue.append(p)

    async def _phase_analyze_page(self, progress_callback: Callable | None) -> None:
        """Phase 2: 页面数据交给 LLM → 发现链接 + 提取数据"""
        batch = self.page_queue[:self.ANALYSIS_BATCH_SIZE]

        for page in batch:
            if page.url in self._analyzed_urls:
                continue

            # 从渲染后的 DOM 中提取同域名链接列表，供 LLM 决策
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page.html, "lxml")
            all_links: list[str] = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text(strip=True)[:40]
                if text and href and not href.startswith("#") and not href.startswith("javascript:"):
                    normalized = normalize_url(href, base_url=page.url)
                    if normalized and is_same_domain(normalized, self.seed_url):
                        all_links.append(f"{text} → {normalized}")

            # 去重 + 限制数量（避免 token 溢出）
            seen = set()
            unique_links: list[str] = []
            for link in all_links:
                if link not in seen:
                    seen.add(link)
                    unique_links.append(link)
            links_text = "\n".join(unique_links[:100])

            # 诊断
            text_preview = page.text_content[:200].replace("\n", " ").strip()
            print(f"[诊断] 页面: {page.title[:60]} | 文本={len(page.text_content)}字 | "
                  f"链接={len(unique_links)}个")

            prompt = PAGE_ANALYSIS_PROMPT_TEMPLATE.format(
                data_description=self.data_description,
                pages_crawled=self.pages_crawled,
                max_pages=self.max_pages,
                max_depth=self.max_depth,
                pending_count=self.frontier.pending_count(),
                page_url=page.url,
                page_title=page.title,
                page_text=page.text_content[:8000],
                page_links=links_text if links_text else "（未找到同域名链接）",
            )

            try:
                response = await self.llm.ainvoke(prompt)
                result = self._parse_llm_json(response)

                # LLM 返回的 URL → 规范化 + 域名/深度/去重检查后入队
                urls_found = result.get("selected_urls", [])
                urls_enqueued = 0
                for url in urls_found:
                    normalized = normalize_url(url, base_url=page.url)
                    if not normalized:
                        continue
                    if not is_same_domain(normalized, self.seed_url):
                        continue
                    if self.frontier.is_visited(normalized):
                        continue
                    depth = self._get_depth(normalized)
                    if depth > self.max_depth:
                        continue
                    if self.frontier.enqueue(normalized, depth):
                        urls_enqueued += 1

                items = result.get("extracted_items", [])
                print(f"[分析] {page.url} → {urls_enqueued}/{len(urls_found)} URL入队, "
                      f"{len(items)} 条数据, 队列: url={self.frontier.pending_count()}, "
                      f"page={len(self.page_queue)}, 已抓={self.pages_crawled}")

                # LLM 返回的数据 → 存入 results
                items = result.get("extracted_items", [])
                for item in items:
                    self.results.append({"source_url": page.url, "data": item})
                if items:
                    await self._report(
                        progress_callback, "data_extracted",
                        url=page.url, items=items,
                    )

            except Exception as e:
                print(f"[警告] LLM 页面分析失败 {page.url}: {e}")

            self._analyzed_urls.add(page.url)

        # 从 page_queue 中移除已分析页面
        self.page_queue = [p for p in self.page_queue if p.url not in self._analyzed_urls]

    async def _phase_push(self, progress_callback: Callable | None) -> None:
        """Phase 3: 定期推送进度到前端"""
        await self._report(
            progress_callback, "progress",
            message=(
                f"进度: {self.pages_crawled} 页已抓取, {len(self.results)} 条已提取, "
                f"队列: {self.frontier.pending_count()} 待抓取, "
                f"{len(self.page_queue)} 待分析"
            ),
        )
        self._last_push_result_count = len(self.results)

    def _parse_llm_json(self, response: Any) -> dict:
        """通用 JSON 解析：去 markdown 代码块 → parse"""
        text = response.content if hasattr(response, "content") else str(response)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)

    # 并发抓取多个页面，返回成功抓取的页面数据列表
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
    # 批量提取页面数据，优先使用批量提取提示，如果失败则回退到单页提取
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
    #提取页面中的链接，并进行过滤：去除蜜罐链、非页面链接、跨域链接、已访问链接，以及根据规则应该跳过的链接，返回 LinkInfo 列表
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
    #提取链接并进行过滤：去除蜜罐链、非页面链接、跨域链接、已访问链接，以及根据规则应该跳过的链接，返回 LinkInfo 列表
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
    #前沿引导：调用 LLM 判断哪些待抓取 URL 更有可能包含目标数据，优先抓取这些 URL，同时跳过明显质量较差或与目标无关的 URL，从而优化爬取效率和结果质量
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
                "pages_discovered": self.frontier.pending_count() + self.pages_crawled + len(self.page_queue),
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
