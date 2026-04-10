"""
Session Model

Defines the Session entity for conversation context management.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class SessionState(Enum):
    """Session lifecycle states."""
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass
class Message:
    """Represents a single message in a session."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Session:
    """
    Represents a conversation session with memory context.

    Features:
    - Unique identifier
    - Message history
    - Context summarization
    - Provider association
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str = ""
    provider_key: str = "deepseek"

    # State
    state: SessionState = SessionState.ACTIVE

    # Messages
    messages: List[Message] = field(default_factory=list)

    # Context summary (for long conversations)
    summary: str = ""
    summary_created_at: Optional[datetime] = None

    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_message_at: Optional[datetime] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_message(
        self,
        role: str,
        content: str,
        **metadata: Any,
    ) -> Message:
        """Add a message to the session."""
        message = Message(
            role=role,
            content=content,
            metadata=metadata,
        )
        self.messages.append(message)
        self.updated_at = datetime.now()
        self.last_message_at = message.timestamp

        # Update title from first user message
        if not self.title and role == "user":
            self.title = content[:50] + ("..." if len(content) > 50 else "")

        return message

    def get_context_window(self, max_messages: int = 20) -> List[Message]:
        """Get recent messages for context window."""
        if len(self.messages) <= max_messages:
            return self.messages
        return self.messages[-max_messages:]

    def get_token_count_estimate(self) -> int:
        """Estimate token count (rough approximation)."""
        # Rough estimate: ~4 characters per token
        total_chars = sum(len(m.content) for m in self.messages)
        if self.summary:
            total_chars += len(self.summary)
        return total_chars // 4

    def archive(self) -> None:
        """Archive the session."""
        self.state = SessionState.ARCHIVED
        self.updated_at = datetime.now()

    def pause(self) -> None:
        """Pause the session."""
        self.state = SessionState.PAUSED
        self.updated_at = datetime.now()

    def resume(self) -> None:
        """Resume a paused session."""
        self.state = SessionState.ACTIVE
        self.updated_at = datetime.now()

    @property
    def message_count(self) -> int:
        """Get total message count."""
        return len(self.messages)

    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        return self.state == SessionState.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "provider_key": self.provider_key,
            "state": self.state.value,
            "message_count": len(self.messages),
            "summary": self.summary,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "metadata": self.metadata,
        }

    def to_full_dict(self) -> Dict[str, Any]:
        """Serialize session with all messages."""
        data = self.to_dict()
        data["messages"] = [m.to_dict() for m in self.messages]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Deserialize session from dictionary."""
        session = cls(
            id=data.get("id", uuid.uuid4().hex[:8]),
            title=data.get("title", ""),
            provider_key=data.get("provider_key", "deepseek"),
            state=SessionState(data.get("state", "active")),
            summary=data.get("summary", ""),
            metadata=data.get("metadata", {}),
        )

        # Parse timestamps
        if data.get("created_at"):
            session.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            session.updated_at = datetime.fromisoformat(data["updated_at"])
        if data.get("last_message_at"):
            session.last_message_at = datetime.fromisoformat(data["last_message_at"])

        # Parse messages
        for msg_data in data.get("messages", []):
            session.messages.append(Message.from_dict(msg_data))

        return session
