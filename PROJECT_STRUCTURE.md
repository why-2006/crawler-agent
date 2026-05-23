# crawler-agent 项目结构（函数级颗粒度）

```
crawler-agent/
├── .gitignore                              — 忽略 Python/Node/IDE/Env 产物
├── package-lock.json                       — 根级空 lockfile
│
├── backend/
│   ├── app/
│   │   ├── __init__.py                     — 空，标记为 Python 包
│   │   │
│   │   ├── main.py                         — FastAPI 应用入口
│   │   │   ├── lifespan()                  — 启动时初始化DB+调度器，关闭时停止调度器
│   │   │   └── health()                    — GET /api/health 健康检查
│   │   │
│   │   ├── config.py                       — 全局配置（pydantic-settings）
│   │   │   └── Settings                    — LLM密钥/模型、爬虫默认值、反反爬虫开关、代理、CAPTCHA、存储路径、服务端口
│   │   │
│   │   ├── scheduler.py                    — 定时任务调度器
│   │   │   └── TaskScheduler
│   │   │       ├── set_run_crawl()         — 注入爬取执行函数
│   │   │       ├── start()                 — 启动轮询循环
│   │   │       ├── stop()                  — 停止轮询，取消 asyncio Task
│   │   │       └── _loop()                 — 每30秒轮询DB，触发到期定时任务并更新下次执行时间
│   │   │
│   │   ├── agent/
│   │   │   ├── __init__.py                 — 空
│   │   │   │
│   │   │   ├── prompts.py                  — LLM 提示词模板（7个）
│   │   │   │   ├── CRAWLER_SYSTEM_PROMPT   — Agent 系统指令：工作策略与约束
│   │   │   │   ├── EXTRACTION_PROMPT_TEMPLATE — 单页数据提取提示词
│   │   │   │   ├── BATCH_EXTRACTION_PROMPT_TEMPLATE — 批量多页提取提示词
│   │   │   │   ├── DECISION_PROMPT_TEMPLATE    — LLM 选择下一步 URL 提示词
│   │   │   │   ├── STEER_PROMPT_TEMPLATE       — LLM 筛选/跳过队列 URL 提示词
│   │   │   │   ├── INSIGHTS_PROMPT_TEMPLATE    — 数据洞察生成提示词
│   │   │   │   └── CHANGE_SUMMARY_PROMPT       — 内容变更摘要提示词
│   │   │   │
│   │   │   ├── tools.py                    — LangChain 工具定义 + 实现函数
│   │   │   │   ├── FetchPageInput          — fetch_page 工具参数 schema
│   │   │   │   ├── ExtractLinksInput       — extract_links 工具参数 schema
│   │   │   │   ├── ExtractDataInput        — extract_data 工具参数 schema
│   │   │   │   ├── UnvisitedLink           — 待抓取链接子模型
│   │   │   │   ├── CrawlConfig             — 爬取配置子模型
│   │   │   │   ├── DecideNextInput         — decide_next_urls 工具参数 schema
│   │   │   │   ├── set_fetcher()           — 注入全局 Fetcher 实例
│   │   │   │   ├── fetch_page_tool()       — 抓取页面，返回标题+文本+链接数 JSON
│   │   │   │   ├── extract_links_tool()    — 提取页面链接，区分站内/站外 JSON
│   │   │   │   ├── extract_data_tool()     — 占位：提示 LLM 需外部提取处理
│   │   │   │   ├── decide_next_urls_tool() — 返回待抓取 URL 列表供 LLM 决策
│   │   │   │   └── ALL_TOOLS               — 4个 StructuredTool 实例列表
│   │   │   │
│   │   │   └── crawler_agent.py            — 爬虫 Agent 核心编排
│   │   │       └── CrawlerAgent
│   │   │           ├── __init__()          — 初始化 Frontier/Fetcher/LLM/AgentExecutor
│   │   │           ├── run()               — 主循环：抓取→发现链接→批量提取→引导→洞察→完成
│   │   │           ├── stop()              — 设置停止标志
│   │   │           ├── _dequeue_batch()    — 从 Frontier 出队 N 个 URL
│   │   │           ├── _fetch_concurrent() — 并发抓取多个 URL（asyncio.gather）
│   │   │           ├── _fetch_page()       — 抓取单页+内容变更检测
│   │   │           ├── _discover_links()   — 提取链接+蜜罐检测+去重+过滤
│   │   │           ├── _extract_and_store()— LLM 单页数据提取并存入 results
│   │   │           ├── _extract_batch()    — LLM 批量多页数据提取（回退到单页）
│   │   │           ├── _decide_next_urls() — LLM 从待抓取队列选择下一步 URL
│   │   │           ├── _steer_frontier()   — 每8页 LLM 筛选队列，跳过不相关 URL
│   │   │           ├── _detect_content_change() — 检测页面内容是否变化（定时监控）
│   │   │           ├── _generate_change_summary() — LLM 生成变更一句话摘要
│   │   │           ├── _generate_insights()— LLM 生成2-4个数据可视化图表配置
│   │   │           ├── _get_depth()        — 计算 URL 相对种子 URL 的深度
│   │   │           └── _report()           — 统一进度回调：broadcast 事件到 WebSocket
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py                 — 空
│   │   │   │
│   │   │   ├── tasks.py                    — 任务 CRUD API（/api/tasks）
│   │   │   │   ├── create_task()           — POST /api/tasks 创建新任务，异步启动爬取
│   │   │   │   ├── list_tasks()            — GET /api/tasks 获取所有任务摘要列表
│   │   │   │   ├── get_task_detail()       — GET /api/tasks/{id} 获取任务详情+结果+洞察+变更
│   │   │   │   ├── delete_task()           — DELETE /api/tasks/{id} 停止并删除任务
│   │   │   │   ├── update_schedule()       — PUT /api/tasks/{id}/schedule 修改定时配置
│   │   │   │   ├── cancel_schedule()       — DELETE /api/tasks/{id}/schedule 取消定时
│   │   │   │   ├── list_content_changes()  — GET /api/tasks/tracking/changes 变更历史
│   │   │   │   ├── list_tracking_stats()   — GET /api/tasks/tracking/stats URL变更统计
│   │   │   │   └── _run_crawl()            — 后台执行爬取：更新状态→创建Agent→run→保存结果
│   │   │   │
│   │   │   ├── websocket.py                — WebSocket 实时推送
│   │   │   │   └── ConnectionManager
│   │   │   │       ├── connect()           — 接受连接，按 task_id 分组
│   │   │   │       ├── disconnect()        — 移除连接，清理空分组
│   │   │   │       ├── broadcast()         — 向某 task_id 的所有连接广播 JSON
│   │   │   │       └── websocket_endpoint()— /ws/tasks/{task_id} 保持长连接+心跳
│   │   │   │
│   │   │   └── login.py                    — 登录管理 API（/api/login）
│   │   │       ├── ProfileCreate           — 登录配置创建请求体
│   │   │       ├── manual_login_start()    — POST /api/login/manual/start 启动可见浏览器
│   │   │       ├── manual_login_complete() — POST /api/login/manual/complete 保存cookies
│   │   │       ├── manual_login_cancel()   — POST /api/login/manual/cancel 取消手动登录
│   │   │       ├── programmatic_login()    — POST /api/login/programmatic 自动表单登录
│   │   │       ├── list_profiles()         — GET /api/login/profiles 列出登录配置
│   │   │       ├── create_profile()        — POST /api/login/profiles 创建登录配置
│   │   │       ├── delete_profile()        — DELETE /api/login/profiles/{name} 删除配置
│   │   │       └── list_active_sessions()  — GET /api/login/sessions 列出活跃手动登录
│   │   │
│   │   ├── crawler/
│   │   │   ├── __init__.py                 — 空
│   │   │   │
│   │   │   ├── fetcher.py                  — 双通道页面抓取器
│   │   │   │   ├── enhance_html_with_semantics() — BeautifulSoup 语义增强：CSS class→文本、alt→文本、data-*→文本、aria-label→文本、meta→文本、breadcrumb→文本、table headers→文本
│   │   │   │   ├── html_to_rich_text()     — HTML→语义增强纯文本（先增强再提取+截断）
│   │   │   │   └── Fetcher
│   │   │   │       ├── _get_ua_rotator()   — 懒加载 UA 轮换器
│   │   │   │       ├── _get_proxy_manager()— 懒加载代理管理器
│   │   │   │       ├── _get_session_store()— 懒加载 Session 存储
│   │   │   │       ├── __init__()          — 初始化任务目录、反爬配置、CAPTCHA 求解器
│   │   │   │       ├── _get_browser()      — 懒加载 Playwright Chromium 实例
│   │   │   │       ├── close_browser()     — 关闭 Playwright 浏览器
│   │   │   │       ├── _build_headers()    — 构建 HTTP 请求头（UA轮换+标准化）
│   │   │   │       ├── _build_cookie_header() — 从 SessionStore 加载 cookies 拼成 header
│   │   │   │       ├── _respect_rate_limit()  — 域名级延迟控制（+抖动）
│   │   │   │       ├── _handle_captcha()   — 检测并识别验证码（reCAPTCHA/hCaptcha/图片）
│   │   │   │       ├── fetch_static()      — httpx 静态抓取（含CAPTCHA重试+session持久化）
│   │   │   │       ├── fetch_with_js()     — Playwright JS渲染（含stealth+资源拦截+CF检测）
│   │   │   │       ├── fetch()             — 统一入口：先静态，必要时自动切换JS渲染
│   │   │   │       ├── _needs_js()         — 判断是否需要JS渲染（文本<200字或SPA根节点）
│   │   │   │       ├── _parse_html()       — 解析HTML→语义增强文本→PageData（含保存HTML）
│   │   │   │       └── extract_links()     — 多标签提取URL（a/link/iframe+CSS url()+JS URL）
│   │   │   │
│   │   │   ├── frontier.py                 — URL 队列管理器
│   │   │   │   └── Frontier
│   │   │   │       ├── __init__()          — 初始化 deque+visited set+域名计数器
│   │   │   │       ├── enqueue()           — 入队（去重+容量限制）
│   │   │   │       ├── enqueue_batch()     — 批量入队，返回成功数
│   │   │   │       ├── dequeue()           — 出队（标记visited+记录域名频次）
│   │   │   │       ├── mark_visited()      — 手动标记已访问
│   │   │   │       ├── is_visited()        — 检查是否已访问
│   │   │   │       ├── has_pending()       — 队列是否有待处理项
│   │   │   │       ├── pending_count()     — 待处理数量
│   │   │   │       ├── visited_count()     — 已访问数量
│   │   │   │       ├── get_pending_urls()  — 获取全部待处理列表（供LLM决策）
│   │   │   │       └── remove_urls()       — 从队列移除指定URL（LLM决定跳过）
│   │   │   │
│   │   │   ├── link_utils.py               — URL 处理与过滤
│   │   │   │   ├── normalize_url()         — 规范化URL（绝对路径+去fragment+去追踪参数+去尾斜杠）
│   │   │   │   ├── is_same_domain()        — 判断两URL是否同域
│   │   │   │   ├── get_domain()            — 提取域名
│   │   │   │   ├── content_hash()          — SHA256 前16位 hex
│   │   │   │   ├── is_valid_url()          — 校验 http/https scheme
│   │   │   │   ├── is_page_url()           — 过滤非页面资源（图片/CSS/JS/字体/文档）
│   │   │   │   ├── should_skip_url()       — 智能跳过（about/contact/login+分页2++查询参数>5）
│   │   │   │   └── is_honeypot_link()      — 蜜罐链检测（隐藏样式/aria-hidden/空文本/父元素）
│   │   │   │
│   │   │   ├── stealth.py                  — 反反爬虫基础组件
│   │   │   │   ├── UserAgentRotator
│   │   │   │   │   ├── __init__()          — 加载内置/自定义 UA 列表
│   │   │   │   │   ├── next()              — 随机返回一个 UA
│   │   │   │   │   └── for_domain()        — 同域名保持 UA 一致
│   │   │   │   ├── HeaderNormalizer
│   │   │   │   │   └── normalize()         — 补充 Accept/Accept-Language/Sec-Fetch 等浏览器头
│   │   │   │   ├── delay_with_jitter()     — 基础延迟+随机抖动
│   │   │   │   └── retry_with_backoff()    — 指数退避重试（可自定义重试条件）
│   │   │   │
│   │   │   ├── proxy.py                    — 代理管理器
│   │   │   │   └── ProxyManager
│   │   │   │       ├── __init__()          — 加载代理URL+轮换列表
│   │   │   │       ├── _pick()             — 选代理（同域保持一致）
│   │   │   │       ├── _parse_proxy()      — 解析代理URL→httpx/Playwright 格式
│   │   │   │       ├── for_httpx()         — 返回 httpx 代理配置
│   │   │   │       └── for_playwright()    — 返回 Playwright 代理配置
│   │   │   │
│   │   │   ├── session.py                  — Cookie/Session 持久化
│   │   │   │   └── SessionStore
│   │   │   │       ├── __init__()          — 设置存储目录
│   │   │   │       ├── save()              — 按域名保存 cookies+localStorage JSON
│   │   │   │       ├── load()              — 加载域名 session JSON
│   │   │   │       ├── load_cookies()      — 仅加载 cookies 列表
│   │   │   │       ├── load_storage_state()— 返回 Playwright storage_state 格式
│   │   │   │       ├── delete()            — 删除域名 session 文件
│   │   │   │       └── extract_cookies_from_httpx() — 从 httpx Response 解析 Set-Cookie
│   │   │   │
│   │   │   ├── captcha.py                  — CAPTCHA 检测与识别
│   │   │   │   ├── CaptchaType             — 枚举：recaptcha_v2/v3, hcaptcha, cloudflare, image
│   │   │   │   ├── CaptchaDetector
│   │   │   │   │   ├── detect()            — 检测页面验证码类型（正则+BeautifulSoup）
│   │   │   │   │   ├── _extract_recaptcha_info() — 提取 reCAPTCHA sitekey+版本
│   │   │   │   │   ├── _extract_sitekey()  — 从属性或 script 中提取 sitekey
│   │   │   │   │   ├── _extract_attr()     — 提取标签属性（按正则匹配）
│   │   │   │   │   └── _extract_image_captcha() — 提取图片验证码 URL+input name
│   │   │   │   ├── CaptchaSolver
│   │   │   │   │   ├── __init__()          — 设置 2captcha API key+超时
│   │   │   │   │   ├── solve_recaptcha_v2()— 识别 reCAPTCHA v2 → token
│   │   │   │   │   ├── solve_recaptcha_v3()— 识别 reCAPTCHA v3 → token
│   │   │   │   │   ├── solve_hcaptcha()    — 识别 hCaptcha → token
│   │   │   │   │   ├── solve_image_captcha() — 下载图片→base64→识别→文本
│   │   │   │   │   └── _solve()            — 通用2captcha流程：createTask→轮询getTaskResult
│   │   │   │   └── needs_captcha_solve()   — 快捷方法：403/503→Cloudflare，否则detect
│   │   │   │
│   │   │   ├── credentials.py              — 登录凭据管理
│   │   │   │   └── CredentialManager
│   │   │   │       ├── __init__()          — 设置 profiles 目录
│   │   │   │       ├── list_profiles()     — 列出所有 .profile.json 文件
│   │   │   │       ├── load()              — 加载配置+${ENV_VAR} 环境变量替换
│   │   │   │       ├── save()              — 保存配置 JSON
│   │   │   │       ├── delete()            — 删除配置 JSON
│   │   │   │       └── _resolve_env_vars() — 递归替换 ${VAR} 为环境变量值
│   │   │   │
│   │   │   └── login.py                    — 登录引擎
│   │   │       └── LoginEngine
│   │   │           ├── __init__()          — 初始化凭据管理器+SessionStore
│   │   │           ├── manual_login()      — 启动可见浏览器到登录页，等待用户手动登录
│   │   │           ├── complete_manual_login() — 保存 cookies+storage→关闭浏览器
│   │   │           ├── cancel_manual_login()   — 取消手动登录，关闭浏览器
│   │   │           ├── programmatic_login()— 自动表单填充登录（含 CAPTCHA 检测+人类化输入延迟）
│   │   │           ├── _detect_captcha_on_page() — 检测页面验证码
│   │   │           └── list_active_sessions()   — 列出活跃手动登录会话
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py                 — 空
│   │   │   └── schemas.py                  — 数据模型定义（Pydantic v2）
│   │   │       ├── TaskStatus              — 枚举：queued/running/completed/failed/stopped
│   │   │       ├── AntiCrawlConfig         — 单任务反反爬虫配置（覆盖全局settings）
│   │   │       ├── TaskCreate              — 创建任务请求体（含验证：深度1-20，页数1-500）
│   │   │       ├── TaskSummary             — 任务列表摘要
│   │   │       ├── ExtractedRecord         — 提取记录：source_url + data
│   │   │       ├── ContentChange           — 内容变更记录
│   │   │       ├── DataInsight             — 数据洞察：类型+图表类型+标题+ECharts数据+描述
│   │   │       ├── UrlTrackingInfo         — URL 追踪信息
│   │   │       ├── TaskDetail              — 任务完整详情（含results/insights/changes/group）
│   │   │       ├── PageData                — 抓取页面数据
│   │   │       ├── LinkInfo                — 链接信息：url+text+depth
│   │   │       ├── LinksResult             — 链接提取结果（站内/站外）
│   │   │       ├── FetchResult             — 抓取结果
│   │   │       ├── ExtractResult           — 提取结果
│   │   │       ├── DecideResult            — LLM 决策结果
│   │   │       ├── ProgressEvent           — WebSocket 进度事件
│   │   │       ├── new_task_id()           — 生成16位 hex UUID
│   │   │       └── now_iso()               — 当前 UTC 时间 ISO 格式
│   │   │
│   │   └── storage/
│   │       ├── __init__.py                 — 空
│   │       └── database.py                 — SQLite 数据持久化（aiosqlite）
│   │           ├── get_db()                — 获取 aiosqlite 连接（WAL模式）
│   │           ├── init_db()               — 建表+自动添加新列（tasks/crawled_pages/url_tracking/content_changes）
│   │           ├── insert_task()           — 插入任务（INSERT OR IGNORE）
│   │           ├── get_all_tasks()         — 获取所有任务摘要（按创建时间倒序）
│   │           ├── get_task()              — 获取单个任务完整行
│   │           ├── get_tasks_by_group()    — 按 task_group_id 获取同组任务
│   │           ├── update_task_status()    — 动态更新任务状态+可选字段
│   │           ├── save_task_results()     — 保存 results JSON
│   │           ├── save_task_insights()    — 保存 insights JSON
│   │           ├── update_schedule_next_run() — 更新定时任务下次执行时间
│   │           ├── get_due_recurring_tasks()  — 查询到期定时任务
│   │           ├── insert_crawled_page()   — 记录已抓取页面
│   │           ├── upsert_url_tracking()   — 插入/更新URL追踪（返回是否变化）
│   │           ├── insert_content_change() — 记录内容变更
│   │           ├── get_content_changes()   — 查询变更历史（可按 task_group/url 筛选）
│   │           └── get_url_tracking_stats()— 查询变更统计排行（Top 50）
│   │
│   ├── test_crawl.py                       — 快速爬取测试
│   │   ├── main()                          — 异步入口：初始化DB→创建Agent→爬取books.toscrape.com→保存结果
│   │   └── on_progress()                   — 事件回调：打印进度/页面/数据/完成/错误
│   │
│   └── test_e2e.py                         — 端到端 API 测试
│       └── test_api()                      — 5个测试：创建任务→轮询完成→检查洞察→定时任务→追踪API→调度修改→列表
│
└── frontend/
    ├── index.html                          — HTML 入口：<div id="root"> + /src/main.tsx
    ├── tsconfig.json                       — TypeScript 配置（ES2020, react-jsx, strict）
    ├── vite.config.ts                      — Vite 配置
    │   └── defineConfig()                  — React 插件 + 端口5173 + /api→localhost:8000 代理 + /ws WebSocket 代理
    │
    └── src/
        ├── main.tsx                         — React 入口
        │   └── (root render)               — createRoot+StrictMode 渲染 <App />
        │
        ├── App.tsx                          — 路由与布局
        │   └── App()                       — ConfigProvider(中文+主题) → BrowserRouter → Layout(Header+Content) → Routes(/, /tasks/new, /tasks/:taskId)
        │
        ├── vite-env.d.ts                   — Vite 客户端类型引用
        │
        ├── types/
        │   └── index.ts                     — TypeScript 类型定义
        │       ├── TaskStatus              — 联合类型：queued|running|completed|failed|stopped
        │       ├── TaskSummary             — 任务列表项
        │       ├── ExtractedRecord         — 提取记录
        │       ├── DataInsight             — 数据洞察
        │       ├── GroupTask               — 同组任务
        │       ├── TaskDetail              — 任务详情
        │       ├── ProgressEvent           — WebSocket 进度事件
        │       ├── TaskCreateInput         — 创建任务表单输入
        │       ├── ContentChange           — 内容变更
        │       └── TrackingStat            — URL 变更统计
        │
        ├── api/
        │   └── client.ts                    — HTTP/WS API 客户端
        │       ├── request()               — 通用 fetch 封装（JSON 请求/响应 + 错误处理）
        │       ├── api.createTask()        — POST /api/tasks
        │       ├── api.listTasks()         — GET /api/tasks
        │       ├── api.getTask()           — GET /api/tasks/{id}
        │       ├── api.deleteTask()        — DELETE /api/tasks/{id}
        │       ├── api.updateSchedule()    — PUT /api/tasks/{id}/schedule
        │       ├── api.cancelSchedule()    — DELETE /api/tasks/{id}/schedule
        │       ├── api.getChanges()        — GET /api/tasks/tracking/changes
        │       ├── api.getTrackingStats()  — GET /api/tasks/tracking/stats
        │       └── createWsUrl()           — 构建 WebSocket URL（自动判断 ws/wss）
        │
        ├── hooks/
        │   └── useWebSocket.ts              — WebSocket 连接 Hook
        │       └── useWebSocket()          — 管理 WS 连接：connect→onopen→onmessage→onclose(5s重连)→onerror；返回 lastMessage/connected/insights/changes
        │
        ├── components/
        │   ├── TaskCard.tsx                 — 任务摘要卡片
        │   │   └── TaskCard()              — 显示状态Tag+种子URL+抓取/发现/结果统计+运行中进度条
        │   │
        │   ├── DataTable.tsx                — 动态列数据表格
        │   │   └── DataTable()             — 从数据推断列→动态生成 antd Table（来源URL列+数据列，分页20条）
        │   │
        │   ├── CrawlProgress.tsx            — 爬取进度组件
        │   │   └── CrawlProgress()         — 进度条 + Statistic(已抓取/已发现/已提取)
        │   │
        │   ├── InsightCharts.tsx            — 数据洞察图表
        │   │   └── InsightCharts()         — 遍历insights→渲染ECharts（bar/line/pie/scatter）+ 描述文字
        │   │
        │   └── ChangeTrendChart.tsx         — 变更趋势图表
        │       └── ChangeTrendChart()       — 变更频率折线图+URL变更排行柱状图+变更记录列表
        │
        └── pages/
            ├── Dashboard.tsx                — 任务列表仪表盘
            │   └── Dashboard()
            │       ├── fetchTasks()         — 调用 API 获取任务列表
            │       └── (effect)             — 每5秒轮询 fetchTasks；渲染任务卡片列表或空状态
            │
            ├── CreateTask.tsx               — 创建任务表单
            │   └── CreateTask()
            │       ├── onFinish()           — 提交表单→API创建任务→跳转详情
            │       └── (render)             — 表单：种子URL+数据描述+深度+页数+JS渲染开关+增量监控配置
            │
            └── TaskDetail.tsx               — 任务详情页
                └── TaskDetail()
                    ├── fetchTask()          — 获取任务详情+结果+洞察
                    ├── fetchTrackingData()  — 获取变更历史+统计
                    ├── handleDelete()       — 停止任务并返回首页
                    ├── (ws effects×4)       — WebSocket 实时更新：进度/数据/洞察/变更
                    └── (render)             — 3个Tab：爬取结果（描述列表+进度+DataTable） / 数据洞察 / 变更历史
```

---

## 项目概览

基于 **FastAPI + LangChain + Playwright + React** 的通用智能爬虫 Agent 系统。后端使用 LLM 驱动的 Agent 循环（抓取→提取→决策→引导），支持静态/JS双通道抓取、CAPTCHA 识别、反反爬虫（UA轮换/代理/蜜罐检测）、定时监控+内容变更追踪、数据洞察自动生成；前端使用 Ant Design + ECharts 提供任务管理、实时进度、数据表格和可视化图表。前后端通过 REST API + WebSocket 通信，总计 **约 30 个源文件、100+ 个函数/方法**。
