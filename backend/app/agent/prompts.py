CRAWLER_SYSTEM_PROMPT = """你是一个智能爬虫 Agent。你的目标是根据用户的数据需求，浏览网站并提取结构化数据。

## 可用工具
- **fetch_page**: 抓取并提取页面文本。如果页面是 JavaScript 渲染的，设置 use_javascript=true。
- **extract_links**: 从页面中获取所有链接，区分站内链接和外部链接。
- **extract_data**: 根据页面内容和用户对目标数据的描述，提取结构化数据（JSON 格式）。
- **decide_next_urls**: 根据当前进度、待抓取 URL 列表和爬取约束，选择下一步要抓取的 URL。

## 工作策略
1. 先抓取种子 URL，理解网站结构
2. 每次抓取页面后，先提取其中的目标数据
3. 然后提取链接来扩展待抓取队列
4. 优先抓取链接文本或 URL 路径暗示包含目标数据的页面
5. 避免抓取高度重复的页面（如分页列表的后续页）
6. 严格遵守深度和页面数量限制

## 约束
- 同一域名请求间隔不少于 2 秒
- 忽略非页面资源（图片、CSS、JS、PDF 等）
- 发现重复内容时跳过后续同类页面
"""

EXTRACTION_PROMPT_TEMPLATE = """从以下网页内容中提取目标数据。

## 目标数据描述
{data_description}

## 页面 URL
{page_url}

## 页面标题
{page_title}

## 页面内容
{page_content}

请以 JSON 对象格式返回，包含 "items" 数组字段。如果没有找到相关数据，返回 {{"items": []}}。
只返回 JSON，不要包含其他文字。

示例格式：
{{"items": [{{"字段1": "值1", "字段2": "值2"}}, {{"字段1": "值3", "字段2": "值4"}}]}}
"""

DECISION_PROMPT_TEMPLATE = """你正在爬取网站以提取以下数据："{data_description}"

## 当前进度
- 已抓取页数：{pages_crawled} / {max_pages}
- 最大深度：{max_depth}
- 已提取记录数：{results_count}

## 待抓取 URL 列表
{unvisited_links}

请选择下一步要抓取的 URL。优先选择：
1. URL 路径或链接文本暗示包含目标数据的页面
2. 深度较浅的页面优先
3. 避免选择高度相似的 URL（如分页 /page/1, /page/2），选择 1-2 个代表即可

以 JSON 格式返回：
{{"next_urls": ["url1", "url2", ...], "skip_urls": ["url3", ...], "reason": "选择理由"}}
只返回 JSON，不要包含其他文字。"""

STEER_PROMPT_TEMPLATE = """你正在爬取网站以提取以下数据："{data_description}"

## 当前进度
- 已抓取页数：{pages_crawled} / {max_pages}
- 队列中待抓取 URL 数：{pending_count}

## 待筛选 URL 列表（从队列中抽样）
{sample_urls}

请判断每个 URL 是否值得抓取。优先保留：
1. URL 路径暗示包含目标数据的页面（如产品详情、列表页）
2. 路径结构简洁、内容密度高的页面

跳过：
1. 明显不相关的页面（关于我们、联系方式、登录注册、法律条款等）
2. URL 结构高度重复的页面（分页 /page/2+、排序变体、过滤参数等）

以 JSON 格式返回：
{{"keep_urls": ["url1", "url2", ...], "skip_urls": ["url3", ...], "reason": "筛选理由"}}
只返回 JSON，不要包含其他文字。"""

INSIGHTS_PROMPT_TEMPLATE = """你是一个数据分析师。以下是爬取提取的结构化数据，请分析并生成可视化洞察。

## 数据描述
{data_description}

## 爬取数据（共 {record_count} 条，展示前 {sample_size} 条）
{sample_data}

## 要求
生成 2-4 个可视化图表配置，每个包含：
- insight_type: distribution(分布) / trend(趋势) / comparison(对比) / anomaly(异常)
- chart_type: bar(柱状图) / line(折线图) / pie(饼图) / scatter(散点图)
- title: 图表标题
- data: 包含 "categories"（字符串数组）和 "series"（对象数组，每项有 name 和 values 数值数组）
- description: 一句话解读

返回 JSON 数组，只返回 JSON：
[{{"insight_type": "distribution", "chart_type": "bar", "title": "...", "data": {{"categories": ["A","B"], "series": [{{"name": "数量", "values": [10,20]}}]}}, "description": "..."}}]"""

CHANGE_SUMMARY_PROMPT = """对比以下网页内容的前后变化，用一句话描述变化（如"价格从 £51.77 变为 £49.99"、"新增了 3 本书"、"库存状态从 In stock 变为 Out of stock"）。

## 之前的页面内容（前 1000 字符）
{old_content}

## 当前的页面内容（前 1000 字符）
{new_content}

只返回一句话描述，不要包含其他文字。"""

BATCH_EXTRACTION_PROMPT_TEMPLATE = """从以下多个网页中提取目标数据。

## 目标数据描述
{data_description}

## 页面列表
{page_contents}

请以 JSON 对象格式返回从所有页面提取的数据，包含 "items" 数组，每条记录必须包含 "source_url" 字段。
只返回 JSON，不要包含其他文字。

示例格式：
{{"items": [{{"source_url": "https://...", "字段1": "值1"}}]}}
"""