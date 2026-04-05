from __future__ import annotations

import pytest
from unittest.mock import MagicMock
import web_app

@pytest.mark.asyncio
async def test_queue_flow(monkeypatch):
    # Mock core for send_with_retry
    async def fake_send_ok(cfg, prompt):
        yield "result"
    
    monkeypatch.setattr(web_app.core, "send_with_retry", fake_send_ok)
    monkeypatch.setattr(web_app.core, "load_config", lambda: {})
    monkeypatch.setattr(web_app.core, "build_prompt", lambda k, v: v)
    monkeypatch.setattr(web_app.core, "append_history", MagicMock())
    
    # Clear queue
    await web_app._clear_queue()
    
    # Add to queue
    msg = await web_app._add_to_queue("摘要总结", "hello")
    assert "已成功加入" in msg
    assert len(web_app.TASK_QUEUE) == 1
    
    # Process once
    status, table = await web_app._process_queue_once()
    assert "已处理完毕" in status
    assert table[0][4] == "执行成功"
    assert table[0][5] == "result"

@pytest.mark.asyncio
async def test_queue_fail(monkeypatch):
    async def fake_send_fail(cfg, prompt):
        raise RuntimeError("boom")
        yield ""
        
    monkeypatch.setattr(web_app.core, "send_with_retry", fake_send_fail)
    monkeypatch.setattr(web_app.core, "load_config", lambda: {})
    monkeypatch.setattr(web_app.core, "build_prompt", lambda k, v: v)
    monkeypatch.setattr(web_app.core, "append_history", MagicMock())
    
    await web_app._clear_queue()
    await web_app._add_to_queue("摘要总结", "fail me")
    
    status, table = await web_app._process_queue_once()
    assert "已处理完毕" in status
    assert table[0][4] == "执行失败"
    assert "boom" in table[0][5]

@pytest.mark.asyncio
async def test_process_empty_queue():
    await web_app._clear_queue()
    status, _ = await web_app._process_queue_once()
    assert "没有等待" in status
