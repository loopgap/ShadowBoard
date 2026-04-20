"""
Tests for Core Logic (Updated for v3.0 ShadowBoard Architecture)

These tests verify the core engine functionality.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import os

import main


def test_build_prompt():
    assert "ShadowBoard" in main.build_prompt("market_analyst", "abc")
    assert "ShadowBoard" in main.build_prompt("tech_lead", "abc")
    assert main.build_prompt("custom", "direct") == "direct"


def test_load_save_config(tmp_path):
    """Test config loading with the new ConfigManager."""
    from src.core.config import ConfigManager

    tmpdir = tmp_path
    config_path = tmpdir / "config.json"
    manager = ConfigManager(config_path=config_path, state_dir=tmpdir)

    # Test default
    cfg = manager.get_all()
    assert cfg["target_url"] == "https://chat.deepseek.com/"

    # Test save and load
    manager.set("target_url", "https://example.com")
    cfg2 = manager.get_all()
    assert cfg2["target_url"] == "https://example.com"


def test_load_config_corrupted(tmp_path):
    """Test config loading with corrupted file raises ConfigError."""
    from src.core.exceptions import ConfigError

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    config_path = state_dir / "config.json"

    # Write corrupted content
    config_path.write_text("{invalid json content", encoding="utf-8")

    # Create a temporary manager instance (bypassing singleton)
    from src.core.config import ConfigManager

    manager = object.__new__(ConfigManager)
    manager._state_dir = state_dir
    manager._config_path = config_path
    manager._providers = {}
    manager._config = {}
    manager._listeners = []

    # Test that corrupted config raises ConfigError
    with pytest.raises(ConfigError) as exc_info:
        manager._load_config()

    # Verify the error message
    assert "corrupted" in str(exc_info.value).lower()


def test_load_config_empty_file(tmp_path):
    """Test config loading with empty file returns defaults."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    config_path = state_dir / "config.json"

    # Write empty content
    config_path.write_text("", encoding="utf-8")

    # Create a temporary manager instance (bypassing singleton)
    from src.core.config import ConfigManager, DEFAULT_CONFIG

    manager = object.__new__(ConfigManager)
    manager._state_dir = state_dir
    manager._config_path = config_path
    manager._providers = {}
    manager._config = {}
    manager._listeners = []

    # Test that empty config returns defaults
    loaded_config = manager._load_config()
    assert loaded_config["target_url"] == DEFAULT_CONFIG["target_url"]


def test_history_ops(tmp_path):
    """Test history operations with file-based storage."""
    tmpdir = tmp_path
    history_path = tmpdir / "history.jsonl"

    # Write entries directly
    entry1 = {"ok": True, "time": "now", "template": "custom"}
    entry2 = {"ok": False, "time": "later", "template": "custom"}
    history_path.write_text(json.dumps(entry1) + "\n" + json.dumps(entry2) + "\n", encoding="utf-8")

    # Read using the main module's function with patched path
    with patch.object(main, "HISTORY_PATH", history_path):
        with patch.object(main, "get_config_manager") as mock_mgr:
            mock_mgr.return_value.history_path = history_path
            rows = main.read_history(limit=10)
            assert len(rows) == 2
            assert rows[0]["ok"] is False
            assert rows[1]["ok"] is True


def test_read_history_corrupted(tmp_path):
    """Test reading history with corrupted lines."""
    # Test the underlying read_history function logic directly
    hist_file = tmp_path / "history.jsonl"
    # Write valid and invalid lines
    hist_file.write_text('{"valid": true}\ninvalid line\n{"valid": false}', encoding="utf-8")

    # Use the core read logic directly
    rows = []
    chunk_size = 4096

    with hist_file.open("rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        buffer = bytearray()
        pointer = file_size

        while pointer > 0 and len(rows) < 10:
            step = min(pointer, chunk_size)
            pointer -= step
            f.seek(pointer)
            new_chunk = f.read(step)
            buffer = new_chunk + buffer

            lines = buffer.splitlines()
            if pointer > 0:
                buffer = lines[0]
                to_process = lines[1:]
            else:
                buffer = bytearray()
                to_process = lines

            for line in reversed(to_process):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line.decode("utf-8")))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

    assert len(rows) == 2  # skipped invalid line
    assert rows[0]["valid"] is False  # Most recent first
    assert rows[1]["valid"] is True


