"""Cookie / Session 持久化：按域名存储浏览器状态，支持 headless 复用"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.config import settings


class SessionStore:
    """按域名存储 cookies 和 localStorage，用于跨任务复用登录态"""

    def __init__(self, base_dir: str = ""):
        self._base = Path(base_dir or settings.profiles_dir)

    def _domain_file(self, domain: str) -> Path:
        safe = domain.replace(":", "_").replace("/", "_")
        return self._base / f"{safe}.session.json"

    def save(self, domain: str, cookies: list[dict], local_storage: dict[str, str] | None = None) -> None:
        self._base.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "domain": domain,
            "saved_at": time.time(),
            "cookies": cookies,
        }
        if local_storage:
            data["local_storage"] = local_storage
        self._domain_file(domain).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, domain: str) -> dict | None:
        path = self._domain_file(domain)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def load_cookies(self, domain: str) -> list[dict]:
        data = self.load(domain)
        if data and "cookies" in data:
            return data["cookies"]
        return []

    def load_storage_state(self, domain: str) -> dict | None:
        """返回 Playwright storage_state 格式的数据"""
        data = self.load(domain)
        if not data:
            return None
        state: dict[str, Any] = {"cookies": data.get("cookies", [])}
        if "local_storage" in data:
            origins: list[dict] = []
            for key, value in data["local_storage"].items():
                origins.append({"origin": f"https://{domain}", "localStorage": [{"name": key, "value": value}]})
            if origins:
                state["origins"] = origins
        return state

    def delete(self, domain: str) -> None:
        path = self._domain_file(domain)
        if path.exists():
            path.unlink()

    @staticmethod
    def extract_cookies_from_httpx(response) -> list[dict]:
        """从 httpx Response 提取 Set-Cookie 为标准化格式"""
        cookies: list[dict] = []
        for raw in response.headers.get_list("set-cookie"):
            cookie: dict[str, Any] = {}
            for part in raw.split(";"):
                part = part.strip()
                if "=" in part and "name" not in cookie:
                    key, val = part.split("=", 1)
                    cookie["name"] = key
                    cookie["value"] = val
                elif "=" in part:
                    k, v = part.split("=", 1)
                    k = k.lower()
                    if k == "path":
                        cookie["path"] = v
                    elif k == "domain":
                        cookie["domain"] = v
                    elif k == "expires":
                        cookie["expires"] = v
                    elif k == "max-age":
                        cookie["maxAge"] = int(v) if v.isdigit() else 0
                elif part.lower() in ("httponly",):
                    cookie["httpOnly"] = True
                elif part.lower() in ("secure",):
                    cookie["secure"] = True
                elif part.lower() in ("samesite",):
                    pass  # handled as key=value below
            if "name" in cookie:
                cookies.append(cookie)
        return cookies
