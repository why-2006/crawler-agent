import json
import os
from pathlib import Path

import aiosqlite

from app.config import settings


DB_PATH = Path(settings.database_path)


async def get_db() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                seed_url TEXT NOT NULL,
                data_description TEXT NOT NULL,
                max_depth INTEGER DEFAULT 3,
                max_pages INTEGER DEFAULT 50,
                use_javascript INTEGER DEFAULT 0,
                status TEXT DEFAULT 'queued',
                pages_crawled INTEGER DEFAULT 0,
                pages_discovered INTEGER DEFAULT 0,
                result_count INTEGER DEFAULT 0,
                results_json TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS crawled_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                url TEXT NOT NULL,
                depth INTEGER,
                status TEXT,
                content_hash TEXT,
                extracted_count INTEGER DEFAULT 0,
                fetched_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)
        # 新增：URL 内容追踪表（跨任务持久化）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS url_tracking (
                url TEXT PRIMARY KEY,
                seed_url TEXT NOT NULL,
                last_content_hash TEXT NOT NULL,
                last_seen_task_id TEXT,
                last_seen_at TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                change_count INTEGER DEFAULT 0,
                last_changed_at TEXT
            )
        """)
        # 新增：变更历史表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS content_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                url TEXT NOT NULL,
                old_content_hash TEXT,
                new_content_hash TEXT NOT NULL,
                change_summary TEXT,
                detected_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)

        # 新增 tasks 表列（SQLite 不支持 IF NOT EXISTS，用 try/except）
        new_columns = [
            "ALTER TABLE tasks ADD COLUMN recurring_interval_minutes INTEGER DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN schedule_next_run TEXT",
            "ALTER TABLE tasks ADD COLUMN task_group_id TEXT",
            "ALTER TABLE tasks ADD COLUMN changes_detected INTEGER DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN insights_json TEXT",
        ]
        for sql in new_columns:
            try:
                await db.execute(sql)
            except aiosqlite.OperationalError:
                pass  # 列已存在

        await db.commit()
    finally:
        await db.close()


# ─── tasks CRUD ──────────────────────────────────────────────

async def insert_task(
    task_id: str,
    seed_url: str,
    data_description: str,
    max_depth: int,
    max_pages: int,
    use_javascript: bool,
    created_at: str,
    recurring_interval_minutes: int = 0,
    task_group_id: str | None = None,
    schedule_next_run: str | None = None,
) -> None:
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR IGNORE INTO tasks (id, seed_url, data_description, max_depth, max_pages,
               use_javascript, status, created_at, recurring_interval_minutes,
               task_group_id, schedule_next_run)
               VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
            (task_id, seed_url, data_description, max_depth, max_pages,
             int(use_javascript), created_at, recurring_interval_minutes,
             task_group_id, schedule_next_run),
        )
        await db.commit()
    finally:
        await db.close()


async def get_all_tasks() -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, seed_url, status, pages_crawled, pages_discovered, "
            "result_count, created_at, recurring_interval_minutes, task_group_id "
            "FROM tasks ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_task(task_id: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_tasks_by_group(task_group_id: str) -> list[dict]:
    """获取同一 task_group 下的所有任务（按时间排序）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE task_group_id = ? "
            "ORDER BY created_at ASC",
            (task_group_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def update_task_status(
    task_id: str,
    status: str,
    pages_crawled: int | None = None,
    pages_discovered: int | None = None,
    result_count: int | None = None,
    error_message: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    changes_detected: int | None = None,
) -> None:
    db = await get_db()
    try:
        parts = ["status = ?"]
        params: list = [status]
        if pages_crawled is not None:
            parts.append("pages_crawled = ?")
            params.append(pages_crawled)
        if pages_discovered is not None:
            parts.append("pages_discovered = ?")
            params.append(pages_discovered)
        if result_count is not None:
            parts.append("result_count = ?")
            params.append(result_count)
        if error_message is not None:
            parts.append("error_message = ?")
            params.append(error_message)
        if started_at is not None:
            parts.append("started_at = ?")
            params.append(started_at)
        if completed_at is not None:
            parts.append("completed_at = ?")
            params.append(completed_at)
        if changes_detected is not None:
            parts.append("changes_detected = ?")
            params.append(changes_detected)
        params.append(task_id)
        await db.execute(
            f"UPDATE tasks SET {', '.join(parts)} WHERE id = ?", params
        )
        await db.commit()
    finally:
        await db.close()


async def save_task_results(task_id: str, results_json: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE tasks SET results_json = ? WHERE id = ?",
            (results_json, task_id),
        )
        await db.commit()
    finally:
        await db.close()


async def save_task_insights(task_id: str, insights_json: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE tasks SET insights_json = ? WHERE id = ?",
            (insights_json, task_id),
        )
        await db.commit()
    finally:
        await db.close()


async def update_schedule_next_run(task_id: str, next_run: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "UPDATE tasks SET schedule_next_run = ? WHERE id = ?",
            (next_run, task_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_due_recurring_tasks(now: str) -> list[dict]:
    """获取所有应执行的定时任务（schedule_next_run <= now 且为定时任务）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE recurring_interval_minutes > 0 "
            "AND schedule_next_run IS NOT NULL "
            "AND schedule_next_run <= ? "
            "ORDER BY schedule_next_run ASC",
            (now,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def insert_crawled_page(
    task_id: str,
    url: str,
    depth: int,
    status: str,
    content_hash: str,
    extracted_count: int,
    fetched_at: str,
) -> None:
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO crawled_pages (task_id, url, depth, status, content_hash,
               extracted_count, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (task_id, url, depth, status, content_hash, extracted_count, fetched_at),
        )
        await db.commit()
    finally:
        await db.close()


# ─── URL 内容追踪 ────────────────────────────────────────────

async def upsert_url_tracking(
    url: str,
    seed_url: str,
    content_hash: str,
    task_id: str,
    now: str,
) -> tuple[bool, str | None]:
    """
    插入或更新 URL 追踪记录。
    返回 (是否变化, 旧hash)。
    """
    db = await get_db()
    try:
        existing = await db.execute(
            "SELECT last_content_hash, change_count FROM url_tracking WHERE url = ?",
            (url,),
        )
        row = await existing.fetchone()
        if row is None:
            await db.execute(
                """INSERT INTO url_tracking (url, seed_url, last_content_hash,
                   last_seen_task_id, last_seen_at, first_seen_at, change_count)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (url, seed_url, content_hash, task_id, now, now),
            )
            await db.commit()
            return False, None
        else:
            old_hash = row["last_content_hash"]
            if old_hash != content_hash:
                new_count = row["change_count"] + 1
                await db.execute(
                    """UPDATE url_tracking SET last_content_hash = ?,
                       last_seen_task_id = ?, last_seen_at = ?,
                       change_count = ?, last_changed_at = ?
                       WHERE url = ?""",
                    (content_hash, task_id, now, new_count, now, url),
                )
                await db.commit()
                return True, old_hash
            else:
                await db.execute(
                    "UPDATE url_tracking SET last_seen_task_id = ?, last_seen_at = ? WHERE url = ?",
                    (task_id, now, url),
                )
                await db.commit()
                return False, None
    finally:
        await db.close()


async def insert_content_change(
    task_id: str,
    url: str,
    old_content_hash: str | None,
    new_content_hash: str,
    change_summary: str | None,
    detected_at: str,
) -> None:
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO content_changes (task_id, url, old_content_hash,
               new_content_hash, change_summary, detected_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, url, old_content_hash, new_content_hash, change_summary, detected_at),
        )
        await db.commit()
    finally:
        await db.close()


async def get_content_changes(
    task_group_id: str | None = None,
    url: str | None = None,
    limit: int = 50,
) -> list[dict]:
    db = await get_db()
    try:
        conditions = []
        params: list = []
        if task_group_id:
            # 查询同一 task_group 下所有任务的变更
            conditions.append("cc.task_id IN (SELECT id FROM tasks WHERE task_group_id = ?)")
            params.append(task_group_id)
        if url:
            conditions.append("cc.url = ?")
            params.append(url)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)
        cursor = await db.execute(
            f"SELECT cc.*, t.task_group_id FROM content_changes cc "
            f"LEFT JOIN tasks t ON cc.task_id = t.id "
            f"{where} ORDER BY cc.detected_at DESC LIMIT ?",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_url_tracking_stats(task_group_id: str) -> list[dict]:
    """获取变更统计：每个 URL 的变更次数和时间"""
    db = await get_db()
    try:
        conditions = ["ut.change_count > 0"]
        params: list = []
        if task_group_id:
            conditions.append(
                "ut.last_seen_task_id IN (SELECT id FROM tasks WHERE task_group_id = ?)"
            )
            params.append(task_group_id)
        where = "WHERE " + " AND ".join(conditions)
        params.append(50)
        cursor = await db.execute(
            f"SELECT ut.url, ut.change_count, ut.last_changed_at, ut.last_seen_at "
            f"FROM url_tracking ut "
            f"{where} ORDER BY ut.change_count DESC LIMIT ?",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def clear_all_schedules() -> None:
    """关闭程序时清除所有定时任务的调度配置，防止重启后自动触发"""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE tasks SET recurring_interval_minutes = 0, schedule_next_run = NULL "
            "WHERE recurring_interval_minutes > 0"
        )
        await db.commit()
    finally:
        await db.close()
