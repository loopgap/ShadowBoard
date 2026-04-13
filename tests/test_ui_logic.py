import pytest
import asyncio
from src.ui.state import QueueItem, TASK_QUEUE, get_queue_lock, get_login_lock

@pytest.mark.asyncio
async def test_queue_lock_singleton():
    lock1 = get_queue_lock()
    lock2 = get_queue_lock()
    assert lock1 is lock2
    assert isinstance(lock1, asyncio.Lock)

@pytest.mark.asyncio
async def test_login_lock_singleton():
    lock1 = get_login_lock()
    lock2 = get_login_lock()
    assert lock1 is lock2
    assert isinstance(lock1, asyncio.Lock)

def test_queue_item_creation():
    item = QueueItem(template_label="Test", user_input="Hello")
    assert item.template_label == "Test"
    assert item.user_input == "Hello"
    assert item.status == "等待中"
    assert len(item.id) == 8

@pytest.mark.asyncio
async def test_concurrent_queue_access():
    lock = get_queue_lock()
    TASK_QUEUE.clear()
    
    async def add_item(i):
        async with lock:
            TASK_QUEUE.append(QueueItem(user_input=f"item {i}"))
            
    await asyncio.gather(*(add_item(i) for i in range(10)))
    
    assert len(TASK_QUEUE) == 10
    for i in range(10):
        assert any(item.user_input == f"item {i}" for item in TASK_QUEUE)
