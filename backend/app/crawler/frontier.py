from __future__ import annotations

from collections import deque
from urllib.parse import urlparse


class Frontier:
    """URL 队列管理器：管理待抓取 URL、已访问集合、深度跟踪"""

    def __init__(self, max_queue_size: int = 10000):
        self._queue: deque[tuple[str, int]] = deque()  # (url, depth)
        self._visited: set[str] = set()
        self._queued_urls: set[str] = set()  # 快速去重
        self._max_queue_size = max_queue_size
        self._domain_hits: dict[str, int] = {}

    def enqueue(self, url: str, depth: int) -> bool:
        """入队一个 URL，返回是否成功（去重 + 容量限制）"""
        if url in self._visited or url in self._queued_urls:
            return False
        if len(self._queue) >= self._max_queue_size:
            return False
        self._queue.append((url, depth))
        self._queued_urls.add(url)
        return True

    def enqueue_batch(self, urls: list[tuple[str, int]]) -> int:
        """批量入队，返回成功入队数量"""
        count = 0
        for url, depth in urls:
            if self.enqueue(url, depth):
                count += 1
        return count

    def dequeue(self) -> tuple[str, int] | None:
        """出队一个 URL"""
        if not self._queue:
            return None
        url, depth = self._queue.popleft()
        self._queued_urls.discard(url)
        self._visited.add(url)
        domain = urlparse(url).netloc
        self._domain_hits[domain] = self._domain_hits.get(domain, 0) + 1
        return url, depth

    def mark_visited(self, url: str) -> None:
        self._visited.add(url)
        self._queued_urls.discard(url)

    def is_visited(self, url: str) -> bool:
        return url in self._visited

    def has_pending(self) -> bool:
        return len(self._queue) > 0

    def pending_count(self) -> int:
        return len(self._queue)

    def visited_count(self) -> int:
        return len(self._visited)

    def get_pending_urls(self) -> list[tuple[str, int]]:
        """获取所有待抓取 URL 列表（供 LLM 决策）"""
        return list(self._queue)

    def remove_urls(self, urls: set[str]) -> None:
        """从队列中移除指定 URL（LLM 决定跳过）"""
        new_queue: deque[tuple[str, int]] = deque()
        for url, depth in self._queue:
            if url not in urls:
                new_queue.append((url, depth))
            else:
                self._queued_urls.discard(url)
        self._queue = new_queue

    def remove_by_domain(self, domain: str) -> int:
        """移除队列中指定域名的所有 URL，返回移除数量"""
        removed = 0
        new_queue: deque[tuple[str, int]] = deque()
        for url, depth in self._queue:
            if urlparse(url).netloc == domain:
                self._queued_urls.discard(url)
                removed += 1
            else:
                new_queue.append((url, depth))
        self._queue = new_queue
        return removed
