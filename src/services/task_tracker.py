"""
Task Tracking Service

Provides comprehensive task lifecycle tracking with:
- State transitions
- Event logging
- Dependency management
- Persistence
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Import from models
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.models.task import Task, TaskStatus, TaskPriority


class TaskTrackerEvent(Enum):
    """Events emitted by TaskTracker."""
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    TASK_RETRY = "task_retry"
    DEPENDENCY_RESOLVED = "dependency_resolved"


@dataclass
class TaskListener:
    """Callback registration for task events."""
    event: TaskTrackerEvent
    callback: Callable[[Task], None]
    filter_func: Optional[Callable[[Task], bool]] = None


class TaskTracker:
    """
    Comprehensive task tracking and management.

    Features:
    - SQLite persistence
    - Event-driven notifications
    - Dependency resolution
    - Statistics aggregation
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        state_dir: Optional[Path] = None,
    ) -> None:
        # Resolve database path
        if db_path:
            self._db_path = db_path
        elif state_dir:
            self._db_path = state_dir / "tasks.db"
        else:
            from src.core.config import get_config_manager
            self._db_path = get_config_manager().state_dir / "tasks.db"

        # In-memory task cache
        self._tasks: Dict[str, Task] = {}
        self._listeners: List[TaskListener] = []
        self._lock = asyncio.Lock()

        # Initialize database
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database schema."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    template_key TEXT,
                    user_input TEXT,
                    prompt TEXT,
                    status TEXT,
                    priority INTEGER,
                    response TEXT,
                    error TEXT,
                    created_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_seconds REAL,
                    max_retries INTEGER,
                    retry_count INTEGER,
                    depends_on TEXT,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    timestamp TEXT,
                    status TEXT,
                    message TEXT,
                    metadata TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """)

            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_task_id ON task_events(task_id)")

    def _emit(self, event: TaskTrackerEvent, task: Task) -> None:
        """Emit event to listeners."""
        for listener in self._listeners:
            if listener.event == event:
                if listener.filter_func is None or listener.filter_func(task):
                    try:
                        listener.callback(task)
                    except Exception as e:
                        print(f"Task listener error: {e}")

    def add_listener(
        self,
        event: TaskTrackerEvent,
        callback: Callable[[Task], None],
        filter_func: Optional[Callable[[Task], bool]] = None,
    ) -> None:
        """Register a listener for task events."""
        self._listeners.append(TaskListener(
            event=event,
            callback=callback,
            filter_func=filter_func,
        ))

    async def create_task(
        self,
        template_key: str = "custom",
        user_input: str = "",
        prompt: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
        depends_on: Optional[List[str]] = None,
        max_retries: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """
        Create a new task.

        Args:
            template_key: Template identifier
            user_input: Raw user input
            prompt: Processed prompt
            priority: Task priority
            depends_on: List of task IDs this depends on
            max_retries: Maximum retry attempts
            metadata: Additional metadata

        Returns:
            Created Task object
        """
        task = Task(
            template_key=template_key,
            user_input=user_input,
            prompt=prompt,
            priority=priority,
            depends_on=depends_on or [],
            max_retries=max_retries,
            metadata=metadata or {},
        )

        async with self._lock:
            self._tasks[task.id] = task
            self._persist_task(task)

        self._emit(TaskTrackerEvent.TASK_CREATED, task)
        return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        # Check cache first
        if task_id in self._tasks:
            return self._tasks[task_id]

        # Load from database
        task = self._load_task(task_id)
        if task:
            self._tasks[task_id] = task
        return task

    async def update_task(self, task: Task) -> None:
        """Update task state."""
        async with self._lock:
            self._tasks[task.id] = task
            self._persist_task(task)
            self._persist_events(task)

    async def start_task(self, task_id: str) -> bool:
        """Start a task execution."""
        task = await self.get_task(task_id)
        if not task:
            return False

        # Check dependencies
        if not await self._check_dependencies(task):
            return False

        task.start()
        await self.update_task(task)
        self._emit(TaskTrackerEvent.TASK_STARTED, task)
        return True

    async def complete_task(
        self,
        task_id: str,
        response: str,
    ) -> bool:
        """Mark task as completed."""
        task = await self.get_task(task_id)
        if not task:
            return False

        task.complete(response)
        await self.update_task(task)
        self._emit(TaskTrackerEvent.TASK_COMPLETED, task)
        return True

    async def fail_task(
        self,
        task_id: str,
        error: str,
    ) -> bool:
        """Mark task as failed."""
        task = await self.get_task(task_id)
        if not task:
            return False

        task.fail(error)
        await self.update_task(task)

        if task.status == TaskStatus.RETRYING:
            self._emit(TaskTrackerEvent.TASK_RETRY, task)
        else:
            self._emit(TaskTrackerEvent.TASK_FAILED, task)

        return True

    async def cancel_task(
        self,
        task_id: str,
        reason: str = "",
    ) -> bool:
        """Cancel a task."""
        task = await self.get_task(task_id)
        if not task or task.is_terminal:
            return False

        task.cancel(reason)
        await self.update_task(task)
        self._emit(TaskTrackerEvent.TASK_CANCELLED, task)
        return True

    async def get_pending_tasks(
        self,
        limit: int = 100,
    ) -> List[Task]:
        """Get all pending tasks sorted by priority."""
        tasks = []
        async with self._lock:
            for task in self._tasks.values():
                if task.status == TaskStatus.PENDING:
                    tasks.append(task)

        # Sort by priority (descending) then creation time
        tasks.sort(key=lambda t: (-t.priority.value, t.created_at))
        return tasks[:limit]

    async def get_running_tasks(self) -> List[Task]:
        """Get all currently running tasks."""
        return [
            t for t in self._tasks.values()
            if t.status == TaskStatus.RUNNING
        ]

    async def _check_dependencies(self, task: Task) -> bool:
        """Check if all dependencies are satisfied."""
        for dep_id in task.depends_on:
            dep = await self.get_task(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETED:
                return False
        return True

    def _persist_task(self, task: Task) -> None:
        """Persist task to database."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tasks (
                    id, template_key, user_input, prompt, status, priority,
                    response, error, created_at, started_at, completed_at,
                    duration_seconds, max_retries, retry_count, depends_on, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id,
                task.template_key,
                task.user_input,
                task.prompt,
                task.status.value,
                task.priority.value,
                task.response,
                task.error,
                task.created_at.isoformat(),
                task.started_at.isoformat() if task.started_at else None,
                task.completed_at.isoformat() if task.completed_at else None,
                task.duration_seconds,
                task.max_retries,
                task.retry_count,
                json.dumps(task.depends_on),
                json.dumps(task.metadata),
            ))

    def _persist_events(self, task: Task) -> None:
        """Persist task events to database."""
        with sqlite3.connect(self._db_path) as conn:
            for event in task.events[-10:]:  # Only last 10 events
                conn.execute("""
                    INSERT OR IGNORE INTO task_events (
                        task_id, timestamp, status, message, metadata
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    task.id,
                    event.timestamp.isoformat(),
                    event.status.value,
                    event.message,
                    json.dumps(event.metadata),
                ))

    def _load_task(self, task_id: str) -> Optional[Task]:
        """Load task from database."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            task = Task(
                id=row["id"],
                template_key=row["template_key"],
                user_input=row["user_input"] or "",
                prompt=row["prompt"] or "",
                status=TaskStatus(row["status"]),
                priority=TaskPriority(row["priority"]),
                response=row["response"] or "",
                error=row["error"],
                max_retries=row["max_retries"] or 3,
                retry_count=row["retry_count"] or 0,
                depends_on=json.loads(row["depends_on"] or "[]"),
                metadata=json.loads(row["metadata"] or "{}"),
            )

            # Parse timestamps
            if row["created_at"]:
                task.created_at = datetime.fromisoformat(row["created_at"])
            if row["started_at"]:
                task.started_at = datetime.fromisoformat(row["started_at"])
            if row["completed_at"]:
                task.completed_at = datetime.fromisoformat(row["completed_at"])

            task.duration_seconds = row["duration_seconds"] or 0.0

            return task

    def get_statistics(self) -> Dict[str, Any]:
        """Get task statistics."""
        with sqlite3.connect(self._db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            completed = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status = 'completed'"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status = 'failed'"
            ).fetchone()[0]
            running = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status = 'running'"
            ).fetchone()[0]

            avg_duration = conn.execute(
                "SELECT AVG(duration_seconds) FROM tasks WHERE status = 'completed'"
            ).fetchone()[0] or 0

            return {
                "total_tasks": total,
                "completed": completed,
                "failed": failed,
                "running": running,
                "success_rate": completed / total if total > 0 else 0,
                "avg_duration_seconds": round(avg_duration, 2),
            }
