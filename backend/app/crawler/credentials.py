"""登录凭据配置管理：存储和解析各网站的登录配置，密码从环境变量引用"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from app.config import settings


_ENV_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class CredentialManager:
    """管理 data/profiles/*.profile.json 登录配置"""

    def __init__(self, base_dir: str = ""):
        self._base = Path(base_dir or settings.profiles_dir)

    def _ensure_dir(self) -> None:
        self._base.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> list[dict]:
        self._ensure_dir()
        profiles = []
        for f in self._base.glob("*.profile.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                profiles.append({
                    "name": data.get("name", f.stem.replace(".profile", "")),
                    "domain": data.get("domain", ""),
                    "login_url": data.get("login_url", ""),
                })
            except (json.JSONDecodeError, OSError):
                pass
        return profiles

    def load(self, name: str) -> dict | None:
        path = self._base / f"{name}.profile.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data = self._resolve_env_vars(data)
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def save(self, name: str, config: dict) -> None:
        self._ensure_dir()
        config["name"] = name
        path = self._base / f"{name}.profile.json"
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete(self, name: str) -> bool:
        path = self._base / f"{name}.profile.json"
        if path.exists():
            path.unlink()
            return True
        return False

    @staticmethod
    def _resolve_env_vars(data: dict) -> dict:
        """将 ${VAR} 引用替换为环境变量值"""
        resolved = {}
        for key, value in data.items():
            if isinstance(value, str):
                def _replace(m):
                    return os.environ.get(m.group(1), "")
                resolved[key] = _ENV_REF_RE.sub(_replace, value)
            elif isinstance(value, dict):
                resolved[key] = CredentialManager._resolve_env_vars(value)
            else:
                resolved[key] = value
        return resolved
