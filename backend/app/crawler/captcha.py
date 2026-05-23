"""
CAPTCHA 识别模块 — 检测页面中的验证码并调用第三方服务识别

支持的 CAPTCHA 类型:
- reCAPTCHA v2/v3 (Google)
- hCaptcha
- Cloudflare Turnstile
- 图片验证码 (image CAPTCHA)

支持的识别服务:
- 2captcha (https://2captcha.com)
"""

from __future__ import annotations

import base64
import re
import time
from enum import Enum
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


class CaptchaType(Enum):
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    CLOUDFLARE = "cloudflare_turnstile"
    IMAGE = "image_captcha"
    UNKNOWN = "unknown"


class CaptchaDetector:
    """检测页面是否包含验证码，识别验证码类型"""

    RECAPTCHA_PATTERNS = [
        r"google\.com/recaptcha",
        r"grecaptcha",
        r"g-recaptcha",
        r"data-sitekey",
    ]
    HCAPTCHA_PATTERNS = [
        r"hcaptcha\.com",
        r"h-captcha",
        r"data-hcaptcha",
    ]
    CLOUDFLARE_PATTERNS = [
        r"challenges\.cloudflare\.com",
        r"turnstile",
        r"cf-challenge",
        r"cf-captcha",
        r"Checking your browser",
        r"Just a moment",
    ]
    IMAGE_CAPTCHA_PATTERNS = [
        r'<img[^>]+(?:captcha|verify|code)',
        r'<input[^>]+captcha',
        r'captcha\.php',
    ]

    @classmethod
    def detect(cls, html: str, url: str = "") -> tuple[bool, CaptchaType, dict]:
        """
        检测页面中的验证码
        返回: (是否包含验证码, 验证码类型, 额外信息如 sitekey)
        """
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text().lower()
        html_lower = html.lower()

        # 检测 Cloudflare
        for pattern in cls.CLOUDFLARE_PATTERNS:
            if re.search(pattern, html_lower) or re.search(pattern, text, re.IGNORECASE):
                return True, CaptchaType.CLOUDFLARE, {}

        # 检测 reCAPTCHA
        for pattern in cls.RECAPTCHA_PATTERNS:
            if re.search(pattern, html_lower):
                info = cls._extract_recaptcha_info(soup, html_lower)
                return True, info.get("captcha_type", CaptchaType.RECAPTCHA_V2), info

        # 检测 hCaptcha
        for pattern in cls.HCAPTCHA_PATTERNS:
            if re.search(pattern, html_lower):
                info = {"sitekey": cls._extract_sitekey(soup, "data-hcaptcha")}
                return True, CaptchaType.HCAPTCHA, info

        # 检测图片验证码
        for pattern in cls.IMAGE_CAPTCHA_PATTERNS:
            if re.search(pattern, html_lower):
                img_info = cls._extract_image_captcha(soup, url)
                return True, CaptchaType.IMAGE, img_info

        return False, CaptchaType.UNKNOWN, {}

    @classmethod
    def _extract_recaptcha_info(cls, soup: BeautifulSoup, html_lower: str) -> dict:
        sitekey = cls._extract_sitekey(soup, "data-sitekey")
        info = {"sitekey": sitekey}
        if "recaptcha/v3" in html_lower or "version=v3" in html_lower:
            info["captcha_type"] = CaptchaType.RECAPTCHA_V3
        else:
            info["captcha_type"] = CaptchaType.RECAPTCHA_V2
        info["api_server"] = cls._extract_attr(soup, "script", "src", r"api\.js")
        return info

    @classmethod
    def _extract_sitekey(cls, soup: BeautifulSoup, attr: str) -> str:
        for tag in soup.find_all(attrs={attr: True}):
            return tag[attr]
        # 尝试从 script 中提取
        for script in soup.find_all("script", string=True):
            m = re.search(rf'{attr}["\']?\s*[:=]\s*["\']([^"\']+)["\']', script.string)
            if m:
                return m.group(1)
        return ""

    @classmethod
    def _extract_attr(cls, soup: BeautifulSoup, tag: str, attr: str, pattern: str) -> str:
        for el in soup.find_all(tag, attrs={attr: True}):
            if re.search(pattern, el[attr]):
                return el[attr]
        return ""

    @classmethod
    def _extract_image_captcha(cls, soup: BeautifulSoup, base_url: str) -> dict:
        for img in soup.find_all("img"):
            src = img.get("src", "")
            img_id = img.get("id", "").lower()
            alt = (img.get("alt") or "").lower()
            cls_name = " ".join(img.get("class", [])).lower()
            combined = f"{src} {img_id} {alt} {cls_name}"
            if any(kw in combined for kw in ("captcha", "verify", "code", "seccode")):
                if src and not src.startswith("http"):
                    src = httpx.URL(base_url).join(httpx.URL(src)).__str__()
                # 还可能需要找到对应的 input
                input_name = ""
                for inp in soup.find_all("input", attrs={"name": True}):
                    n = inp["name"].lower()
                    if any(kw in n for kw in ("captcha", "verify", "code")):
                        input_name = inp["name"]
                        break
                return {"image_url": src, "input_name": input_name}
        return {}


