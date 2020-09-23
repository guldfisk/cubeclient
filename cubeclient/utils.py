from __future__ import annotations

import typing as t
import threading


K = t.TypeVar('K')
V = t.TypeVar('V')


class EventWithValue(threading.Event, t.Generic[K, V]):

    def __init__(self, task_awaiter: TaskAwaiter, key: K) -> None:
        super().__init__()
        self._task_awaiter = task_awaiter
        self._key = key
        self.value: t.Union[None, V, Exception] = None

    def set_value(self, value: t.Union[V, Exception]) -> None:
        self.value = value
        self._task_awaiter.del_key(self._key)
        super().set()

    def set(self) -> None:
        raise NotImplemented()


class TaskAwaiter(t.Generic[K, V]):

    def __init__(self):
        self._lock = threading.Lock()
        self._map: t.Dict[K, EventWithValue[K, V]] = {}

    def del_key(self, key: K) -> None:
        with self._lock:
            del self._map[key]

    def get_condition(self, key: K) -> t.Tuple[EventWithValue[V], bool]:
        with self._lock:
            try:
                return self._map[key], True
            except KeyError:
                self._map[key] = event = EventWithValue(self, key)
                return event, False
