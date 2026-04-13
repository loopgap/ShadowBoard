"""
Browser Management Module

Provides browser automation capabilities with:
- Session pooling and reuse
- Automatic fallback strategies
- Health monitoring
- Resource management
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, AsyncGenerator, TYPE_CHECKING

from .config import get_config_manager
from .exceptions import BrowserError

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page, Playwright, Locator

logger = logging.getLogger(__name__)


@dataclass
class BrowserSession:
    """
    Represents an active browser session.

    Tracks session state, health, and resource usage.
    """
    id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    page_count: int = 0
    is_healthy: bool = True
    error_count: int = 0

    def touch(self) -> None:
        """Update last used timestamp."""
        self.last_used = datetime.now()

    def record_error(self) -> None:
        """Record an error for health tracking."""
        self.error_count += 1
        if self.error_count >= 3:
            self.is_healthy = False


class BrowserManager:
    """
    Manages browser instances with session pooling.

    Features:
    - Lazy initialization
    - Session reuse
    - Automatic cleanup
    - Fallback strategies
    """

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._session: Optional[BrowserSession] = None
        self._lock = asyncio.Lock()
        self._closed = False

    async def _ensure_playwright(self) -> Playwright:
        """Ensure Playwright is initialized."""
        if self._playwright is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
        return self._playwright

    async def launch(
        self,
        headless: bool = False,
        channel: Optional[str] = None,
    ) -> BrowserContext:
        """
        Launch browser with persistent context.

        Args:
            headless: Run in headless mode
            channel: Browser channel (msedge, chrome, etc.)

        Returns:
            Browser context
        """
        config = get_config_manager()
        profile_dir = config.profile_dir
        preferred_channel = channel or config.get("browser_channel", "msedge")

        launch_kwargs = {
            "user_data_dir": str(profile_dir),
            "headless": headless,
            "viewport": {"width": 1280, "height": 800},
        }

        playwright = await self._ensure_playwright()

        # Try preferred channel first
        try:
            if preferred_channel:
                self._context = await playwright.chromium.launch_persistent_context(
                    channel=preferred_channel,
                    **launch_kwargs
                )
            else:
                self._context = await playwright.chromium.launch_persistent_context(
                    **launch_kwargs
                )
        except Exception as e:
            # Fallback to default chromium
            logger.warning(f"Failed to launch with channel '{preferred_channel}': {e}. Falling back to default.")
            try:
                self._context = await playwright.chromium.launch_persistent_context(
                    **launch_kwargs
                )
            except Exception as inner_e:
                # 修复：显式清理资源防止僵尸进程
                await self.close()
                raise BrowserError(
                    f"Failed to launch browser: {inner_e}",
                    cause=inner_e,
                )

        # Create or get page
        try:
            if self._context is None:
                raise BrowserError("Browser context is None after launch")
                
            if not self._context.pages:
                await self._context.new_page()
            
            if not self._context.pages:
                raise BrowserError("Failed to create page in browser context")
                
            self._page = self._context.pages[0]

            # Configure timeouts
            self._page.set_default_timeout(30000)
            self._page.set_default_navigation_timeout(60000)

            # Create session tracking
            import uuid
            self._session = BrowserSession(id=uuid.uuid4().hex[:8])
            self._session.page_count = len(self._context.pages)
        except Exception as e:
            await self.close()
            raise BrowserError(f"Failed to initialize browser state: {e}", cause=e)

        return self._context

    async def get_page(self) -> Page:
        """
        Get the current page or create one.

        Returns:
            Playwright Page object
        """
        async with self._lock:
            if self._page is None:
                await self.launch()

            if self._page is None:
                raise BrowserError("Browser page is unavailable")

            if self._session:
                self._session.touch()

            return self._page

    async def navigate(
        self,
        url: Optional[str] = None,
        wait_until: str = "domcontentloaded",
    ) -> Page:
        """
        Navigate to a URL.

        Args:
            url: Target URL (uses config default if not provided)
            wait_until: Wait condition

        Returns:
            Page object
        """
        config = get_config_manager()
        target_url = url or config.get("target_url")
        
        if not target_url:
            raise BrowserError("No navigation URL specified")

        page = await self.get_page()
        timeout = config.get("navigation_timeout_seconds", 30) * 1000

        try:
            await page.goto(
                target_url,
                wait_until=wait_until,
                timeout=timeout,
            )
        except Exception as e:
            # 修复：根据重要性适度向上抛出或记录错误状态，防止盲目执行
            error_msg = f"Navigation failed for {target_url}: {e}"
            logger.error(error_msg)
            
            if self._session:
                self._session.record_error()
                
            # 如果是关键连接错误，向上抛出异常
            if any(err in str(e) for err in ["ERR_NAME_NOT_RESOLVED", "ERR_CONNECTION_REFUSED", "Timeout"]):
                raise BrowserError(error_msg, cause=e)

        return page

    async def close(self) -> None:
        """Close browser and cleanup resources."""
        async with self._lock:
            if self._context is not None:
                try:
                    await self._context.close()
                except Exception as e:
                    logger.warning(f"Error closing browser context: {e}")
                self._context = None

            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.warning(f"Error stopping playwright: {e}")
                self._playwright = None

            self._page = None
            self._session = None
            self._closed = True

    @property
    def is_active(self) -> bool:
        """Check if browser session is active."""
        return self._context is not None and not self._closed

    @property
    def session(self) -> Optional[BrowserSession]:
        """Get current session info."""
        return self._session

    @asynccontextmanager
    async def session_context(
        self,
        url: Optional[str] = None,
        headless: bool = False,
    ) -> AsyncGenerator[Page, None]:
        """
        Context manager for browser sessions.

        Ensures proper cleanup even on errors.
        """
        try:
            await self.launch(headless=headless)
            if url:
                await self.navigate(url)
            if self._page is None:
                raise BrowserError("Failed to initialize page in session context")
            yield self._page
        finally:
            await self.close()


# Element Locator Utilities

async def get_first_visible_locator(
    page: Page,
    selectors: List[str],
    timeout_ms: int = 5000,
) -> Optional[Locator]:
    """
    Find the first visible element matching selectors.

    Uses a multi-stage semantic anchor strategy:
    1. Try explicit CSS selectors
    2. Fall back to A11y role-based search
    3. Try visual placeholders

    Args:
        page: Playwright page object
        selectors: List of CSS selectors to try
        timeout_ms: Timeout in milliseconds

    Returns:
        Locator object or None if not found
    """
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    # Stage 1: Try explicit selectors
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(timeout=timeout_ms // 2, state="visible")
            return locator
        except PlaywrightTimeoutError:
            continue
        except Exception as e:
            logger.debug(f"Locator error for {selector}: {e}")
            continue

    # Stage 2: Semantic fallback (A11y roles)
    if any("textarea" in s for s in selectors):
        for role in ["textbox", "searchbox"]:
            try:
                loc = page.get_by_role(role).first  # type: ignore
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception as e:
                logger.debug(f"Role search error for {role}: {e}")

    # Stage 3: Visual placeholder fallback
    placeholders = ["输入", "message", "chat", "问我", "ask"]
    for placeholder in placeholders:
        try:
            loc = page.get_by_placeholder(placeholder, exact=False).first
            if await loc.count() > 0 and await loc.is_visible():
                return loc
        except Exception as e:
            logger.debug(f"Placeholder search error for {placeholder}: {e}")

    return None


async def get_latest_response_text(
    page: Page,
    selectors: List[str],
) -> str:
    """
    Get the latest AI response text from the page.

    Args:
        page: Playwright page object
        selectors: CSS selectors for response elements

    Returns:
        Response text or empty string
    """
    best = ""
    for selector in selectors:
        try:
            loc = page.locator(selector)
            count = await loc.count()
            if count <= 0:
                continue
            text = await loc.nth(count - 1).inner_text()
            text = text.strip()
            if len(text) > len(best):
                best = text
        except Exception as e:
            logger.debug(f"Failed to get response text for selector {selector}: {e}")
            continue
    return best
