"""Bounded LRU cache for answers. Not functools.lru_cache: two endpoints share
one store, and responses report whether they were cached."""
from __future__ import annotations

from collections import OrderedDict
from typing import Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    def __init__(self, capacity: int = 256) -> None:
        if capacity <= 0:
            raise ValueError("LRUCache capacity must be positive")
        self.capacity = capacity
        self._store: "OrderedDict[K, V]" = OrderedDict()

    def get(self, key: K) -> Optional[V]:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def set(self, key: K, value: V) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self.capacity:
            self._store.popitem(last=False)  # least recently used is first

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
