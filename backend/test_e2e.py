# """E2E test for crawler with monitoring + insights"""
# import asyncio
# import json
# from app.storage.database import init_db

# async def test_api():
#     import httpx

#     base = "http://localhost:8000/api"

#     async with httpx.AsyncClient(timeout=120) as client:
#         # 1. Create a non-recurring task
#         print("=" * 50)
#         print("TEST 1: Create non-recurring task")
#         resp = await client.post(f"{base}/tasks", json={
#             "seed_url": "https://books.toscrape.com",
#             "data_description": "book titles, prices, star ratings, stock status",
#             "max_depth": 2,
#             "max_pages": 5,
#             "use_javascript": False,
#             "recurring_interval_minutes": 0,
#         })
#         print(f"  Status: {resp.status_code}")
#         task1 = resp.json()
#         print(f"  Task ID: {task1.get('task_id')}")
#         print(f"  Status: {task1.get('status')}")
#         task1_id = task1["task_id"]

#         # 2. Wait for completion (poll)
#         print("\n  Waiting for completion...")
#         for i in range(60):
#             await asyncio.sleep(2)
#             resp = await client.get(f"{base}/tasks/{task1_id}")
#             data = resp.json()
#             status = data.get("status", "")
#             print(f"    [{i+1}] pages={data['pages_crawled']}/{data['pages_discovered']} results={data['result_count']} status={status}")
#             if status in ("completed", "failed"):
#                 break

#         # 3. Check insights
#         resp = await client.get(f"{base}/tasks/{task1_id}")
#         task1_detail = resp.json()
#         insights = task1_detail.get("insights", [])
#         print(f"\n  Insights generated: {len(insights)}")
#         for ins in insights:
#             title = ins.get('title', '')
#             print(f"    - [{ins.get('chart_type')}] {title}")

#         # 4. Check results
#         results = task1_detail.get("results", [])
#         print(f"  Total results: {len(results)}")
#         if results:
#             sample = json.dumps(results[0], ensure_ascii=True)[:200]
#             print(f"  Sample: {sample}")

#         # 5. Create a recurring monitoring task (short interval)
#         print("\n" + "=" * 50)
#         print("TEST 2: Create recurring monitoring task")
#         resp = await client.post(f"{base}/tasks", json={
#             "seed_url": "https://books.toscrape.com",
#             "data_description": "book titles, prices",
#             "max_depth": 1,
#             "max_pages": 3,
#             "use_javascript": False,
#             "recurring_interval_minutes": 5,
#         })
#         print(f"  Status: {resp.status_code}")
#         task2 = resp.json()
#         print(f"  Task ID: {task2.get('task_id')}")
#         print(f"  Status: {task2.get('status')}")
#         task2_id = task2["task_id"]

#         # 6. Get detail to check monitoring fields
#         resp = await client.get(f"{base}/tasks/{task2_id}")
#         task2_detail = resp.json()
#         print(f"  recurring_interval: {task2_detail.get('recurring_interval_minutes')}")
#         print(f"  task_group_id: {task2_detail.get('task_group_id')}")
#         print(f"  group_tasks: {len(task2_detail.get('group_tasks', []))}")

#         # 7. Test tracking endpoints
#         print("\n" + "=" * 50)
#         print("TEST 3: Tracking API endpoints")
#         resp = await client.get(f"{base}/tasks/tracking/changes?limit=10")
#         print(f"  GET /tracking/changes: {resp.status_code}, count={len(resp.json())}")

#         resp = await client.get(f"{base}/tasks/tracking/stats")
#         print(f"  GET /tracking/stats: {resp.status_code}, count={len(resp.json())}")

#         # 8. Test schedule update
#         print("\n" + "=" * 50)
#         print("TEST 4: Schedule update")
#         resp = await client.put(f"{base}/tasks/{task1_id}/schedule?recurring_interval_minutes=30")
#         print(f"  PUT schedule: {resp.status_code}, body={resp.json()}")

#         # 9. Test schedule cancel
#         resp = await client.delete(f"{base}/tasks/{task1_id}/schedule")
#         print(f"  DELETE schedule: {resp.status_code}, body={resp.json()}")

#         # 10. List tasks
#         print("\n" + "=" * 50)
#         print("TEST 5: List tasks")
#         resp = await client.get(f"{base}/tasks")
#         tasks = resp.json()
#         print(f"  Total tasks: {len(tasks)}")
#         for t in tasks:
#             print(f"    {t['task_id'][:12]}... status={t['status']} recurring={t.get('recurring_interval_minutes',0)}")

#         print("\n" + "=" * 50)
#         print("ALL TESTS COMPLETE")

# if __name__ == "__main__":
#     asyncio.run(test_api())
