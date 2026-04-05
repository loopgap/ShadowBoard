from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

import main

def test_build_prompt():
    assert "Summarize" in main.build_prompt("summary", "abc")
    assert "Translate" in main.build_prompt("translation", "abc")
    assert main.build_prompt("custom", "direct") == "direct"

def test_load_save_config(tmp_path, monkeypatch):
    conf_file = tmp_path / "config.json"
    monkeypatch.setattr(main, "CONFIG_PATH", conf_file)
    monkeypatch.setattr(main, "STATE_DIR", tmp_path)
    
    # Test default
    cfg = main.load_config()
    assert cfg["target_url"] == "https://chat.deepseek.com/"
    
    # Test save and load
    cfg["target_url"] = "https://example.com"
    main.save_config(cfg)
    cfg2 = main.load_config()
    assert cfg2["target_url"] == "https://example.com"

def test_load_config_corrupted(tmp_path, monkeypatch):
    conf_file = tmp_path / "config.json"
    conf_file.write_text("invalid json")
    monkeypatch.setattr(main, "CONFIG_PATH", conf_file)
    monkeypatch.setattr(main, "STATE_DIR", tmp_path)
    
    cfg = main.load_config()
    assert cfg["target_url"] == "https://chat.deepseek.com/" # reset to default

def test_history_ops(tmp_path, monkeypatch):
    hist_file = tmp_path / "history.jsonl"
    monkeypatch.setattr(main, "HISTORY_PATH", hist_file)
    
    main.append_history({"ok": True, "time": "now"})
    main.append_history({"ok": False, "time": "later"})
    
    rows = main.read_history(limit=10)
    assert len(rows) == 2
    assert rows[0]["ok"] is False 
    assert rows[1]["ok"] is True

def test_read_history_corrupted(tmp_path, monkeypatch):
    hist_file = tmp_path / "history.jsonl"
    hist_file.write_text("{\"valid\": true}\ninvalid\n{\"valid\": false}")
    monkeypatch.setattr(main, "HISTORY_PATH", hist_file)
    
    rows = main.read_history(limit=10)
    assert len(rows) == 2 # skipped invalid line
    assert rows[0]["valid"] is False
    assert rows[1]["valid"] is True

def test_read_history_empty(tmp_path, monkeypatch):
    hist_file = tmp_path / "nonexistent.jsonl"
    monkeypatch.setattr(main, "HISTORY_PATH", hist_file)
    assert main.read_history() == []

@pytest.mark.asyncio
async def test_get_first_visible_locator_success():
    page = MagicMock()
    locator = MagicMock()
    locator.wait_for = AsyncMock()
    page.locator.return_value.first = locator
    
    res = await main.get_first_visible_locator(page, ["#a", "#b"], 100)
    assert res == locator
    assert page.locator.called

@pytest.mark.asyncio
async def test_get_first_visible_locator_fail():
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    page = MagicMock()
    
    # Mock locator for step 1
    locator = MagicMock()
    locator.wait_for = AsyncMock(side_effect=PlaywrightTimeoutError("timeout"))
    page.locator.return_value.first = locator
    
    # Mock for step 2 & 3
    sub_loc = MagicMock()
    sub_loc.count = AsyncMock(return_value=0)
    sub_loc.is_visible = AsyncMock(return_value=False)
    page.get_by_role.return_value.first = sub_loc
    page.get_by_placeholder.return_value.first = sub_loc
    
    res = await main.get_first_visible_locator(page, ["#a"], 100)
    assert res is None

@pytest.mark.asyncio
async def test_get_latest_response_text():
    page = MagicMock()
    loc = MagicMock()
    loc.count = AsyncMock(return_value=2)
    loc.nth.return_value.inner_text = AsyncMock(return_value="hello")
    page.locator.return_value = loc
    
    text = await main.get_latest_response_text(page, [".msg"])
    assert text == "hello"

@pytest.mark.asyncio
async def test_wait_for_response_generator(monkeypatch):
    page = MagicMock()
    responses = ["a", "ab", "abc", "abc"]
    idx = 0
    async def fake_get_latest(*args):
        nonlocal idx
        val = responses[min(idx, len(responses)-1)]
        idx += 1
        return val
    
    monkeypatch.setattr(main, "get_latest_response_text", fake_get_latest)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    chunks = []
    gen = main.wait_for_response(page, [".msg"], timeout_seconds=5, stable_seconds=1)
    
    async for chunk in gen:
        chunks.append(chunk)
        if len(chunks) >= 5:
            break
            
    assert "a" in chunks
    assert "ab" in chunks
    assert "abc" in chunks

@pytest.mark.asyncio
async def test_send_with_retry_logic(monkeypatch):
    config = {"max_retries": 2, "backoff_seconds": 0.01}
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    
    call_count = 0
    async def fake_send_once(cfg, prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("fail")
        yield "success"

    monkeypatch.setattr(main, "send_once", fake_send_once)
    
    results = []
    async for chunk in main.send_with_retry(config, "test"):
        results.append(chunk)
        
    assert call_count == 2
    assert "success" in results

@pytest.mark.asyncio
async def test_send_with_retry_exhausted(monkeypatch):
    config = {"max_retries": 2, "backoff_seconds": 0.01}
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    
    async def fake_send_once_fail(cfg, prompt):
        raise RuntimeError("always fail")
        yield ""

    monkeypatch.setattr(main, "send_once", fake_send_once_fail)
    
    with pytest.raises(RuntimeError, match="always fail"):
        async for _ in main.send_with_retry(config, "test"):
            pass
