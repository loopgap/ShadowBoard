import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.browser import BrowserManager

@pytest.mark.asyncio
async def test_browser_manager_launch():
    mock_playwright = AsyncMock()
    mock_chromium = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    
    mock_playwright.chromium = mock_chromium
    mock_chromium.launch_persistent_context.return_value = mock_context
    mock_context.pages = [mock_page]
    mock_context.new_page = AsyncMock(return_value=mock_page)
    
    with patch("playwright.async_api.async_playwright") as mock_ap, \
         patch("src.core.browser.get_config_manager") as mock_get_config:
        
        mock_ap_instance = MagicMock()
        mock_ap_instance.start = AsyncMock(return_value=mock_playwright)
        mock_ap.return_value = mock_ap_instance
        
        mock_config = MagicMock()
        mock_config.profile_dir = "test_profile"
        mock_config.get.return_value = "msedge"
        mock_get_config.return_value = mock_config
        
        manager = BrowserManager()
        context = await manager.launch()
        
        assert context == mock_context
        assert manager._page == mock_page
        assert manager._session is not None
        assert manager.is_active is True
        
        mock_chromium.launch_persistent_context.assert_called_once()
        mock_page.set_default_timeout.assert_called_with(30000)

@pytest.mark.asyncio
async def test_browser_manager_navigate():
    manager = BrowserManager()
    mock_page = AsyncMock()
    manager._page = mock_page
    
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda k, d=None: "https://example.com" if k == "target_url" else (30 if k == "navigation_timeout_seconds" else d)
    
    with patch("src.core.browser.get_config_manager", return_value=mock_config):
        page = await manager.navigate("https://test.com")
        
        assert page == mock_page
        mock_page.goto.assert_called_with(
            "https://test.com",
            wait_until="domcontentloaded",
            timeout=30000
        )

@pytest.mark.asyncio
async def test_browser_manager_close():
    manager = BrowserManager()
    mock_context = AsyncMock()
    mock_playwright = AsyncMock()
    manager._context = mock_context
    manager._playwright = mock_playwright
    manager._page = MagicMock()
    manager._session = MagicMock()
    
    await manager.close()
    
    mock_context.close.assert_called_once()
    mock_playwright.stop.assert_called_once()
    assert manager._context is None
    assert manager._playwright is None
    assert manager._page is None
    assert manager._session is None
    assert manager._closed is True

@pytest.mark.asyncio
async def test_browser_session_context():
    manager = BrowserManager()
    mock_page = MagicMock()
    manager.launch = AsyncMock()
    manager.navigate = AsyncMock()
    manager.close = AsyncMock()
    manager._page = mock_page
    
    async with manager.session_context(url="https://test.com") as page:
        assert page == mock_page
        manager.launch.assert_called_once()
        manager.navigate.assert_called_with("https://test.com")
        
    manager.close.assert_called_once()

@pytest.mark.asyncio
async def test_browser_manager_ensure_playwright():
    manager = BrowserManager()
    mock_playwright = AsyncMock()
    
    with patch("playwright.async_api.async_playwright") as mock_ap:
        mock_ap_instance = MagicMock()
        mock_ap_instance.start = AsyncMock(return_value=mock_playwright)
        mock_ap.return_value = mock_ap_instance
        
        pw = await manager._ensure_playwright()
        assert pw == mock_playwright
        assert manager._playwright == mock_playwright
        
        pw2 = await manager._ensure_playwright()
        assert pw2 == pw
        mock_ap_instance.start.assert_called_once()
