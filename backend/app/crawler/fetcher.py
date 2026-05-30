from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.crawler.proxy import ProxyManager
from app.crawler.session import SessionStore
from app.crawler.stealth import (
    UserAgentRotator,
    HeaderNormalizer,
    delay_with_jitter,
    retry_with_backoff,
)

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

from app.crawler.captcha import (
    CaptchaDetector,
    CaptchaSolver,
    CaptchaType,
    needs_captcha_solve,
)
from app.models.schemas import FetchResult, PageData


SPA_ROOT_PATTERNS = [
    ("div", {"id": "root"}),
    ("div", {"id": "app"}),
    ("div", {"id": "__next"}),
    ("div", {"id": "__nuxt"}),
]

# ─── BeautifulSoup HTML 语义增强 ───

def enhance_html_with_semantics(html: str, url: str = "") -> str:
    """
    用 BeautifulSoup 解析 HTML，将隐藏在 CSS class / 属性中的语义信息转为可见文本。
    解决 rating（star-rating class）、data-* 属性等在纯文本提取中丢失的问题。
    """
    soup = BeautifulSoup(html, "lxml")

    # 1. star-rating class → 文字评分
    for tag in soup.find_all(class_=re.compile(r"star-rating", re.I)):
        classes = tag.get("class", [])
        rating_map = {"One": "1", "Two": "2", "Three": "3", "Four": "4", "Five": "5"}
        for cls in classes:
            if cls in rating_map:
                tag.insert(0, f"[评分: {rating_map[cls]}/5 星] ")
                break

    # 2. img alt 文本 → 保留为可见文字
    for img in soup.find_all("img", alt=True):
        alt = img["alt"].strip()
        if alt:
            img.insert_after(f"[图片: {alt}]")

    # 3. data-* 属性中有语义值的情况
    for tag in soup.find_all(attrs={"data-price": True}):
        tag.insert(0, f"[价格: {tag['data-price']}] ")

    for tag in soup.find_all(attrs={"data-rating": True}):
        tag.insert(0, f"[评分: {tag['data-rating']}] ")

    # 4. aria-label → 可见文本
    for tag in soup.find_all(attrs={"aria-label": True}):
        label = tag["aria-label"].strip()
        if label:
            tag.insert(0, f" {label} ")

    # 5. meta description / keywords
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        soup.body.insert(0, f"\n[页面描述: {meta_desc['content']}]\n")

    # 6. breadcrumb 导航 → 保留层级结构
    for bc in soup.find_all(class_=re.compile(r"breadcrumb", re.I)):
        links = bc.find_all("a")
        if links:
            crumbs = " > ".join(a.get_text(strip=True) for a in links)
            bc.insert_after(f"\n[面包屑导航: {crumbs}]\n")

    # 7. table → 保留表格结构的关键信息
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if headers:
            table.insert_before(f"\n[表格列: {', '.join(headers)}]")

    # 8. 价格相关 class → 标记
    for tag in soup.find_all(class_=re.compile(r"price|amount|cost", re.I)):
        text = tag.get_text(strip=True)
        if text:
            tag.insert_before(f"[价格信息] ")

    # 9. stock/availability class → 标记
    for tag in soup.find_all(class_=re.compile(r"(stock|availability|in-stock|out-of-stock)", re.I)):
        classes = " ".join(tag.get("class", []))
        tag.insert_before(f"[库存: {classes}] ")

    return str(soup)


