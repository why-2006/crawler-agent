"""登录引擎：手动登录 + 自动化登录，完成后保存 cookies 到 SessionStore"""

from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path

from app.config import settings
from app.crawler.credentials import CredentialManager
from app.crawler.session import SessionStore


_playwright_available = True
try:
    from playwright.async_api import async_playwright
except ImportError:
    _playwright_available = False

_stealth_available = True
try:
    from playwright_stealth import stealth_async
except ImportError:
    _stealth_available = False


class LoginEngine:
    """两种登录方式：手动（可见浏览器）和自动化（表单填充 + 验证码识别）"""

    def __init__(self):
        self._credentials = CredentialManager()
        self._session_store = SessionStore()
        self._active_browsers: dict[str, dict] = {}  # profile_name → {playwright, browser, page}

    async def manual_login(self, profile_name: str) -> dict:
        """
        启动可见浏览器，用户手动完成登录后保存 cookies。
        返回 {"status": "waiting" | "completed", "message": str}
        """
        if not _playwright_available:
            return {"status": "error", "message": "playwright 未安装"}

        config = self._credentials.load(profile_name)
        if not config:
            return {"status": "error", "message": f"登录配置 {profile_name} 不存在"}

        domain = config.get("domain", "")
        login_url = config.get("login_url", "")
        if not login_url:
            return {"status": "error", "message": "登录配置缺少 login_url"}

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        if settings.playwright_stealth_enabled and _stealth_available:
            await stealth_async(page)

        await page.goto(login_url, wait_until="networkidle", timeout=60000)

        self._active_browsers[profile_name] = {
            "playwright": pw,
            "browser": browser,
            "context": context,
            "page": page,
            "domain": domain,
        }

        return {"status": "waiting", "message": f"浏览器已打开 {login_url}，请手动完成登录"}

    async def complete_manual_login(self, profile_name: str) -> dict:
        """手动登录完成后调用：保存 cookies 并关闭浏览器"""
        session = self._active_browsers.pop(profile_name, None)
        if not session:
            return {"status": "error", "message": f"没有正在进行的登录会话: {profile_name}"}

        domain = session["domain"]
        context = session["context"]
        page = session["page"]

        try:
            cookies = await context.cookies()
            local_storage = {}
            try:
                ls_raw = await page.evaluate("JSON.stringify(localStorage)")
                if ls_raw:
                    local_storage = json.loads(ls_raw)
            except Exception:
                pass

            self._session_store.save(domain, cookies, local_storage)
        finally:
            await context.close()
            await session["browser"].close()
            await session["playwright"].stop()

        return {"status": "completed", "message": f"已保存 {len(cookies)} 个 cookies", "cookies_count": len(cookies)}

    async def cancel_manual_login(self, profile_name: str) -> dict:
        """取消手动登录"""
        session = self._active_browsers.pop(profile_name, None)
        if not session:
            return {"status": "error", "message": f"没有正在进行的登录会话: {profile_name}"}

        await session["context"].close()
        await session["browser"].close()
        await session["playwright"].stop()
        return {"status": "cancelled", "message": "登录已取消"}

    async def programmatic_login(self, profile_name: str) -> dict:
        """
        自动化登录：填写表单 → 提交 → 检测成功 → 保存 cookies。
        返回 {"status": "completed" | "failed", "message": str}
        """
        if not _playwright_available:
            return {"status": "error", "message": "playwright 未安装"}

        config = self._credentials.load(profile_name)
        if not config:
            return {"status": "error", "message": f"登录配置 {profile_name} 不存在"}

        domain = config.get("domain", "")
        login_url = config.get("login_url", "")
        selectors = config.get("form_selectors", {})
        username = config.get("username", "")
        password = config.get("password", "")
        success_indicator = config.get("success_indicator", "")

        if not all([login_url, selectors, username, password]):
            return {"status": "error", "message": "登录配置不完整：需要 login_url, form_selectors, username, password"}

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        if settings.playwright_stealth_enabled and _stealth_available:
            await stealth_async(page)

        try:
            await page.goto(login_url, wait_until="networkidle", timeout=60000)

            user_sel = selectors.get("username")
            pass_sel = selectors.get("password")
            submit_sel = selectors.get("submit")

            if user_sel:
                await page.fill(user_sel, "")  # 先清空
                for ch in username:
                    await page.type(user_sel, ch, delay=random.randint(40, 120))
                    await asyncio.sleep(0.05)

            if pass_sel:
                await page.fill(pass_sel, "")
                for ch in password:
                    await page.type(pass_sel, ch, delay=random.randint(40, 120))
                    await asyncio.sleep(0.05)

            # 检测验证码
            has_captcha, captcha_type, info = await self._detect_captcha_on_page(page)
            if has_captcha:
                return {"status": "failed", "message": f"检测到 {captcha_type} 验证码，请使用手动登录"}

            if submit_sel:
                await page.click(submit_sel)
                await page.wait_for_load_state("networkidle", timeout=30000)

            # 等待并检测登录成功
            await asyncio.sleep(2)
            if success_indicator:
                try:
                    await page.wait_for_selector(success_indicator, timeout=10000)
                except Exception:
                    return {"status": "failed", "message": f"未检测到登录成功标志: {success_indicator}"}

            cookies = await context.cookies()
            local_storage = {}
            try:
                ls_raw = await page.evaluate("JSON.stringify(localStorage)")
                if ls_raw:
                    local_storage = json.loads(ls_raw)
            except Exception:
                pass

            self._session_store.save(domain, cookies, local_storage)
            return {"status": "completed", "message": f"登录成功，已保存 {len(cookies)} 个 cookies", "cookies_count": len(cookies)}

        except Exception as e:
            return {"status": "failed", "message": str(e)}
        finally:
            await context.close()
            await browser.close()
            await pw.stop()

    @staticmethod
    async def _detect_captcha_on_page(page) -> tuple[bool, str, dict]:
        """检测页面上是否有验证码"""
        html = await page.content()
        from app.crawler.captcha import needs_captcha_solve
        return needs_captcha_solve(html)

    def list_active_sessions(self) -> list[str]:
        return list(self._active_browsers.keys())
