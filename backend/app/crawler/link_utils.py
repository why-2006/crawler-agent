from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "source", "sessionid", "phpsessid",
    "clickid", "affiliate", "tracking", "mc_cid", "mc_eid",
}


def normalize_url(url: str, base_url: str = "") -> str:
    """规范化 URL：转绝对路径、去 fragment、去追踪参数、统一尾部斜杠"""
    if base_url:
        url = urljoin(base_url, url)

    parsed = urlparse(url)

    # 去除 fragment
    parsed = parsed._replace(fragment="")

    # 去除追踪参数
    if parsed.query:
        qsl = parse_qsl(parsed.query, keep_blank_values=True)
        clean_qsl = [(k, v) for k, v in qsl if k.lower() not in TRACKING_PARAMS]
        parsed = parsed._replace(query=urlencode(clean_qsl) if clean_qsl else "")

    # 统一路径尾部斜杠：去掉尾部 /
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    parsed = parsed._replace(path=path)

    return urlunparse(parsed)


def is_same_domain(url1: str, url2: str) -> bool:
    """判断两个 URL 是否同域"""
    return urlparse(url1).netloc == urlparse(url2).netloc


def get_domain(url: str) -> str:
    return urlparse(url).netloc


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme in ("http", "https") and parsed.netloc)


def is_page_url(url: str) -> bool:
    """过滤非页面资源：图片、CSS、JS、字体等"""
    skip_extensions = {
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
        ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
        ".pdf", ".zip", ".tar", ".gz", ".mp4", ".mp3", ".avi",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".xml", ".json", ".rss", ".atom", ".csv",
    }
    path = urlparse(url).path.lower()
    return not any(path.endswith(ext) for ext in skip_extensions)


# URL 路径关键词，匹配到则跳过（不包含目标数据）
SKIP_PATH_PATTERNS = [
    "about", "contact", "login", "signup", "signin", "register",
    "cart", "checkout", "terms", "privacy", "faq", "help",
    "search", "tag", "archive", "author", "account", "wishlist",
    "order", "shipping", "returns", "legal", "cookie", "subscribe",
    "newsletter", "press", "careers", "jobs", "investor",
    "accessibility", "sitemap",
]

# 分页 URL 正则：匹配 /page/2, /page/3 等
import re as _re
_PAGINATION_RE = _re.compile(r"/page/(\d+)", _re.I)


def should_skip_url(url: str) -> tuple[bool, str]:
    """智能判断 URL 是否应跳过（不包含目标数据）。
    返回 (是否跳过, 原因)
    """
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    # 检查路径关键词
    for keyword in SKIP_PATH_PATTERNS:
        if f"/{keyword}" in path_lower or path_lower.startswith(f"{keyword}"):
            return True, f"路径关键词: {keyword}"

    # 检查分页（保留第 1 页，跳过 page/2, page/3...）
    m = _PAGINATION_RE.search(path_lower)
    if m and int(m.group(1)) > 1:
        return True, f"分页: page/{m.group(1)}"

    # 检查查询参数过多（通常为过滤/排序/跟踪）
    if parsed.query:
        qsl = parse_qsl(parsed.query, keep_blank_values=True)
        if len(qsl) > 5:
            return True, f"查询参数过多: {len(qsl)}"

    return False, ""


# ─── 蜜罐链检测 ──────────────────────────────────────────

_HONEYPOT_STYLE_PATTERNS = [
    "display:none", "display: none",
    "visibility:hidden", "visibility: hidden",
    "opacity:0", "opacity: 0",
    "font-size:0", "font-size: 0",
    "font-size:0px",
    "color:transparent", "color: transparent",
    "text-indent:-9999",
    "left:-9999", "left: -9999",
    "top:-9999", "top: -9999",
    "position:absolute;left:-9999",
    "position:absolute;top:-9999",
    "width:0", "width: 0",
    "height:0", "height: 0",
    "overflow:hidden",
    "clip:rect(0,0,0,0)",
    "pointer-events:none",
]

_HONEYPOT_CLASS_PATTERNS = [
    "hidden", "hide", "display-none", "invisible",
    "sr-only", "visually-hidden", "screen-reader",
    "no-display", "d-none", "opacity-0",
]


def is_honeypot_link(el) -> tuple[bool, str]:
    """检测元素是否为反爬蜜罐链。
    返回 (是否蜜罐, 原因)
    """
    # 1. 检查内联样式
    style = (el.get("style") or "").lower().replace(" ", "")
    for pattern in _HONEYPOT_STYLE_PATTERNS:
        if pattern.replace(" ", "") in style:
            return True, f"蜜罐 style: {el.get('style', '')[:60]}"

    # 2. aria-hidden
    if el.get("aria-hidden") == "true":
        return True, "aria-hidden=true"

    # 3. role="presentation"
    role = el.get("role") or ""
    if role.lower() in ("presentation", "none"):
        return True, f"role={role}"

    # 4. 可疑 class 名
    classes = [c.lower() for c in el.get("class", [])]
    for cls in classes:
        if cls in _HONEYPOT_CLASS_PATTERNS:
            return True, f"蜜罐 class: {cls}"

    # 5. 链接文本为不可见字符
    text = el.get_text(strip=True)
    if text in ("\u200b", "\u00a0", "\u200d", "&#8203;", ""):
        href = el.get("href", "")[:50]
        if href and not text:
            return True, "空链接文本"

    # 6. 父元素检测（递归检查父元素样式）
    parent = el.parent
    if parent and parent.name:
        parent_style = (parent.get("style") or "").lower().replace(" ", "")
        for pattern in _HONEYPOT_STYLE_PATTERNS:
            if pattern.replace(" ", "") in parent_style:
                return True, f"父元素蜜罐: {parent.get('style', '')[:60]}"

    return False, ""
