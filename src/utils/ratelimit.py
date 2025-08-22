from __future__ import annotations
import time
from collections import defaultdict, deque


class WindowRateLimiter:
    """
    Простой in-memory лимитер: разрешает не более N запросов (per_chat)
    в скользящем окне из `interval_sec` секунд.
    """

    def __init__(self, per_chat: int, interval_sec: int):
        self.per_chat = max(1, per_chat)
        self.interval = max(1, interval_sec)
        self.hits: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, key: int) -> bool:
        now = time.time()
        dq = self.hits[key]
        # вычищаем события старше окна
        while dq and now - dq[0] > self.interval:
            dq.popleft()
        if len(dq) >= self.per_chat:
            return False
        dq.append(now)
        return True