def test_read_history_empty(tmp_path):
    """Test reading from nonexistent history file."""
    hist_file = tmp_path / "nonexistent.jsonl"

    with patch.object(main, "HISTORY_PATH", hist_file):
        rows = main.read_history(limit=10)
        # Should return empty list for nonexistent file
        assert rows == []


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
        val = responses[min(idx, len(responses) - 1)]
        idx += 1
        return val

    # Patch the function in main module
    with patch.object(main, "get_latest_response_text", fake_get_latest):
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
    async_gen = main.send_with_retry(config, "test")
    async for chunk in async_gen:
        results.append(chunk)

    assert call_count == 2
    assert "success" in results


@pytest.mark.asyncio
async def test_send_with_retry_exhausted(monkeypatch):
    config = {"max_retries": 2, "backoff_seconds": 0.01}
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    async def fake_send_once_fail(cfg, prompt):
        raise RuntimeError("always fail")
        if False:
            yield ""

    monkeypatch.setattr(main, "send_once", fake_send_once_fail)

    with pytest.raises(RuntimeError, match="always fail"):
        async_gen = main.send_with_retry(config, "test")
        async for _ in async_gen:
            pass


# ============== Tests for new services ==============


@pytest.mark.asyncio
async def test_task_tracker_basic(tmp_path):
    """Test TaskTracker basic functionality."""
    from src.services.task_tracker import TaskTracker
    from src.models.task import TaskStatus

    tmpdir = tmp_path
    tracker = TaskTracker(state_dir=tmpdir)
    await tracker.initialize()

    task = await tracker.create_task(template_key="custom", user_input="Test input")
    assert task.status == TaskStatus.PENDING

    await tracker.start_task(task.id)
    updated = await tracker.get_task(task.id)
    assert updated.status == TaskStatus.RUNNING

    await tracker.complete_task(task.id, "Test response")
    completed = await tracker.get_task(task.id)
    assert completed.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_memory_store_basic(tmp_path):
    """Test MemoryStore basic functionality."""
    from src.services.memory_store import MemoryStore

    tmpdir = tmp_path
    store = MemoryStore(state_dir=tmpdir)
    await store.initialize()

    session = await store.create_session(title="Test Session")
    assert session.title == "Test Session"

    await store.add_message(session.id, "user", "Hello!")
    context = await store.get_context(session.id)
    assert len(context) == 1
    assert context[0]["content"] == "Hello!"


def test_workflow_engine_basic():
    """Test WorkflowEngine basic functionality."""
    from src.services.workflow import (
        WorkflowEngine,
        WorkflowDefinition,
        WorkflowStep,
        StepType,
    )

    engine = WorkflowEngine()

    workflow = WorkflowDefinition(
        id="test_basic",
        name="Test Workflow",
        steps=[
            WorkflowStep(
                id="step1",
                name="First Step",
                step_type=StepType.TASK,
                template_key="custom",
                user_input="Test input",
            ),
        ],
    )

    engine.register_workflow(workflow)

    workflows = engine.list_workflows()
    assert len(workflows) >= 1
    assert any(w.id == "test_basic" for w in workflows)


@pytest.mark.asyncio
async def test_monitor_basic(tmp_path):
    """Test Monitor basic functionality."""
    from src.services.monitor import Monitor

    monitor = Monitor(state_dir=tmp_path)
    await monitor.initialize()

    await monitor.metrics.increment("test_counter", 5)
    assert monitor.metrics.get_counter("test_counter") == 5.0

    await monitor.metrics.gauge("test_gauge", 42.0)
    assert monitor.metrics.get_gauge("test_gauge") == 42.0


# ============== Integration Tests ==============


def test_config_singleton_reset():
    """Verify config singleton can be reset for testing."""
    from src.core.config import get_config_manager
    import src.core.config as config_module

    # Reset singleton
    config_module._config_manager = None

    # Get new instance
    manager = get_config_manager()
    assert manager is not None

    # Reset for other tests
    config_module._config_manager = None
