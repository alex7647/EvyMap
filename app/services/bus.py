"""Шина событий для SSE. In-process реализация; для нескольких процессов заменить на Redis pub/sub
с тем же интерфейсом (subscribe / unsubscribe / publish)."""
import asyncio
from collections import defaultdict


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set] = defaultdict(set)

    def subscribe(self, key: str):
        item = (asyncio.get_running_loop(), asyncio.Queue(maxsize=20))
        self._subs[key].add(item)
        return item

    def unsubscribe(self, key: str, item) -> None:
        self._subs[key].discard(item)

    def publish(self, key: str, msg: dict) -> None:
        """Можно вызывать из любого потока (sync-эндпоинты FastAPI работают в threadpool)."""
        for loop, q in list(self._subs.get(key, ())):
            loop.call_soon_threadsafe(self._put, q, msg)

    @staticmethod
    def _put(q: asyncio.Queue, msg: dict) -> None:
        if q.full():
            q.get_nowait()
        q.put_nowait(msg)


bus = EventBus()
