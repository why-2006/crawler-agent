# """快速测试爬虫 Agent — 爬取 books.toscrape.com（专用爬虫测试站点）"""
# import asyncio
# import json
# import sys
# from pathlib import Path
# from app.agent.crawler_agent import CrawlerAgent
# from app.storage.database import init_db

# # 修复 Windows GBK 编码问题
# sys.stdout.reconfigure(encoding="utf-8")


# async def main():
#     await init_db()

#     agent = CrawlerAgent(
#         seed_url="https://books.toscrape.com",
#         data_description="书名（title）、价格（price）、库存状态（availability）、评分（rating）",
#         max_depth=2,
#         max_pages=5,
#         use_javascript=False,
#         task_data_dir=Path("data/tasks/test"),
#     )

#     async def on_progress(event: dict):
#         t = event.get("type", "?")
#         if t == "progress":
#             print(f"[进度] {event.get('message', '')} (已抓取: {event.get('pages_crawled', 0)})")
#         elif t == "page_crawled":
#             print(f"[页面] {event.get('url', '?')}")
#         elif t == "data_extracted":
#             items = event.get("items", [])
#             print(f"[数据] 提取 {len(items)} 条记录")
#             for item in items:
#                 print(f"       {json.dumps(item, ensure_ascii=False)[:200]}")
#         elif t == "completed":
#             print(f"[完成] {event.get('message', '')}")
#         elif t == "error":
#             print(f"[错误] {event.get('message', '')}")

#     results = await agent.run(progress_callback=on_progress)

#     print(f"\n=== 爬取完成，共 {len(results)} 条结果 ===")
#     for i, r in enumerate(results[:10]):
#         print(f"{i+1}. 来源: {r['source_url']}")
#         print(f"   数据: {json.dumps(r['data'], ensure_ascii=False)}")

#     # 保存完整结果
#     Path("data/test_result.json").write_text(
#         json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
#     )
#     print("\n完整结果已保存到 data/test_result.json")


# asyncio.run(main())
