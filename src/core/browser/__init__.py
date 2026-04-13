"""Browser Module with backward-compatible BrowserManager and pool APIs."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ..config import get_config_manager
from ..exceptions import BrowserError
from .browser_pool import BrowserPool, BrowserPoolConfig, BrowserHealth, BrowserMetrics


@dataclass
class BrowserSession:
    id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    page_count: int = 0
    is_healthy: bool = True
    error_count: int = 0

    def touch(self) -> None:
        self.last_used = datetime.now()


class BrowserManager:
    def __init__(self) -> None:
        self._playwright = None
        self._context = None
        self._page = None
        self._session: Optional[BrowserSession] = None
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def is_active(self) -> bool:
        return self._context is not None and self._page is not None and not self._closed

    async def _ensure_playwright(self):
        if self._playwright is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
        return self._playwright

    async def launch(self, headless: bool = False, channel: Optional[str] = None):
        config = get_config_manager()
        preferred_channel = channel or config.get("browser_channel", "msedge")
        playwright = await self._ensure_playwright()

        launch_kwargs = {
            "user_data_dir": str(config.profile_dir),
            "headless": headless,
            "viewport": {"width": 1280, "height": 800},
        }

        try:
            if preferred_channel:
                self._context = await playwright.chromium.launch_persistent_context(channel=preferred_channel, **launch_kwargs)
            else:
                self._context = await playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception:
            self._context = await playwright.chromium.launch_persistent_context(**launch_kwargs)

        if not self._context.pages:
            await self._context.new_page()
        self._page = self._context.pages[0]
        default_timeout_result = self._page.set_default_timeout(30000)
        if asyncio.iscoroutine(default_timeout_result):
            await default_timeout_result
        nav_timeout_result = self._page.set_default_navigation_timeout(60000)
        if asyncio.iscoroutine(nav_timeout_result):
            await nav_timeout_result

        import uuid

        self._session = BrowserSession(id=uuid.uuid4().hex[:8], page_count=len(self._context.pages))
        return self._context

    async def get_page(self):
        if self._page is None:
            await self.launch()
        return self._page

    async def navigate(self, url: Optional[str] = None, wait_until: str = "domcontentloaded"):
        page = await self.get_page()
        config = get_config_manager()
        target_url = url or config.get("target_url")
        timeout = int(config.get("navigation_timeout_seconds", 30)) * 1000
        try:
            await page.goto(target_url, wait_until=wait_until, timeout=timeout)
        except Exception as exc:
            raise BrowserError(f"Navigation failed: {exc}", cause=exc)
        return page

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            if self._context is not None:
                await self._context.close()
            if self._playwright is not None:
                await self._playwright.stop()
            self._context = None
            self._playwright = None
            self._page = None
            self._session = None

    @asynccontextmanager
    async def session_context(self, url: Optional[str] = None, headless: bool = False):
        try:
            await self.launch(headless=headless)
            if url:
                await self.navigate(url)
            yield self._page
        finally:
            await self.close()


async def get_first_visible_locator(page, selectors, timeout_ms: int = 5000):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(timeout=timeout_ms)
            return locator
        except PlaywrightTimeoutError:
            continue
    return None


async def get_latest_response_text(page, selectors):
    best = ""
    for selector in selectors:
        loc = page.locator(selector)
        count = await loc.count()
        if count <= 0:
            continue
        text = (await loc.nth(count - 1).inner_text()).strip()
        if len(text) > len(best):
            best = text
    return best


__all__ = [
    "BrowserManager",
    "BrowserSession",
    "get_first_visible_locator",
    "get_latest_response_text",
    "BrowserPool",
    "BrowserPoolConfig",
    "BrowserHealth",
    "BrowserMetrics",
]

_pool = None


async def get_browser_pool(config: BrowserPoolConfig = None) -> BrowserPool:
    global _pool
    if _pool is None:
        _pool = BrowserPool(config)
        await _pool.initialize()
    return _pool


async def close_browser_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
