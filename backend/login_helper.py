"""登录助手：用 Playwright 打开浏览器，手动登录后自动保存 Cookie。

用法：
    python login_helper.py https://example.com/login

浏览器打开后手动完成登录，登录成功后按 Enter 键保存 Cookie 并退出。
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright


PROFILES_DIR = Path(__file__).parent / "data" / "profiles"


async def main(login_url: str):
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        # 先获取 UA（在导航之前，避免页面跳转导致上下文丢失）
        ua = await page.evaluate("navigator.userAgent")

        await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

        input("\n>>> 请在浏览器中完成登录，然后按 Enter 保存 Cookie...")

        # 获取域名
        domain = page.url.split("/")[2]
        safe_domain = domain.replace(":", "_").replace("/", "_")

        # 保存 Cookie（清理空 name 和字符串 expires）
        cookies = await context.cookies()
        import json
        for c in cookies:
            # 删除空 name
            if not c.get("name", "").strip():
                cookies.remove(c)
            # 修复字符串 expires → 数字
            elif isinstance(c.get("expires"), str):
                try:
                    from email.utils import parsedate_to_datetime
                    c["expires"] = parsedate_to_datetime(c["expires"]).timestamp()
                except Exception:
                    c["expires"] = -1
        session_file = PROFILES_DIR / f"{safe_domain}.session.json"
        session_file.write_text(json.dumps({
            "domain": domain,
            "saved_at": __import__("time").time(),
            "user_agent": ua,
            "cookies": cookies,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        # 同时保存 localStorage（页面可能已跳转，失败则跳过）
        local_storage = {}
        try:
            ls_raw = await page.evaluate("JSON.stringify(localStorage)")
            if ls_raw and ls_raw != "{}":
                local_storage = json.loads(ls_raw)
        except Exception:
            pass

        if local_storage:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            data["local_storage"] = local_storage
            session_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"✅ Cookie 已保存到: {session_file}")
        print(f"   Cookie 数量: {len(cookies)}, localStorage keys: {len(local_storage)}")

        await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python login_helper.py <登录页面URL>")
        print("示例: python login_helper.py https://example.com/login")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
