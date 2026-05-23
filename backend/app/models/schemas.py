from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    stopped = "stopped"


class AntiCrawlConfig(BaseModel):
    """单任务级反反爬虫配置，覆盖全局 settings"""
    ua_rotation: bool = False
    header_normalization: bool = True
    jitter_ratio: float = 0.3
    retry_enabled: bool = True
    retry_max_attempts: int = 3
    playwright_stealth: bool = False
    proxy_url: str = ""
    proxy_rotation: bool = False
    session_persistence: bool = False
    login_profile: str = ""
    honeypot_detection: bool = True


class TaskCreate(BaseModel):
    seed_url: str
    data_description: str
    max_depth: int = Field(default=3, ge=1, le=20)
    max_pages: int = Field(default=50, ge=1, le=500)
    use_javascript: bool = False
    recurring_interval_minutes: int = Field(default=0, ge=0, le=10080)  # 0=一次性, >0=定时监控（最大7天）
    anti_crawl: AntiCrawlConfig | None = None


class TaskSummary(BaseModel):
    task_id: str
    seed_url: str
    status: TaskStatus
    pages_crawled: int
    pages_discovered: int
    result_count: int
    created_at: str
    recurring_interval_minutes: int = 0
    task_group_id: str | None = None


class ExtractedRecord(BaseModel):
    source_url: str
    data: dict[str, Any]


class ContentChange(BaseModel):
    url: str
    change_summary: str | None = None
    old_hash: str | None = None
    new_hash: str
    detected_at: str


class DataInsight(BaseModel):
    insight_type: str   # distribution / trend / comparison / anomaly
    chart_type: str     # bar / line / pie / scatter / heatmap
    title: str
    data: dict[str, Any]  # ECharts 格式 {"categories": [...], "series": [...]}
    description: str


class UrlTrackingInfo(BaseModel):
    url: str
    last_hash: str
    last_seen_at: str
    first_seen_at: str
    change_count: int
    last_changed_at: str | None = None


class TaskDetail(BaseModel):
    task_id: str
    seed_url: str
    data_description: str
    max_depth: int
    max_pages: int
    use_javascript: bool
    status: TaskStatus
    pages_crawled: int
    pages_discovered: int
    result_count: int
    results: list[ExtractedRecord] = []
    insights: list[DataInsight] = []
    changes_detected: int = 0
    recurring_interval_minutes: int = 0
    task_group_id: str | None = None
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class PageData(BaseModel):
    url: str
    title: str
    text_content: str
    html: str = ""
    links_count: int = 0
    content_type: str = ""
    rendered: bool = False
    depth: int = 0


class LinkInfo(BaseModel):
    url: str
    text: str = ""
    depth: int = 0


class LinksResult(BaseModel):
    same_domain_links: list[LinkInfo] = []
    external_links: list[LinkInfo] = []


class FetchResult(BaseModel):
    url: str
    title: str
    text_content: str
    links_count: int
    content_type: str
    rendered: bool


class ExtractResult(BaseModel):
    extracted_items: list[dict[str, Any]] = []
    confidence: float = 0.0


class DecideResult(BaseModel):
    next_urls: list[str] = []
    skip_urls: list[str] = []


class ProgressEvent(BaseModel):
    type: str  # progress | page_crawled | data_extracted | completed | error | insights | content_changed
    pages_crawled: int = 0
    pages_discovered: int = 0
    url: str | None = None
    items: list[dict[str, Any]] | None = None
    insights: list[dict[str, Any]] | None = None
    message: str | None = None
    change_summary: str | None = None
    change_count: int = 0
    detected_at: str | None = None


def new_task_id() -> str:
    return uuid.uuid4().hex[:16]

#返回当前 UTC 时间的 ISO 格式字符串，用于记录任务的创建时间、开始时间和完成时间等时间戳信息
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
