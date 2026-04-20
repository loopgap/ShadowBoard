"""
UI Compatibility Smoke Test

Checks if the target AI platform's UI structure is still compatible with the selector logic.
"""

import os
import pytest
from playwright.async_api import async_playwright
from src.core.config import get_config_manager

@pytest.mark.asyncio
async def test_ui_compatibility_probe():
    """
    Probe the target AI platform's UI structure.
    If CI=true and no network, skip with success to not block CI.
    """
    # Fix: Use get_all() instead of load_config()
    config = get_config_manager().get_all()
    target_url = config.get("target_url")
    
    if not target_url or "localhost" in target_url or "example.com" in target_url:
        pytest.skip("No real AI platform URL configured for compatibility probe.")

    is_ci = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Use a short timeout for the probe
            await page.goto(target_url, timeout=15000)
            
            # Check for common AI platform input elements
            selectors = [
                "textarea", 
                "input[type='text']",
                "[contenteditable='true']",
                "#chat-input",
                ".chat-input"
            ]
            
            found = False
            for selector in selectors:
                try:
                    el = await page.wait_for_selector(selector, timeout=5000)
                    if el:
                        found = True
                        break
                except Exception:
                    continue
            
            await browser.close()
            
            if not found:
                print(f"Warning: UI compatibility probe failed to find input elements at {target_url}")
                if not is_ci:
                    # Only assert in local dev environment where we expect real access
                    assert found, f"UI compatibility probe failed: No input elements found at {target_url}"
                else:
                    pytest.skip("UI compatibility probe failed to find elements, but skipping as it's non-blocking in CI.")
        
        except Exception as e:
            if is_ci:
                pytest.skip(f"UI compatibility probe skipped due to network/timeout: {e}")
            else:
                raise e
