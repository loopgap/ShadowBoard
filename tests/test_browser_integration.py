"""
Real Browser Integration Tests

Tests that launch actual Chromium browser via Playwright.
These tests verify real browser automation without mocks.
"""

from playwright.sync_api import sync_playwright


def test_browser_launch():
    """Launch real Chromium browser and verify it starts."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        assert browser is not None
        assert browser.version is not None
        browser.close()


def test_browser_close():
    """Close browser cleanly."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        assert page is not None
        browser.close()
        # Context and page should be unusable after close
        assert context.pages == []


def test_navigation():
    """Navigate to about:blank and verify page loads."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("about:blank")
        assert page.url == "about:blank"
        browser.close()


def test_element_check():
    """Check element existence on a page with HTML content."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Set some HTML content to test against
        page.set_content("""
        <html>
            <body>
                <h1 id="title">Test Page</h1>
                <p class="description">A test paragraph</p>
                <div data-testid="container">
                    <span>Nested content</span>
                </div>
            </body>
        </html>
        """)

        # Check element existence
        assert page.locator("#title").count() > 0
        assert page.locator(".description").count() > 0
        assert page.locator("[data-testid='container']").count() > 0
        assert page.locator("span").count() > 0

        browser.close()


def test_element_visibility():
    """Test that element visibility can be checked."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.set_content("""
        <html>
            <body>
                <div id="visible">Visible text</div>
                <div id="hidden" style="display: none;">Hidden text</div>
            </body>
        </html>
        """)

        # Check visible element
        visible_locator = page.locator("#visible")
        assert visible_locator.count() > 0
        assert visible_locator.is_visible()

        # Check hidden element exists but is not visible
        hidden_locator = page.locator("#hidden")
        assert hidden_locator.count() > 0
        assert not hidden_locator.is_visible()

        browser.close()
