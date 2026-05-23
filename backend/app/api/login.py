"""登录 API：手动登录 / 自动化登录 / 凭据管理"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.crawler.credentials import CredentialManager
from app.crawler.login import LoginEngine

router = APIRouter(prefix="/api/login", tags=["login"])

_engine = LoginEngine()
_credentials = CredentialManager()


class ProfileCreate(BaseModel):
    name: str
    domain: str
    login_url: str
    form_selectors: dict[str, str] = {}
    username: str = ""
    password: str = ""  # 支持 ${ENV_VAR} 引用
    success_indicator: str = ""


# ─── 手动登录 ──────────────────────────────────────────

@router.post("/manual/start")
async def manual_login_start(profile_name: str = Query(...)) -> dict[str, Any]:
    """启动可见浏览器，等待用户手动登录"""
    result = await _engine.manual_login(profile_name)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/manual/complete")
async def manual_login_complete(profile_name: str = Query(...)) -> dict[str, Any]:
    """手动登录完成后保存 cookies"""
    result = await _engine.complete_manual_login(profile_name)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/manual/cancel")
async def manual_login_cancel(profile_name: str = Query(...)) -> dict[str, Any]:
    """取消手动登录"""
    result = await _engine.cancel_manual_login(profile_name)
    return result


# ─── 自动登录 ──────────────────────────────────────────

@router.post("/programmatic")
async def programmatic_login(profile_name: str = Query(...)) -> dict[str, Any]:
    """自动化登录（表单填充）"""
    result = await _engine.programmatic_login(profile_name)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    if result["status"] == "failed":
        raise HTTPException(status_code=422, detail=result["message"])
    return result


# ─── 登录配置管理 ──────────────────────────────────────

@router.get("/profiles")
async def list_profiles() -> list[dict[str, Any]]:
    """列出所有登录配置"""
    return _credentials.list_profiles()


@router.post("/profiles", status_code=201)
async def create_profile(body: ProfileCreate) -> dict[str, str]:
    """创建登录配置"""
    config = {
        "domain": body.domain,
        "login_url": body.login_url,
        "form_selectors": body.form_selectors,
        "username": body.username,
        "password": body.password,
        "success_indicator": body.success_indicator,
    }
    _credentials.save(body.name, config)
    return {"name": body.name, "status": "created"}


@router.delete("/profiles/{name}")
async def delete_profile(name: str) -> dict[str, str]:
    """删除登录配置"""
    ok = _credentials.delete(name)
    if not ok:
        raise HTTPException(status_code=404, detail="配置不存在")
    return {"name": name, "status": "deleted"}


# ─── 会话状态 ──────────────────────────────────────────

@router.get("/sessions")
async def list_active_sessions() -> list[str]:
    """列出当前活动的手动登录会话"""
    return _engine.list_active_sessions()
