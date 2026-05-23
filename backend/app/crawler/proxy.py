"""代理管理器：HTTP/SOCKS5 代理，支持 httpx 和 Playwright 双通道"""

from __future__ import annotations

import random
from urllib.parse import urlparse


class ProxyManager:
    """管理代理配置，为 httpx 和 Playwright 提供统一接口"""

    def __init__(self, proxy_url: str = "", rotation_list: str = ""):
        self._proxy_url = proxy_url
        self._rotation_list = [p.strip() for p in rotation_list.split(",") if p.strip()]
        self._per_domain: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._proxy_url or self._rotation_list)

    def _pick(self, domain: str = "") -> str:
        if domain and domain in self._per_domain:
            return self._per_domain[domain]
        if self._rotation_list:
            chosen = random.choice(self._rotation_list)
            if domain:
                self._per_domain[domain] = chosen
            return chosen
        return self._proxy_url

    def _parse_proxy(self, raw: str) -> dict:
        """解析代理 URL 为 httpx/Playwright 所需格式"""
        if not raw:
            return {}
        parsed = urlparse(raw)
        scheme = parsed.scheme or "http"
        if scheme in ("socks5", "socks5h"):
            return {"server": raw}
        return {"http://": raw, "https://": raw}

    def for_httpx(self, domain: str = "") -> dict | None:
        """返回 httpx 客户端可用的代理配置"""
        if not self.enabled:
            return None
        raw = self._pick(domain)
        if not raw:
            return None
        result = self._parse_proxy(raw)
        if "server" in result:
            return {"http://": result["server"], "https://": result["server"]}
        return result

    def for_playwright(self, domain: str = "") -> dict:
        """返回 Playwright browser context 可用的代理配置"""
        raw = self._pick(domain)
        return self._parse_proxy(raw)
