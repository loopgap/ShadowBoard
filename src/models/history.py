"""
History Model

Defines the HistoryEntry entity for task execution records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class HistoryEntry:
    """
    Represents a historical record of task execution.

    Used for auditing, analytics, and debugging.
    """

    # Core fields
    time: datetime = field(default_factory=datetime.now)
    template: str = ""
    input_chars: int = 0
    response_chars: int = 0
    duration_seconds: float = 0.0
    ok: bool = True

    # Error information
    error: Optional[str] = None

    # Additional context
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    provider_key: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "time": self.time.isoformat(timespec="seconds"),
            "template": self.template,
            "input_chars": self.input_chars,
            "response_chars": self.response_chars,
            "duration_seconds": round(self.duration_seconds, 2),
            "ok": self.ok,
            "error": self.error,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "provider_key": self.provider_key,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryEntry":
        """Deserialize from dictionary."""
        entry = cls(
            template=data.get("template", ""),
            input_chars=data.get("input_chars", 0),
            response_chars=data.get("response_chars", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
            ok=data.get("ok", True),
            error=data.get("error"),
            task_id=data.get("task_id"),
            session_id=data.get("session_id"),
            provider_key=data.get("provider_key"),
            metadata=data.get("metadata", {}),
        )

        # Parse timestamp
        if data.get("time"):
            try:
                entry.time = datetime.fromisoformat(data["time"])
            except (ValueError, TypeError):
                pass

        return entry

    @classmethod
    def from_task(cls, task: Any) -> "HistoryEntry":
        """Create history entry from a completed task."""
        # Import here to avoid circular dependency
        from .task import Task, TaskStatus

        if not isinstance(task, Task):
            raise TypeError(f"Expected Task, got {type(task)}")

        return cls(
            time=task.completed_at or datetime.now(),
            template=task.template_key,
            input_chars=len(task.user_input),
            response_chars=len(task.response),
            duration_seconds=task.duration_seconds,
            ok=task.status == TaskStatus.COMPLETED,
            error=task.error if task.status == TaskStatus.FAILED else None,
            task_id=task.id,
            metadata={"retry_count": task.retry_count},
        )