def html_to_rich_text(html: str, url: str = "", max_chars: int = None) -> str:
    """
    将 HTML 转为语义增强的纯文本。
    1. 先用 BeautifulSoup 增强语义
    2. 再提取文本
    """
    if max_chars is None:
        max_chars = settings.page_text_max_chars

    enhanced_html = enhance_html_with_semantics(html, url)
    soup = BeautifulSoup(enhanced_html, "lxml")

    # 移除无内容的样式/脚本标签
    for tag in soup(["script", "style"]):
        tag.decompose()

    # 保留更多结构信息的标签，转为换行
    for tag_name in ["nav", "footer", "header", "aside"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    text = soup.body.get_text(separator="\n", strip=True) if soup.body else ""

    # 合并多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    if len(text) > max_chars:
        text = text[:max_chars]

    return text


class Fetcher:
    """双通道页面抓取器：httpx 静态抓取 + Playwright JS 渲染 + CAPTCHA 识别"""

    _semaphore = asyncio.Semaphore(settings.browser_concurrency)
    _playwright_instance = None
    _browser = None
    _domain_last_request: dict[str, float] = {}
    _ua_rotator: UserAgentRotator | None = None
    _proxy_manager: ProxyManager | None = None
    _session_store: SessionStore | None = None

    @classmethod
    def _get_ua_rotator(cls) -> UserAgentRotator:
        if cls._ua_rotator is None:
            cls._ua_rotator = UserAgentRotator(
                custom_list=settings.ua_rotation_custom_list
            )
        return cls._ua_rotator

    @classmethod
    def _get_proxy_manager(cls) -> ProxyManager:
        if cls._proxy_manager is None:
            cls._proxy_manager = ProxyManager(
                proxy_url=settings.proxy_url,
                rotation_list=settings.proxy_list,
            )
        return cls._proxy_manager

    @classmethod
    def _get_session_store(cls) -> SessionStore:
        if cls._session_store is None:
            cls._session_store = SessionStore()
        return cls._session_store

    def __init__(self, task_data_dir: Path | None = None, anti_crawl_config=None,
                 seed_domain: str = ""):
        from app.models.schemas import AntiCrawlConfig
        self._task_data_dir = task_data_dir
        self._anti_crawl = anti_crawl_config if isinstance(anti_crawl_config, AntiCrawlConfig) else None
        self._captcha_solver: CaptchaSolver | None = None
        self._captcha_fail_count: dict[str, int] = {}  # 域名 → 连续失败次数
        self._seed_domain = seed_domain

        # 熔断器：域名 → 解封时间戳（monotonic）
        self._blocked_domains: dict[str, float] = {}

        # 动态 Referer：域名 → 上次成功抓取的 URL
        self._domain_last_url: dict[str, str] = {}

        if settings.captcha_api_key:
            self._captcha_solver = CaptchaSolver(
                api_key=settings.captcha_api_key,
                timeout=120,
            )

    # ─── 熔断器 ──────────────────────────────────────────

    def is_domain_blocked(self, domain: str) -> bool:
        """检查域名是否被熔断器封锁（过期自动解封）"""
        until = self._blocked_domains.get(domain)
        if until is None:
            return False
        if time.monotonic() >= until:
            del self._blocked_domains[domain]
            return False
        return True

    def _block_domain(self, domain: str) -> None:
        """封锁域名（种子域永不封锁）"""
        if domain == self._seed_domain:
            return
        cooldown = settings.circuit_breaker_cooldown_seconds
        self._blocked_domains[domain] = time.monotonic() + cooldown
        print(f"[断路器] 域名 {domain} 已被阻止 {cooldown}s，原因：连续验证码失败")

    @property
    def blocked_domains(self) -> set[str]:
        """返回当前被封锁的域名集合（供 agent 清理队列）"""
        now = time.monotonic()
        return {d for d, until in self._blocked_domains.items() if until > now}

    # ─── 浏览器管理 ──────────────────────────────────────

    @classmethod
    async def _get_browser(cls):
        if not _playwright_available:
            raise RuntimeError("playwright 未安装，无法使用 JS 渲染")
        if cls._browser is None:
            # 诊断：打印当前事件循环类型（仅首次启动时）
            try:
                loop = asyncio.get_running_loop()
                print(f"[调试] 当前事件循环类型: {type(loop).__name__}")
            except RuntimeError:
                print("[调试] 无运行中的事件循环")
            cls._playwright_instance = await async_playwright().start()
            cls._browser = await cls._playwright_instance.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
        return cls._browser

    @classmethod
    async def close_browser(cls):
        if cls._browser:
            await cls._browser.close()
        if cls._playwright_instance:
            await cls._playwright_instance.stop()
        cls._browser = None
        cls._playwright_instance = None

    def _build_headers(self, domain: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        """构建请求头：根据配置决定是否轮换 UA 和标准化"""
        headers: dict[str, str] = {}
        if extra:
            headers.update(extra)

        # 动态 Referer：同域名上次成功抓取的 URL
        referer = self._domain_last_url.get(domain)
        if referer:
            headers["Referer"] = referer

        ua_rotation = self._anti_crawl.ua_rotation if self._anti_crawl else settings.ua_rotation_enabled
        header_norm = self._anti_crawl.header_normalization if self._anti_crawl else settings.header_normalization

        if ua_rotation:
            ua = self._get_ua_rotator().for_domain(domain)
        else:
            ua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            )
        headers["User-Agent"] = ua

        if header_norm:
            headers = HeaderNormalizer.normalize(headers, referer_present=bool(referer))

        return headers

    @property
    def _session_enabled(self) -> bool:
        if self._anti_crawl:
            return self._anti_crawl.session_persistence
        return settings.session_persistence_enabled

    def _build_cookie_header(self, domain: str) -> str:
        cookies = self._get_session_store().load_cookies(domain)
        if not cookies:
            return ""
        pairs = []
        for c in cookies:
            name = c.get("name", "")
            value = c.get("value", "")
            if name:
                pairs.append(f"{name}={value}")
        return "; ".join(pairs)

    async def _respect_rate_limit(self, domain: str) -> None:
        now = time.monotonic()
        last = self._domain_last_request.get(domain, 0)
        wait = settings.request_delay_seconds - (now - last)
        jitter = self._anti_crawl.jitter_ratio if self._anti_crawl else settings.request_jitter_ratio
        if wait > 0:
            await delay_with_jitter(wait, jitter)
        self._domain_last_request[domain] = time.monotonic()

    async def _handle_captcha(self, html: str, url: str) -> str | None:
        """
        检测并尝试识别验证码。
        返回 None 表示识别失败或不需要识别。
        """
        if not self._captcha_solver:
            return None

        domain = urlparse(url).netloc

        # 同一域名连续失败 3 次，跳过后续验证码尝试
        if self._captcha_fail_count.get(domain, 0) >= 3:
            print(f"[CAPTCHA] {domain} 连续验证码失败 3 次，跳过后续尝试")
            return None

        has_captcha, captcha_type, info = needs_captcha_solve(html, url=url)
        if not has_captcha:
            return None

        print(f"[CAPTCHA] 检测到验证码: {captcha_type.value}")

        try:
            result = None
            if captcha_type == CaptchaType.RECAPTCHA_V2:
                sitekey = info.get("sitekey", "")
                if sitekey:
                    result = await self._captcha_solver.solve_recaptcha_v2(sitekey, url)
            elif captcha_type == CaptchaType.RECAPTCHA_V3:
                sitekey = info.get("sitekey", "")
                if sitekey:
                    result = await self._captcha_solver.solve_recaptcha_v3(sitekey, url)
            elif captcha_type == CaptchaType.HCAPTCHA:
                sitekey = info.get("sitekey", "")
                if sitekey:
                    result = await self._captcha_solver.solve_hcaptcha(sitekey, url)
            elif captcha_type == CaptchaType.IMAGE:
                img_url = info.get("image_url", "")
                if img_url:
                    result = await self._captcha_solver.solve_image_captcha(img_url)
            elif captcha_type == CaptchaType.CLOUDFLARE:
                print("[CAPTCHA] Cloudflare 验证，2captcha 不支持，请使用 JS 渲染模式")

            if result:
                self._captcha_fail_count[domain] = 0  # 成功则重置计数
                return result
            else:
                self._captcha_fail_count[domain] = self._captcha_fail_count.get(domain, 0) + 1
                # 熔断检查
                if self._captcha_fail_count[domain] >= settings.circuit_breaker_threshold:
                    self._block_domain(domain)
                return None
        except Exception as e:
            self._captcha_fail_count[domain] = self._captcha_fail_count.get(domain, 0) + 1
            print(f"[CAPTCHA] 识别异常: {e}")
            # 熔断检查
            if self._captcha_fail_count[domain] >= settings.circuit_breaker_threshold:
                self._block_domain(domain)

        return None

    async def fetch_static(self, url: str, retry_captcha: bool = True) -> PageData:
        """httpx 静态抓取，自动检测并处理 CAPTCHA"""
        domain = urlparse(url).netloc

        # 熔断器：被封锁域名直接跳过
        if self.is_domain_blocked(domain):
            raise RuntimeError(f"域名 {domain} 已被熔断器阻止，跳过抓取")

        await self._respect_rate_limit(domain)

        headers = self._build_headers(domain)

        # Session 持久化：加载已有 cookies
        if self._session_enabled:
            cookie_header = self._build_cookie_header(domain)
            if cookie_header:
                headers["Cookie"] = cookie_header

        resp_for_session = None

        async def _do_request() -> PageData:
            nonlocal resp_for_session
            proxy = self._get_proxy_manager().for_httpx(domain)
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                headers=headers,
                proxy=proxy,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                resp_for_session = resp
                html = resp.text

                if retry_captcha and self._captcha_solver:
                    captcha_token = await self._handle_captcha(html, url)
                    if captcha_token:
                        captcha_url = (
                            f"{url}?g-recaptcha-response={captcha_token}"
                            if "?" not in url
                            else f"{url}&g-recaptcha-response={captcha_token}"
                        )
                        resp2 = await client.get(captcha_url)
                        resp2.raise_for_status()
                        resp_for_session = resp2
                        html = resp2.text

                self._domain_last_url[domain] = url
                return self._parse_html(url, html, rendered=False)

        retry_enabled = self._anti_crawl.retry_enabled if self._anti_crawl else settings.retry_enabled
        if retry_enabled:
            retry_codes = {int(c.strip()) for c in settings.retry_on_status.split(",") if c.strip()}
            max_attempts = self._anti_crawl.retry_max_attempts if self._anti_crawl else settings.retry_max_attempts

            def _is_retryable(exc: Exception) -> bool:
                if isinstance(exc, httpx.HTTPStatusError):
                    return exc.response.status_code in retry_codes
                if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError)):
                    return True
                return False

            result = await retry_with_backoff(
                _do_request,
                is_retryable=_is_retryable,
                max_attempts=max_attempts,
                backoff_initial=settings.retry_backoff_initial,
                backoff_max=settings.retry_backoff_max,
            )
        else:
            result = await _do_request()

        # Session 持久化：保存响应的 cookies
        if self._session_enabled and resp_for_session is not None:
            try:
                new_cookies = SessionStore.extract_cookies_from_httpx(resp_for_session)
                if new_cookies:
                    existing = self._get_session_store().load_cookies(domain)
                    merged = {c["name"]: c for c in existing}
                    for c in new_cookies:
                        merged[c["name"]] = c
                    self._get_session_store().save(domain, list(merged.values()))
            except Exception:
                pass

        return result

    async def fetch_with_js(self, url: str) -> PageData:
        """Playwright JS 渲染"""
        if not _playwright_available:
            raise RuntimeError("playwright 未安装")

        domain = urlparse(url).netloc

        # 熔断器：被封锁域名直接跳过
        if self.is_domain_blocked(domain):
            raise RuntimeError(f"域名 {domain} 已被熔断器阻止，跳过 JS 渲染")

        # 速率限制（JS 通道原先缺失）
        await self._respect_rate_limit(domain)

        async with self._semaphore:
            browser = await self._get_browser()

            # 优先使用登录时保存的 UA，保持与 Cookie 一致的指纹
            saved_ua = ""
            if self._session_enabled:
                saved_ua = self._get_session_store().load_user_agent(domain)
            if saved_ua:
                pw_ua = saved_ua
            elif settings.ua_rotation_enabled:
                pw_ua = self._get_ua_rotator().for_domain(domain)
            else:
                pw_ua = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
                )
            proxy = self._get_proxy_manager().for_playwright(domain) or None
            storage_state = self._get_session_store().load_storage_state(domain) if self._session_enabled else None
            context = await browser.new_context(
                user_agent=pw_ua,
                viewport={"width": 1920, "height": 1080},
                proxy=proxy,
                storage_state=storage_state,
            )
            page = await context.new_page()
            try:
                if settings.playwright_stealth_enabled and _stealth_available:
                    await stealth_async(page)
                # 手动补充指纹隐藏（playwright-stealth 可能未覆盖的字段）
                if settings.playwright_stealth_enabled:
                    await page.add_init_script("""
                        // 1. 隐藏 webdriver 标记
                        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

                        // 2. 伪装 plugins（真实浏览器至少有 PDF Viewer 等）
                        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});

                        // 3. 伪装语言偏好
                        Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en-US','en']});

                        // 4. 伪装硬件并发数（真实桌面常见 4/8/16）
                        Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});

                        // 5. 伪装设备内存（真实桌面常见 4/8/16 GB）
                        Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

                        // 6. 伪装屏幕尺寸以匹配 viewport
                        Object.defineProperty(screen, 'width', {get: () => 1920});
                        Object.defineProperty(screen, 'height', {get: () => 1080});
                        Object.defineProperty(screen, 'availWidth', {get: () => 1920});
                        Object.defineProperty(screen, 'availHeight', {get: () => 1040});
                        Object.defineProperty(screen, 'colorDepth', {get: () => 24});
                        Object.defineProperty(screen, 'pixelDepth', {get: () => 24});

                        // 7. 伪装 WebGL 渲染器（headless 默认暴露 Google/ANGLE）
                        try {
                            const getParam = WebGLRenderingContext.prototype.getParameter;
                            WebGLRenderingContext.prototype.getParameter = function(p) {
                                if (p === 37445) return 'Intel Inc.';
                                if (p === 37446) return 'Intel Iris OpenGL Engine';
                                return getParam.call(this, p);
                            };
                        } catch(e) {}

                        // 8. 恢复 chrome 对象（很多反爬脚本检测）
                        window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};

                        // 9. 伪装 Permissions API
                        try {
                            const origQuery = window.navigator.permissions.query;
                            window.navigator.permissions.query = (parameters) => (
                                parameters.name === 'notifications' ?
                                    Promise.resolve({state: Notification.permission}) :
                                    origQuery(parameters)
                            );
                        } catch(e) {}
                    """)
                await page.route(
                    re.compile(r"\.(png|jpg|jpeg|gif|svg|webp|ico|woff2?|ttf|eot|mp4|mp3|avi)(\?.*)?$"),
                    lambda route: route.abort(),
                )
                # 先尝试 networkidle（SPA 完整渲染），超时则降级为 load
                try:
                    await page.goto(url, wait_until="networkidle", timeout=15000)
                except Exception:
                    await page.goto(url, wait_until="load", timeout=settings.playwright_timeout_ms)
                # 给动态内容额外渲染时间
                await asyncio.sleep(2)
                html = await page.content()

                # 在浏览器中检测 Cloudflare 验证
                cf_detected = await page.evaluate("""
                    () => document.body.innerText.includes('Just a moment') ||
                             document.body.innerText.includes('Checking your browser')
                """)
                if cf_detected:
                    print("[CAPTCHA] 检测到 Cloudflare 验证，等待自动通过...")
                    await page.wait_for_load_state("networkidle", timeout=60000)
                    html = await page.content()

                self._domain_last_url[domain] = url
                return self._parse_html(url, html, rendered=True)
            except Exception:
                try:
                    html = await page.content()
                    self._domain_last_url[domain] = url
                    return self._parse_html(url, html, rendered=True)
                except Exception:
                    raise
            finally:
                if self._session_enabled:
                    try:
                        cookies = await context.cookies()
                        local_storage = {}
                        try:
                            ls_raw = await page.evaluate("JSON.stringify(localStorage)")
                            if ls_raw:
                                local_storage = json.loads(ls_raw)
                        except Exception:
                            pass
                        self._get_session_store().save(domain, cookies, local_storage)
                    except Exception:
                        pass
                await context.close()

    async def fetch(self, url: str, use_javascript: bool = False) -> PageData:
        """统一入口：先静态尝试，自动切换 JS 或处理 CAPTCHA"""
        try:
            page_data = await self.fetch_static(url)

            # 静态抓取后页面仍包含验证码 → 强制浏览器渲染重试
            has_captcha, _, _ = needs_captcha_solve(page_data.html, url=url)
            if has_captcha:
                print("[CAPTCHA] 静态抓取遇到验证码，尝试浏览器渲染绕过...")
                try:
                    return await self.fetch_with_js(url)
                except Exception as e:
                    print(f"[CAPTCHA] 浏览器渲染也失败: {e}，返回静态页面")

            if use_javascript or self._needs_js(page_data.text_content, page_data.html):
                return await self.fetch_with_js(url)
            return page_data
        except Exception:
            if not use_javascript:
                try:
                    return await self.fetch_with_js(url)
                except Exception:
                    raise
            raise

    def _needs_js(self, text: str, html: str) -> bool:
        if len(text.strip()) < 200:
            return True
        soup = BeautifulSoup(html, "lxml")
        for tag_name, attrs in SPA_ROOT_PATTERNS:
            if soup.find(tag_name, attrs):
                return True
        return False

    def _parse_html(self, url: str, html: str, rendered: bool = False) -> PageData:
        """解析 HTML，用 BeautifulSoup 语义增强后提取文本"""
        soup = BeautifulSoup(html, "lxml")

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # 用增强版文本提取（保留 CSS class 语义、alt 文本等）
        text = html_to_rich_text(html, url)

        links = soup.find_all("a", href=True)
        links_count = len(links)

        if self._task_data_dir:
            self._task_data_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^\w\-.]", "_", urlparse(url).path.strip("/") or "index")
            html_file = self._task_data_dir / f"{safe_name}.html"
            html_file.write_text(html, encoding="utf-8")

        return PageData(
            url=url,
            title=title,
            text_content=text,
            html=html,
            links_count=links_count,
            content_type="text/html",
            rendered=rendered,
        )

    # 多标签/属性提取映射：标签 → 属性列表(按优先级)
    _TAG_ATTRS: dict[str, list[str]] = {
        "a": ["href"],
        "link": ["href"],
        "area": ["href"],
        "iframe": ["src"],
        "frame": ["src"],
    }
    #提取标签中的链接，并转换为绝对 URL，去重后返回列表
    def extract_links(self, page_data: PageData) -> list[tuple[str, str]]:
        soup = BeautifulSoup(page_data.html, "lxml")
        seen: set[str] = set()
        links: list[tuple[str, str]] = []
        #添加链接的内部函数，负责过滤无效链接、转换为绝对 URL、去重，并保存链接文本
        def _add(href: str, text: str = "") -> None:
            if not href or href.startswith("javascript:") or href.startswith("#"):
                return
            absolute = urljoin(page_data.url, href)
            if absolute not in seen:
                seen.add(absolute)
                links.append((absolute, text))

        # 1. 多标签提取：a / link / area / iframe / frame / base
        for tag, attrs in self._TAG_ATTRS.items():
            for el in soup.find_all(tag):
                for attr in attrs:
                    val = el.get(attr)
                    if val:
                        text = el.get_text(strip=True) if tag in ("a", "area") else ""
                        _add(val.strip(), text)

        # 2. 内联 CSS 中的 url()
        for el in soup.find_all(style=True):
            for m in re.finditer(r'url\(["\']?([^)"\']+)["\']?\)', el["style"], re.I):
                _add(m.group(1).strip())

        # 3. <script> / onclick 等 JS 中引用的 URL 片段（低风险正则）
        _JS_RE = re.compile(
            r"""["']((?:https?:)?//[^\s"'<>]+|/[^\s"'<>,;!]+?\.[a-z]{2,6}(?:/[^\s"'<>,;]*)?)["']""",
            re.I,
        )
        for el in soup.find_all(["script"], src=False):
            if el.string:
                for m in _JS_RE.finditer(el.string):
                    candidate = m.group(1)
                    if not candidate.startswith("http") and not candidate.startswith("//"):
                        candidate = candidate.lstrip("/")
                    _add(candidate)

        return links
