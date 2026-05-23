"""后台定时调度器：轮询 DB 中到期的定时任务，触发新的爬取执行"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.storage.database import (
    get_due_recurring_tasks,
    get_task,
    update_schedule_next_run,
    clear_all_schedules,
)


class TaskScheduler:
    """轮询数据库，发现到期的定时任务并触发新执行"""

    POLL_INTERVAL = 30  # 轮询间隔（秒）

    def __init__(self):
        self._stopped = False
        self._task: asyncio.Task | None = None
        self._run_crawl = None  # 由外部注入
        self._first_tick = True  # 启动时跳过过期任务，避免集中触发

    def set_run_crawl(self, fn):
        self._run_crawl = fn

    async def start(self) -> None:
        self._stopped = False
        self._first_tick = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopped = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # 关闭时清除所有定时配置，防止下次启动自动触发
        await clear_all_schedules()

    async def _loop(self) -> None:
        while not self._stopped:
            try:
                now = datetime.now(timezone.utc)
                now_iso = now.isoformat()
                due_tasks = await get_due_recurring_tasks(now_iso)
                for task in due_tasks:
                    if not self._run_crawl or task["status"] == "running":
                        continue

                    # 启动后第一个周期：过期任务不立即执行，而是重排到下一个间隔
                    if self._first_tick:
                        minutes = task["recurring_interval_minutes"]
                        next_run = (now + timedelta(minutes=minutes)).isoformat()
                        await update_schedule_next_run(task["id"], next_run)
                        continue

                    asyncio.create_task(
                        self._run_crawl(
                            task_id=task["id"] + "_" + now_iso[:19].replace(":", "-"),
                            seed_url=task["seed_url"],
                            data_description=task["data_description"],
                            max_depth=task["max_depth"],
                            max_pages=task["max_pages"],
                            use_javascript=bool(task["use_javascript"]),
                            recurring_interval_minutes=task["recurring_interval_minutes"],
                            task_group_id=task.get("task_group_id") or task["id"],
                        )
                    )
                    # 更新下一次执行时间
                    minutes = task["recurring_interval_minutes"]
                    next_run = (now + timedelta(minutes=minutes)).isoformat()
                    await update_schedule_next_run(task["id"], next_run)
            except Exception:
                pass
            finally:
                self._first_tick = False
            await asyncio.sleep(self.POLL_INTERVAL)
