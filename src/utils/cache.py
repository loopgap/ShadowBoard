"""
Caching Utilities

Provides LRU cache implementation with TTL support.
"""

from __future__ import annotations

import functools
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Dict, Optional, TypeVar, Generic

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

# Background cleanup interval in seconds (5 minutes)
_CLEANUP_INTERVAL_SECONDS = 300


@dataclass
class CacheEntry(Generic[V]):
    """Represents a cached value with metadata."""

    value: V
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    access_count: int = 0

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        """Record an access."""
        self.access_count += 1


class LRUCache(Generic[K, V]):
    """
    Thread-safe LRU cache with TTL support.

    Features:
    - Maximum size limit with LRU eviction
    - Optional TTL (time-to-live) for entries
    - Thread-safe operations
    - Access statistics
    - Background cleanup of expired entries
    """

    def __init__(
        self,
        max_size: int = 100,
        default_ttl: Optional[float] = None,
        cleanup_interval: float = _CLEANUP_INTERVAL_SECONDS,
    ) -> None:
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of entries
            default_ttl: Default TTL in seconds (None = no expiry)
            cleanup_interval: Background cleanup interval in seconds
        """
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
        self._cleanup_interval = cleanup_interval
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()

    def get(self, key: K) -> Optional[V]:
        """Get value from cache, returns None if not found or expired."""
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.touch()
            self._hits += 1
            return entry.value

    def set(
        self,
        key: K,
        value: V,
        ttl: Optional[float] = None,
    ) -> None:
        """Set value in cache with optional TTL."""
        with self._lock:
            # Remove if exists
            if key in self._cache:
                del self._cache[key]

            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            # Calculate expiry
            effective_ttl = ttl if ttl is not None else self._default_ttl
            expires_at = time.time() + effective_ttl if effective_ttl else None

            # Add entry
            self._cache[key] = CacheEntry(
                value=value,
                expires_at=expires_at,
            )

    def delete(self, key: K) -> bool:
        """Delete entry from cache. Returns True if existed."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        with self._lock:
            expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    @property
    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)

    @property
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }

    def _cleanup_loop(self) -> None:
        """Background cleanup loop that runs every cleanup_interval seconds."""
        while not self._stop_cleanup.wait(self._cleanup_interval):
            try:
                removed = self.cleanup_expired()
                if removed > 0:
                    pass  # Could add logging here if needed
            except Exception:
                pass  # Suppress errors in background thread

    def start_background_cleanup(self) -> None:
        """Start the background cleanup thread."""
        if self._cleanup_thread is not None and self._cleanup_thread.is_alive():
            return
        self._stop_cleanup.clear()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def stop_background_cleanup(self) -> None:
        """Stop the background cleanup thread."""
        if self._cleanup_thread is None:
            return
        self._stop_cleanup.set()
        self._cleanup_thread.join(timeout=5.0)
        self._cleanup_thread = None


# Global cache instances
_function_cache: LRUCache[str, Any] = LRUCache(max_size=200, default_ttl=300)
_function_cache.start_background_cleanup()


def cache_result(
    ttl: Optional[float] = 300,
    key_func: Optional[Callable[..., str]] = None,
) -> Callable[[Callable[T]], Callable[T]]:
    """
    Decorator to cache function results.

    Args:
        ttl: Time-to-live in seconds
        key_func: Custom function to generate cache key

    Returns:
        Decorated function

    Example:
        @cache_result(ttl=60)
        def expensive_computation(n):
            return sum(range(n))
    """

    def decorator(func: Callable[T]) -> Callable[T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}|{repr(args)}|{repr(sorted(kwargs.items()))}"

            # Check cache
            cached = _function_cache.get(cache_key)
            if cached is not None:
                return cached

            # Compute and cache
            result = func(*args, **kwargs)
            _function_cache.set(cache_key, result, ttl=ttl)
            return result

        return wrapper  # type: ignore

    return decorator


def cached(key: str = "", ttl: Optional[float] = None) -> Any:
    """
    Simple cache getter for manual caching.

    Usage:
        result = cached("my_key")
        if result is None:
            result = compute_expensive()
            cached_set("my_key", result, ttl=60)

    Can also be used as a decorator with key parameter.
    """
    # If used as decorator without calling, key will be the function
    if callable(key):
        # Direct decoration without arguments: @cached
        func = key

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = f"{func.__name__}|{repr(args)}|{repr(sorted(kwargs.items()))}"
            cached_value = _function_cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            result = func(*args, **kwargs)
            _function_cache.set(cache_key, result, ttl=300)
            return result

        return wrapper

    return _function_cache.get(key)


def cached_set(key: str, value: Any, ttl: Optional[float] = None) -> None:
    """Set a value in the global cache."""
    _function_cache.set(key, value, ttl=ttl)


def clear_cache() -> None:
    """Clear the global function cache."""
    _function_cache.clear()
