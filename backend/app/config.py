from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    openai_api_key: str = "sk-xxx"
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    # 爬虫默认值
    default_max_depth: int = 3
    default_max_pages: int = 50
    page_text_max_chars: int = 8000
    request_delay_seconds: float = 2.0
    browser_concurrency: int = 1
    playwright_timeout_ms: int = 30000

    # CAPTCHA 识别服务
    captcha_api_key: str = ""
    captcha_provider: str = "2captcha"

    # ─── 反反爬虫 ──────────────────────────────────────────
    # UA 轮换
    ua_rotation_enabled: bool = False
    ua_rotation_custom_list: str = ""  # 逗号分隔的自定义 UA 列表，空=使用内置列表

    # 请求头标准化（补充浏览器典型请求头）
    header_normalization: bool = True

    # 延迟抖动系数（0=无抖动, 0.5=±50%）
    request_jitter_ratio: float = 0.3

    # 指数退避重试
    retry_enabled: bool = True
    retry_max_attempts: int = 3
    retry_backoff_initial: float = 1.0  # 秒
    retry_backoff_max: float = 30.0  # 秒
    retry_on_status: str = "429,503,502,403"  # 触发重试的 HTTP 状态码

    # 域名级熔断器：同域名连续验证码失败 N 次后阻止该域名
    circuit_breaker_threshold: int = 3
    # 被熔断的域名冷却时间（秒），过期后可重新尝试
    circuit_breaker_cooldown_seconds: int = 300

    # 代理
    proxy_url: str = ""  # http://user:pass@host:port 或 socks5://host:port
    proxy_rotation_enabled: bool = False
    proxy_list: str = ""  # 逗号分隔的代理列表

    # Playwright 指纹隐藏
    playwright_stealth_enabled: bool = False

    # Session/Cookie 持久化
    session_persistence_enabled: bool = False
    profiles_dir: str = "./data/profiles"

    # 蜜罐链检测
    honeypot_detection_enabled: bool = True

    # 存储
    database_path: str = "./data/crawler.db"
    task_data_dir: str = "./data/tasks"

    # 服务
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
