"""
Task Model

Defines the Task entity with lifecycle tracking and dependencies.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(Enum):
    """Task lifecycle states."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in (self.COMPLETED, self.FAILED, self.CANCELLED)

    def is_active(self) -> bool:
        """Check if task is actively being processed."""
        return self in (self.RUNNING, self.RETRYING)


class TaskPriority(Enum):
    """Task priority levels."""

    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


@dataclass
class TaskEvent:
    """Represents an event in the task lifecycle."""
    __slots__ = ["timestamp", "status", "message", "metadata"]

    timestamp: datetime
    status: TaskStatus
    message: str
    metadata: Dict[str, Any]

    def __init__(
        self,
        status: TaskStatus = TaskStatus.PENDING,
        message: str = "",
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.status = status
        self.message = message
        self.timestamp = timestamp or datetime.now()
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "message": self.message,
            "metadata": self.metadata,
        }


@dataclass
class Task:
    """
    Represents a task to be executed.

    Features:
    - Unique identifier
    - Lifecycle tracking with events
    - Dependency management
    - Retry configuration
    - Result storage
    """
    __slots__ = [
        "id", "template_key", "user_input", "prompt", "status", "priority",
        "response", "error", "created_at", "started_at", "completed_at",
        "duration_seconds", "max_retries", "retry_count", "depends_on",
        "prev_result", "events", "metadata"
    ]

    def __init__(
        self,
        id: Optional[str] = None,
        template_key: str = "custom",
        user_input: str = "",
        prompt: str = "",
        status: TaskStatus = TaskStatus.PENDING,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 3,
        depends_on: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.id = id or uuid.uuid4().hex[:8]
        self.template_key = template_key
        self.user_input = user_input
        self.prompt = prompt
        self.status = status
        self.priority = priority
        self.response = ""
        self.error = None
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.duration_seconds = 0.0
        self.max_retries = max_retries
        self.retry_count = 0
        self.depends_on = depends_on or []
        self.prev_result = ""
        self.events = []
        self.metadata = metadata or {}

        # Record creation event
        self.events.append(
            TaskEvent(
                status=TaskStatus.PENDING,
                message="Task created",
            )
        )

    def add_event(
        self,
        status: TaskStatus,
        message: str = "",
        **metadata: Any,
    ) -> None:
        """Add a lifecycle event."""
        self.events.append(
            TaskEvent(
                status=status,
                message=message,
                metadata=metadata,
            )
        )

    def start(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()
        self.add_event(TaskStatus.RUNNING, "Task started")

    def complete(self, response: str) -> None:
        """Mark task as completed successfully."""
        self.status = TaskStatus.COMPLETED
        self.response = response
        self.completed_at = datetime.now()
        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.add_event(TaskStatus.COMPLETED, "Task completed", response_length=len(response))

    def fail(self, error: str) -> None:
        """Mark task as failed."""
        self.error = error
        self.completed_at = datetime.now()
        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

        if self.retry_count < self.max_retries:
            self.status = TaskStatus.RETRYING
            self.retry_count += 1
            self.add_event(
                TaskStatus.RETRYING,
                f"Task failed, retry {self.retry_count}/{self.max_retries}",
                error=error,
            )
        else:
            self.status = TaskStatus.FAILED
            self.add_event(TaskStatus.FAILED, "Task failed permanently", error=error)

    def cancel(self, reason: str = "") -> None:
        """Cancel the task."""
        self.status = TaskStatus.CANCELLED
        self.completed_at = datetime.now()
        self.add_event(TaskStatus.CANCELLED, reason or "Task cancelled")

    def queue(self) -> None:
        """Mark task as queued."""
        self.status = TaskStatus.QUEUED
        self.add_event(TaskStatus.QUEUED, "Task queued")

    @property
    def is_ready(self) -> bool:
        """Check if task is ready to run (no pending dependencies)."""
        return self.status == TaskStatus.PENDING or self.status == TaskStatus.QUEUED

    @property
    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status.is_terminal()

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time since start."""
        if self.started_at is None:
            return 0.0
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize task to dictionary."""
        return {
            "id": self.id,
            "template_key": self.template_key,
            "user_input": self.user_input[:100] if self.user_input else "",
            "prompt": self.prompt[:100] if self.prompt else "",
            "status": self.status.value,
            "priority": self.priority.value,
            "response": self.response[:500] if self.response else "",
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "duration_seconds": self.duration_seconds,
            "retry_count": self.retry_count,
            "depends_on": self.depends_on,
            "event_count": len(self.events),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Deserialize task from dictionary."""
        task = cls(
            id=data.get("id"),
            template_key=data.get("template_key", "custom"),
            user_input=data.get("user_input", ""),
            prompt=data.get("prompt", ""),
            status=TaskStatus(data.get("status", "pending")),
            priority=TaskPriority(data.get("priority", 5)),
            max_retries=data.get("max_retries", 3),
            depends_on=data.get("depends_on", []),
            metadata=data.get("metadata", {}),
        )

        # Parse additional persistent fields
        if data.get("created_at"):
            task.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("started_at"):
            task.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            task.completed_at = datetime.fromisoformat(data["completed_at"])

        task.response = data.get("response", "")
        task.error = data.get("error")
        task.duration_seconds = data.get("duration_seconds", 0.0)
        task.retry_count = data.get("retry_count", 0)

        return task