class CaptchaSolver:
    """验证码识别服务 — 支持 2captcha"""

    API_URL = "https://api.2captcha.com"

    def __init__(self, api_key: str, timeout: int = 120):
        self.api_key = api_key
        self.timeout = timeout

    async def solve_recaptcha_v2(
        self, sitekey: str, page_url: str
    ) -> str | None:
        """识别 reCAPTCHA v2，返回 g-recaptcha-response token"""
        return await self._solve({
            "clientKey": self.api_key,
            "task": {
                "type": "RecaptchaV2TaskProxyless",
                "websiteURL": page_url,
                "websiteKey": sitekey,
            },
        })

    async def solve_recaptcha_v3(
        self, sitekey: str, page_url: str, action: str = "verify", min_score: float = 0.3
    ) -> str | None:
        """识别 reCAPTCHA v3，返回 token"""
        return await self._solve({
            "clientKey": self.api_key,
            "task": {
                "type": "RecaptchaV3TaskProxyless",
                "websiteURL": page_url,
                "websiteKey": sitekey,
                "minScore": min_score,
                "pageAction": action,
            },
        })

    async def solve_hcaptcha(self, sitekey: str, page_url: str) -> str | None:
        """识别 hCaptcha，返回 token"""
        return await self._solve({
            "clientKey": self.api_key,
            "task": {
                "type": "HCaptchaTaskProxyless",
                "websiteURL": page_url,
                "websiteKey": sitekey,
            },
        })

    async def solve_image_captcha(self, image_url: str) -> str | None:
        """识别图片验证码，返回验证码文本"""
        # 下载图片并 base64 编码
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(image_url)
        body_b64 = base64.b64encode(resp.content).decode()
        return await self._solve({
            "clientKey": self.api_key,
            "task": {
                "type": "ImageToTextTask",
                "body": body_b64,
            },
        })

    async def _solve(self, payload: dict) -> str | None:
        """通用 2captcha 识别流程:
        1. POST /createTask 创建任务
        2. 轮询 POST /getTaskResult 获取结果
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # 创建任务
            create_resp = await client.post(
                f"{self.API_URL}/createTask", json=payload
            )
            create_data = create_resp.json()
            if create_data.get("errorId") != 0:
                error = create_data.get("errorDescription", "Unknown error")
                print(f"[CAPTCHA] 创建任务失败: {error}")
                return None
            task_id = create_data["taskId"]

            # 轮询获取结果
            for _ in range(60):  # 最多等 120 秒 (每次 2 秒)
                await httpx.AsyncClient().asleep(2)
                result_resp = await client.post(
                    f"{self.API_URL}/getTaskResult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                )
                result_data = result_resp.json()
                if result_data.get("status") == "ready":
                    token = result_data["solution"].get("token") or result_data["solution"].get("text") or ""
                    if token:
                        return token
                if result_data.get("errorId") != 0:
                    error = result_data.get("errorDescription", "Unknown error")
                    if "not ready" not in error.lower():
                        print(f"[CAPTCHA] 识别失败: {error}")
                        return None

            print("[CAPTCHA] 识别超时")
            return None


def needs_captcha_solve(html: str, status_code: int = 200, url: str = "") -> tuple[bool, CaptchaType, dict]:
    """快捷方法：检测页面是否需要验证码识别"""
    if status_code in (403, 503):
        return True, CaptchaType.CLOUDFLARE, {}

    return CaptchaDetector.detect(html, url)
