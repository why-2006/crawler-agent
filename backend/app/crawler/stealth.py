"""反反爬虫基础组件：UA 轮换、请求头标准化、延迟抖动、指数退避重试"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Callable, Coroutine


# ─── User-Agent 内置列表（2024-2025 主流浏览器） ─────────────────────

_BUILTIN_USER_AGENTS = [
    # Chrome 130 — Windows 10/11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    # Chrome 130 — macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    # Chrome 130 — Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Firefox 130 — Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    # Firefox 130 — macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:129.0) Gecko/20100101 Firefox/129.0",
    # Firefox 130 — Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
    # Edge 130 — Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
    # Edge 130 — macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    # Safari 17 — macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Chrome 125-127 (older but still common)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Chrome 130 — Windows 10 较旧版本
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Extra Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) Gecko/20100101 Firefox/127.0",
    # Opera
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/115.0.0.0",
]


def _build_default_ua_list() -> list[str]:
    return list(_BUILTIN_USER_AGENTS)


# ─── User-Agent 轮换器 ──────────────────────────────────────


class UserAgentRotator:
    """UA 轮换器：随机选取，同域名保持稳定"""

    def __init__(self, custom_list: str = ""):
        if custom_list.strip():
            self._pool = [s.strip() for s in custom_list.split(",") if s.strip()]
        else:
            self._pool = _build_default_ua_list()
        self._per_domain: dict[str, str] = {}
        self._default_ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )

    @property
    def pool_size(self) -> int:
        return len(self._pool)

    def next(self) -> str:
        """随机返回一个 UA"""
        if not self._pool:
            return self._default_ua
        return random.choice(self._pool)

    def for_domain(self, domain: str) -> str:
        """为指定域名返回 UA，同一 session 内保持一致"""
        if domain not in self._per_domain:
            self._per_domain[domain] = self.next()
        return self._per_domain[domain]


# ─── 请求头标准化 ──────────────────────────────────────────


class HeaderNormalizer:
    """为 HTTP 请求补充浏览器典型请求头"""

    @staticmethod
    def normalize(base_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if base_headers:
            headers.update(base_headers)

        defaults = {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        }
        for k, v in defaults.items():
            if k not in headers:
                headers[k] = v
        return headers


# ─── 延迟抖动 ──────────────────────────────────────────────


async def delay_with_jitter(base_seconds: float, jitter_ratio: float = 0.0) -> None:
    """在基础延迟上施加随机抖动"""
    if base_seconds <= 0:
        return
    if jitter_ratio <= 0:
        actual = base_seconds
    else:
        actual = base_seconds * (1.0 - jitter_ratio + 2.0 * jitter_ratio * random.random())
    await asyncio.sleep(max(0.0, actual))


# ─── 指数退避重试 ──────────────────────────────────────────


RetryableCheck = Callable[[Exception | int | None], bool]
CoroFactory = Callable[[], Coroutine[Any, Any, Any]]


async def retry_with_backoff(
    coro_factory: CoroFactory,
    is_retryable: RetryableCheck | None = None,
    max_attempts: int = 3,
    backoff_initial: float = 1.0,
    backoff_max: float = 30.0,
) -> Any:
    """指数退避重试：遇到可重试错误时自动重试"""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= max_attempts:
                raise
            retryable = is_retryable(exc) if is_retryable else True
            if not retryable:
                raise
            wait = min(backoff_initial * (2 ** attempt) + random.uniform(0, 1), backoff_max)
            await asyncio.sleep(wait)

    raise last_exc or RuntimeError("retry_with_backoff exhausted")
