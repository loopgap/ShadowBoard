from __future__ import annotations
from unittest.mock import MagicMock, AsyncMock
import pytest
from src.ui.state import TASK_QUEUE
from src.ui.tabs import queue_tab

@pytest.fixture(autouse=True)
def setup_teardown():
    TASK_QUEUE.clear()
    yield
    TASK_QUEUE.clear()

@pytest.mark.asyncio
async def test_add_to_queue_and_process(monkeypatch):
    # Mock task tracker
    mock_tracker = MagicMock()
    
    async def fake_create(*args, **kwargs):
        mock = MagicMock()
        mock.id = "t1"
        return mock
        
    monkeypatch.setattr(queue_tab, "get_task_tracker", lambda: mock_tracker)
    monkeypatch.setattr(mock_tracker, "create_task", fake_create)
    monkeypatch.setattr(mock_tracker, "start_task", AsyncMock())
    monkeypatch.setattr(mock_tracker, "complete_task", AsyncMock())
    
    # Mock monitor
    mock_monitor = MagicMock()
    monkeypatch.setattr(queue_tab, "get_monitor", lambda: mock_monitor)

    # Mock core
    monkeypatch.setattr(queue_tab.core, "build_prompt", lambda k, i: f"{k}:{i}")

    msg = await queue_tab.add_to_queue("市场分析 (CMO)", "hello")
    assert "t1" in msg
    assert len(TASK_QUEUE) == 1

    # Mock core.send_with_retry
    async def fake_send(cfg, prompt):
        yield "done"
    monkeypatch.setattr(queue_tab.core, "send_with_retry", fake_send)
    monkeypatch.setattr(queue_tab.core, "load_config", lambda: {"confirm_before_send": False})
    monkeypatch.setattr(queue_tab.core, "append_history", MagicMock())

    status, table = await queue_tab.process_queue_once()
    assert len(status) > 0
    # table row: [id, added_at, label, input, status, result]
    assert len(table[0][4]) > 0
    assert "done" in table[0][5]

@pytest.mark.asyncio
async def test_process_queue_failure(monkeypatch):
    # Mock task tracker
    mock_tracker = MagicMock()
    async def fake_create(*args, **kwargs):
        mock = MagicMock()
        mock.id = "t2"
        return mock
    monkeypatch.setattr(queue_tab, "get_task_tracker", lambda: mock_tracker)
    monkeypatch.setattr(mock_tracker, "create_task", fake_create)
    monkeypatch.setattr(mock_tracker, "start_task", AsyncMock())
    monkeypatch.setattr(mock_tracker, "fail_task", AsyncMock())
    
    # Mock monitor
    mock_monitor = MagicMock()
    monkeypatch.setattr(queue_tab, "get_monitor", lambda: mock_monitor)
    
    # Mock core
    monkeypatch.setattr(queue_tab.core, "build_prompt", lambda k, i: f"{k}:{i}")

    await queue_tab.add_to_queue("市场分析 (CMO)", "fail me")
    
    async def boom(cfg, prompt):
        raise RuntimeError("boom")
        yield ""
    monkeypatch.setattr(queue_tab.core, "send_with_retry", boom)
    monkeypatch.setattr(queue_tab.core, "load_config", lambda: {"confirm_before_send": False})
    monkeypatch.setattr(queue_tab.core, "append_history", MagicMock())

    status, table = await queue_tab.process_queue_once()
    assert len(status) > 0
    assert "Error" in table[0][5]

@pytest.mark.asyncio
async def test_process_empty_queue():
    status, table = await queue_tab.process_queue_once()
    assert "没有等待执行的任务" in status
    assert len(table) == 0
