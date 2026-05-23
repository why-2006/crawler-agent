from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agent.prompts import EXTRACTION_PROMPT_TEMPLATE
from app.crawler.fetcher import Fetcher
from app.crawler.link_utils import is_page_url, is_same_domain, normalize_url


# ─── fetch_page 工具的 args_schema ───
class FetchPageInput(BaseModel):
    url: str = Field(description="要抓取的页面 URL")
    use_javascript: bool = Field(default=False, description="是否使用 JS 渲染")


# ─── extract_links 工具的 args_schema ───
class ExtractLinksInput(BaseModel):
    url: str = Field(description="页面的 URL")
    html: str = Field(default="", description="页面的 HTML 内容，为空则重新抓取")


# ─── extract_data 工具的 args_schema ───
class ExtractDataInput(BaseModel):
    page_url: str = Field(description="页面 URL")
    page_content: str = Field(description="页面文本内容")
    extraction_schema: str = Field(description="用户对目标数据的自然语言描述")


# ─── decide_next_urls 工具的 args_schema ───
class UnvisitedLink(BaseModel):
    url: str
    text: str = ""
    depth: int = 0


class CrawlConfig(BaseModel):
    depth_limit: int = 3
    max_pages: int = 50
    priority_hint: str = ""


class DecideNextInput(BaseModel):
    unvisited_links: list[UnvisitedLink] = Field(description="待抓取 URL 列表")
    crawl_config: CrawlConfig = Field(description="爬取约束配置")


# ─── 全局 fetcher 实例（每个任务可覆盖） ───
_fetcher: Fetcher | None = None


def set_fetcher(fetcher: Fetcher) -> None:
    global _fetcher
    _fetcher = fetcher


async def fetch_page_tool(url: str, use_javascript: bool = False) -> str:
    """抓取页面并返回清洗后的文本内容"""
    assert _fetcher is not None, "Fetcher not initialized"
    page_data = await _fetcher.fetch(url, use_javascript=use_javascript)
    result = {
        "url": page_data.url,
        "title": page_data.title,
        "text_content": page_data.text_content,
        "links_count": page_data.links_count,
        "content_type": page_data.content_type,
        "rendered": page_data.rendered,
    }
    return json.dumps(result, ensure_ascii=False)


async def extract_links_tool(url: str, html: str = "") -> str:
    """提取页面中的所有链接，区分站内/站外"""
    assert _fetcher is not None, "Fetcher not initialized"

    if not html:
        page_data = await _fetcher.fetch(url)
        html = page_data.html

    links = _fetcher.extract_links(
        type("PageData", (), {"html": html, "url": url})()
    )

    same_domain = []
    external = []
    for link_url, link_text in links:
        normalized = normalize_url(link_url, base_url=url)
        if not is_page_url(normalized):
            continue
        if is_same_domain(normalized, url):
            same_domain.append({"url": normalized, "text": link_text})
        else:
            external.append({"url": normalized, "text": link_text})

    result = {
        "same_domain_links": same_domain,
        "external_links": external,
    }
    return json.dumps(result, ensure_ascii=False)


async def extract_data_tool(
    page_url: str, page_content: str, extraction_schema: str
) -> str:
    """用 LLM 从页面内容中提取结构化数据 — 此工具由 Agent 调用后再由外层处理"""
    # 这个工具在 Agent 内部只是占位，真正的提取在 crawler_agent 中直接调用 LLM
    # 返回提示让 Agent 知道需要外部处理
    return json.dumps({
        "extracted_items": [],
        "confidence": 0.0,
        "note": "数据提取需要通过 LLM 直接处理，请将页面内容和提取需求传递给提取流程",
    }, ensure_ascii=False)


async def decide_next_urls_tool(
    unvisited_links: list[dict[str, Any]],
    crawl_config: dict[str, Any],
) -> str:
    """LLM 决策：从待抓取 URL 中选择下一步要抓取的链接"""
    # 简单实现：按深度排序返回前 N 个（实际的 LLM 决策在 crawler_agent 中）
    # 这个工具在 Agent 执行时会被调用，返回格式化数据供 LLM 分析
    links_data = [
        {"url": link.get("url", ""), "text": link.get("text", ""), "depth": link.get("depth", 0)}
        for link in unvisited_links
    ]
    return json.dumps({
        "total_unvisited": len(links_data),
        "links": links_data,
        "depth_limit": crawl_config.get("depth_limit", 3),
        "max_pages": crawl_config.get("max_pages", 50),
    }, ensure_ascii=False)


# ─── 创建 LangChain StructuredTool 实例 ───
fetch_page = StructuredTool.from_function(
    coroutine=fetch_page_tool,
    name="fetch_page",
    description="抓取指定 URL 的网页内容，返回标题和文本。对于 JS 渲染的页面设置 use_javascript=true。",
    args_schema=FetchPageInput,
)

extract_links = StructuredTool.from_function(
    coroutine=extract_links_tool,
    name="extract_links",
    description="从页面提取所有链接，区分站内链接和外部链接。传入 url 和可选的 html 内容。",
    args_schema=ExtractLinksInput,
)

extract_data = StructuredTool.from_function(
    coroutine=extract_data_tool,
    name="extract_data",
    description="根据页面内容和用户的数据描述，提取结构化 JSON 数据。",
    args_schema=ExtractDataInput,
)

decide_next_urls = StructuredTool.from_function(
    coroutine=decide_next_urls_tool,
    name="decide_next_urls",
    description="给定待抓取 URL 列表和爬取配置，返回按优先级排序的下一步 URL 列表。",
    args_schema=DecideNextInput,
)

ALL_TOOLS = [fetch_page, extract_links, extract_data, decide_next_urls]
