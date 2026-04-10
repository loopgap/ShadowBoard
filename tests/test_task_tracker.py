"""
Tests for Task Tracking Service
"""

from __future__ import annotations

import asyncio
import pytest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.task_tracker import TaskTracker, TaskTrackerEvent
from src.models.task import TaskStatus, TaskPriority


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def tracker(temp_db):
    """Create a TaskTracker instance with temporary database."""
    return TaskTracker(state_dir=temp_db)


def test_create_task(tracker):
    """Test task creation."""
    async def run():
        task = await tracker.create_task(
            template_key="summary",
            user_input="Test input",
            prompt="Test prompt",
        )
        assert task.id is not None
        assert task.template_key == "summary"
        assert task.status == TaskStatus.PENDING
        return task

    return asyncio.run(run())


def test_task_lifecycle(tracker):
    """Test complete task lifecycle."""
    async def run():
        # Create
        task = await tracker.create_task(user_input="Test")
        assert task.status == TaskStatus.PENDING

        # Start
        await tracker.start_task(task.id)
        updated = await tracker.get_task(task.id)
        assert updated.status == TaskStatus.RUNNING
        assert updated.started_at is not None

        # Complete
        await tracker.complete_task(task.id, "Test response")
        completed = await tracker.get_task(task.id)
        assert completed.status == TaskStatus.COMPLETED
        assert completed.response == "Test response"
        assert completed.duration_seconds > 0

    asyncio.run(run())


def test_task_failure_with_retry(tracker):
    """Test task failure and retry logic."""
    async def run():
        task = await tracker.create_task(user_input="Test", max_retries=2)
        await tracker.start_task(task.id)
        await tracker.fail_task(task.id, "First error")

        # Should be retrying
        failed = await tracker.get_task(task.id)
        assert failed.status == TaskStatus.RETRYING
        assert failed.retry_count == 1

        # Fail again
        await tracker.start_task(task.id)
        await tracker.fail_task(task.id, "Second error")

        # Still retrying
        retrying = await tracker.get_task(task.id)
        assert retrying.status == TaskStatus.RETRYING
        assert retrying.retry_count == 2

        # Final failure
        await tracker.start_task(task.id)
        await tracker.fail_task(task.id, "Final error")

        # Should be failed permanently
        final = await tracker.get_task(task.id)
        assert final.status == TaskStatus.FAILED

    asyncio.run(run())


def test_task_cancellation(tracker):
    """Test task cancellation."""
    async def run():
        task = await tracker.create_task(user_input="Test")
        await tracker.cancel_task(task.id, "User requested")

        cancelled = await tracker.get_task(task.id)
        assert cancelled.status == TaskStatus.CANCELLED

    asyncio.run(run())


def test_statistics(tracker):
    """Test task statistics."""
    async def run():
        # Create and complete some tasks
        for i in range(3):
            task = await tracker.create_task(user_input=f"Test {i}")
            await tracker.start_task(task.id)
            if i < 2:
                await tracker.complete_task(task.id, f"Response {i}")
            else:
                # Task with no retries will go to FAILED status
                task.max_retries = 0
                await tracker.fail_task(task.id, "Error")

        stats = tracker.get_statistics()
        assert stats["total_tasks"] == 3
        assert stats["completed"] == 2
        assert stats["failed"] == 1
        assert stats["success_rate"] == 2/3

    asyncio.run(run())


def test_event_listeners(tracker):
    """Test event listener functionality."""
    events = []

    def listener(task):
        events.append(task.status)

    tracker.add_listener(TaskTrackerEvent.TASK_COMPLETED, listener)

    async def run():
        task = await tracker.create_task(user_input="Test")
        await tracker.start_task(task.id)
        await tracker.complete_task(task.id, "Done")

    asyncio.run(run())

    assert TaskStatus.COMPLETED in events


def test_get_pending_tasks(tracker):
    """Test getting pending tasks."""
    async def run():
        # Create multiple tasks with different priorities
        for i in range(3):
            priority = TaskPriority.HIGH if i == 0 else TaskPriority.NORMAL
            await tracker.create_task(
                user_input=f"Test {i}",
                priority=priority
            )

        pending = await tracker.get_pending_tasks()
        assert len(pending) == 3
        # First should be HIGH priority
        assert pending[0].priority == TaskPriority.HIGH

    asyncio.run(run())
