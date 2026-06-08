"""A tiny bounded LRU (Least-Recently-Used) cache backed by OrderedDict.

Why not functools.lru_cache? These caches are SHARED between two endpoints (the
blocking and the streaming answer handlers read *and* write the same store),
they need an explicit `cached` flag in the HTTP response, and they must support
a per-graph .clear() when the active graph is hot-swapped. A decorator gives you
none of those. ~25 lines of OrderedDict buys all of it with O(1) get/set/evict
and a hard memory ceiling, which is the whole point — the old plain-dict caches
grew without bound and leaked memory on a long-running server.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """Fixed-capacity cache that evicts the least-recently-used entry first.

    The eviction policy IS the OrderedDict's ordering: we keep the *oldest*
    (least-recently-used) entry on the left and the *most-recently-used* on the
    right. Every read or write moves the touched key to the right, so whatever
    has drifted to the far left is, by definition, the coldest entry — and that's
    exactly what we drop when we're over capacity.
    """

    def __init__(self, capacity: int = 256) -> None:
        if capacity <= 0:
            raise ValueError("LRUCache capacity must be positive")
        self.capacity = capacity
        self._store: "OrderedDict[K, V]" = OrderedDict()

    def get(self, key: K) -> Optional[V]:
        """Return the value (and mark it most-recently-used), or None on miss."""
        if key not in self._store:
            return None
        # A successful read counts as "use": promote the key to the right end so
        # it survives the next eviction. This is what makes it LRU and not FIFO.
        self._store.move_to_end(key)
        return self._store[key]

    def __contains__(self, key: K) -> bool:
        # Note: membership does NOT promote — only get()/set() count as a "use".
        return key in self._store

    def set(self, key: K, value: V) -> None:
        """Insert/overwrite a value, then evict oldest entries past capacity."""
        if key in self._store:
            # Overwriting an existing key still counts as a use → promote it.
            self._store.move_to_end(key)
        self._store[key] = value
        # Evict from the LEFT (oldest) until we're back within the ceiling.
        # last=False pops the first-inserted / least-recently-used item; a normal
        # popitem() would pop the newest, which is the opposite of what we want.
        while len(self._store) > self.capacity:
            self._store.popitem(last=False)

    def clear(self) -> None:
        """Drop everything — used when the active graph changes (snippets differ)."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
