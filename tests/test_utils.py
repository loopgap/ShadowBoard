"""
Tests for Utility Modules
"""

from __future__ import annotations

from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.cache import LRUCache, cached, cached_set, clear_cache, cache_result
from src.utils.helpers import (
    build_prompt,
    shorten_text,
    format_duration,
    get_timestamp,
    parse_bool,
    safe_get,
)


# LRUCache Tests

def test_lru_cache_basic():
    """Test basic cache operations."""
    cache = LRUCache(max_size=3)
    
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    
    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_lru_cache_eviction():
    """Test LRU eviction."""
    cache = LRUCache(max_size=2)
    
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # Should evict "a"
    
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_lru_cache_ttl():
    """Test TTL expiration."""
    import time
    
    cache = LRUCache(max_size=10, default_ttl=0.1)
    
    cache.set("expire", "value")
    assert cache.get("expire") == "value"
    
    time.sleep(0.15)
    assert cache.get("expire") is None


def test_lru_cache_stats():
    """Test cache statistics."""
    cache = LRUCache(max_size=10)
    
    cache.set("a", 1)
    cache.get("a")  # hit
    cache.get("b")  # miss
    
    stats = cache.stats
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["size"] == 1


def test_lru_cache_clear():
    """Test cache clearing."""
    cache = LRUCache()
    
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    
    assert cache.size == 0


def test_cache_decorator():
    """Test the @cache_result decorator."""
    call_count = 0
    
    @cache_result(ttl=60)
    def expensive_function(n):
        nonlocal call_count
        call_count += 1
        return n * 2
    
    result1 = expensive_function(5)
    result2 = expensive_function(5)  # Should be cached
    
    assert result1 == 10
    assert result2 == 10
    assert call_count == 1  # Only called once


def test_global_cache():
    """Test global cache functions."""
    cached_set("test_key", "test_value")
    result = cached("test_key")
    assert result == "test_value"
    
    clear_cache()
    assert cached("test_key") is None


# Helper Function Tests

def test_build_prompt():
    """Test prompt building."""
    result = build_prompt("summary", "Test content")
    assert "Test content" in result
    assert "Summarize" in result
    
    custom = build_prompt("custom", "Direct input")
    assert custom == "Direct input"


def test_shorten_text():
    """Test text shortening."""
    long_text = "A" * 200
    
    result = shorten_text(long_text, max_length=50)
    assert len(result) == 50
    assert result.endswith("...")
    
    short = shorten_text("Short", max_length=100)
    assert short == "Short"


def test_format_duration():
    """Test duration formatting."""
    assert format_duration(30.5) == "30.5s"
    assert format_duration(90) == "1m 30s"
    assert format_duration(3661) == "1h 1m"


def test_get_timestamp():
    """Test timestamp generation."""
    iso = get_timestamp("iso")
    assert "T" in iso  # ISO format contains T
    
    file_ts = get_timestamp("file")
    assert "_" in file_ts  # File format uses underscore
    
    display = get_timestamp("display")
    assert ":" in display  # Display format contains colons


def test_parse_bool():
    """Test boolean parsing."""
    assert parse_bool(True) is True
    assert parse_bool("true") is True
    assert parse_bool("yes") is True
    assert parse_bool("1") is True
    assert parse_bool(False) is False
    assert parse_bool("false") is False
    assert parse_bool("no") is False
    assert parse_bool("invalid", default=True) is True


def test_safe_get():
    """Test safe dictionary access."""
    data = {"a": {"b": {"c": 1}}}
    
    assert safe_get(data, "a", "b", "c") == 1
    assert safe_get(data, "a", "b", "d") is None
    assert safe_get(data, "a", "x", "y", default="missing") == "missing"
    assert safe_get(data, "x", "y", default=0) == 0
