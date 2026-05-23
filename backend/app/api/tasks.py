from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.agent.crawler_agent import CrawlerAgent
from app.api.websocket import manager
from app.config import settings
from app.models.schemas import (
    TaskCreate,
    TaskStatus,
    new_task_id,
    now_iso,
)
from app.storage.database import (
    get_all_tasks,
    get_content_changes,
    get_db,
    get_task,
    get_tasks_by_group,
    get_url_tracking_stats,
    insert_task,
    save_task_insights,
    save_task_results,
    update_task_status,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_running_agents: dict[str, CrawlerAgent] = {}


@router.post("", status_code=201)
async def create_task(body: TaskCreate) -> dict[str, Any]:
    """创建新的爬取任务"""
    task_id = new_task_id()
    now = now_iso()

    schedule_next_run = None
    task_group_id = None
    #如果是定时任务，则设置下一次运行时间为当前时间，并将任务分组 ID 设置为自身 ID
    if body.recurring_interval_minutes > 0:
        schedule_next_run = now
        task_group_id = task_id
    #插入任务记录到数据库
    await insert_task(
        task_id=task_id,
        seed_url=body.seed_url,
        data_description=body.data_description,
        max_depth=body.max_depth,
        max_pages=body.max_pages,
        use_javascript=body.use_javascript,
        created_at=now,
        recurring_interval_minutes=body.recurring_interval_minutes,
        schedule_next_run=schedule_next_run,
        task_group_id=task_group_id,
    )

    asyncio.create_task(
        _run_crawl(
            task_id=task_id,
            seed_url=body.seed_url,
            data_description=body.data_description,
            max_depth=body.max_depth,
            max_pages=body.max_pages,
            use_javascript=body.use_javascript,
            recurring_interval_minutes=body.recurring_interval_minutes,
            anti_crawl_config=body.anti_crawl,
        )
    )

    return {
        "task_id": task_id,
        "status": "queued",
        "created_at": now,
        "recurring_interval_minutes": body.recurring_interval_minutes,
    }


@router.get("")
async def list_tasks() -> list[dict[str, Any]]:
    """获取所有任务列表"""
    rows = await get_all_tasks()
    return [
        {
            "task_id": r["id"],
            "seed_url": r["seed_url"],
            "status": r["status"],
            "pages_crawled": r["pages_crawled"],
            "pages_discovered": r["pages_discovered"],
            "result_count": r["result_count"],
            "created_at": r["created_at"],
            "recurring_interval_minutes": r.get("recurring_interval_minutes", 0),
            "task_group_id": r.get("task_group_id"),
        }
        for r in rows
    ]


@router.get("/{task_id}")
async def get_task_detail(task_id: str) -> dict[str, Any]:
    """获取任务详情"""
    row = await get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")

    results = []
    if row["results_json"]:
        try:
            results = json.loads(row["results_json"])
        except json.JSONDecodeError:
            pass

    insights = []
    if row.get("insights_json"):
        try:
            insights = json.loads(row["insights_json"])
        except json.JSONDecodeError:
            pass

    group_tasks = []
    if row.get("task_group_id"):
        group_rows = await get_tasks_by_group(row["task_group_id"])
        group_tasks = [
            {
                "task_id": t["id"],
                "status": t["status"],
                "created_at": t["created_at"],
                "result_count": t["result_count"],
                "changes_detected": t.get("changes_detected", 0),
            }
            for t in group_rows
        ]

    return {
        "task_id": row["id"],
        "seed_url": row["seed_url"],
        "data_description": row["data_description"],
        "max_depth": row["max_depth"],
        "max_pages": row["max_pages"],
        "use_javascript": bool(row["use_javascript"]),
        "status": row["status"],
        "pages_crawled": row["pages_crawled"],
        "pages_discovered": row["pages_discovered"],
        "result_count": row["result_count"],
        "results": results,
        "insights": insights,
        "changes_detected": row.get("changes_detected", 0),
        "recurring_interval_minutes": row.get("recurring_interval_minutes", 0),
        "task_group_id": row.get("task_group_id"),
        "group_tasks": group_tasks,
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


@router.delete("/{task_id}")
async def delete_task(task_id: str) -> dict[str, str]:
    """停止并删除任务"""
    row = await get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")

    if row["status"] == TaskStatus.running.value:
        agent = _running_agents.get(task_id)
        if agent:
            agent.stop()
            await asyncio.sleep(0.5)
            _running_agents.pop(task_id, None)

    await update_task_status(task_id, TaskStatus.stopped.value)
    return {"task_id": task_id, "status": "stopped"}

@router.put("/{task_id}/schedule")
async def update_schedule(
    task_id: str,
    recurring_interval_minutes: int = Query(..., ge=0, le=10080),
) -> dict[str, Any]:
    """修改定时配置"""
    row = await get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")

    db = await get_db()
    try:
        if recurring_interval_minutes > 0:
            next_run = now_iso()
            await db.execute(
                "UPDATE tasks SET recurring_interval_minutes = ?, schedule_next_run = ? WHERE id = ?",
                (recurring_interval_minutes, next_run, task_id),
            )
        else:
            await db.execute(
                "UPDATE tasks SET recurring_interval_minutes = 0, schedule_next_run = NULL WHERE id = ?",
                (task_id,),
            )
        await db.commit()
    finally:
        await db.close()

    return {"task_id": task_id, "recurring_interval_minutes": recurring_interval_minutes}


@router.delete("/{task_id}/schedule")
async def cancel_schedule(task_id: str) -> dict[str, str]:
    """取消定时配置"""
    row = await get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")

    db = await get_db()
    try:
        await db.execute(
            "UPDATE tasks SET recurring_interval_minutes = 0, schedule_next_run = NULL WHERE id = ?",
            (task_id,),
        )
        await db.commit()
    finally:
        await db.close()

    return {"task_id": task_id, "status": "schedule_cancelled"}


# ─── 变更追踪 API ──────────────────────────────────────────

@router.get("/tracking/changes")
async def list_content_changes(
    task_group_id: str | None = Query(None),
    url: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """获取内容变更历史"""
    return await get_content_changes(task_group_id=task_group_id, url=url, limit=limit)


@router.get("/tracking/stats")
async def list_tracking_stats(
    task_group_id: str | None = Query(None),
) -> list[dict[str, Any]]:
    """获取 URL 变更统计"""
    return await get_url_tracking_stats(task_group_id or "")


# ─── 后台任务执行 ──────────────────────────────────────────

async def _run_crawl(
    task_id: str,
    seed_url: str,
    data_description: str,
    max_depth: int,
    max_pages: int,
    use_javascript: bool,
    recurring_interval_minutes: int = 0,
    task_group_id: str | None = None,
    anti_crawl_config=None,
) -> None:
    """后台执行爬取任务"""
    now = now_iso()

    # 确保任务行存在（调度器触发时可能尚未插入）
    await insert_task(
        task_id=task_id,
        seed_url=seed_url,
        data_description=data_description,
        max_depth=max_depth,
        max_pages=max_pages,
        use_javascript=use_javascript,
        created_at=now,
        recurring_interval_minutes=recurring_interval_minutes,
        task_group_id=task_group_id,
        schedule_next_run=None,
    )

    await update_task_status(task_id, TaskStatus.running.value, started_at=now)

    task_data_dir = Path(settings.task_data_dir) / task_id

    async def progress_callback(event: dict[str, Any]) -> None:
        await manager.broadcast(task_id, event)
        if event["type"] in ("progress", "page_crawled", "data_extracted"):
            await update_task_status(
                task_id,
                TaskStatus.running.value,
                pages_crawled=event.get("pages_crawled"),
                pages_discovered=event.get("pages_discovered"),
            )

    agent = CrawlerAgent(
        seed_url=seed_url,
        data_description=data_description,
        max_depth=max_depth,
        max_pages=max_pages,
        use_javascript=use_javascript,
        task_data_dir=task_data_dir,
        recurring_interval_minutes=recurring_interval_minutes,
        task_id=task_id,
        anti_crawl_config=anti_crawl_config,
    )
    _running_agents[task_id] = agent

    try:
        results = await agent.run(progress_callback=progress_callback)

        results_json = json.dumps(results, ensure_ascii=False)
        await save_task_results(task_id, results_json)

        if agent._last_insights:
            await save_task_insights(
                task_id, json.dumps(agent._last_insights, ensure_ascii=False)
            )#如果任务成功完成，则更新任务状态为 completed，并记录爬取的页面数、发现的页面数、结果数量和变更检测数量

        await update_task_status(
            task_id,
            TaskStatus.completed.value,
            pages_crawled=agent.pages_crawled,
            pages_discovered=agent.pages_crawled + agent.frontier.pending_count(),
            result_count=len(results),
            changes_detected=agent.changes_detected,
            completed_at=now_iso(),
        )
    except Exception as e:
        await update_task_status(
            task_id,
            TaskStatus.failed.value,
            error_message=str(e),
            completed_at=now_iso(),
        )
    finally:
        _running_agents.pop(task_id, None)
