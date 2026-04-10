"""
Memory Storage Service

Provides conversation memory management with:
- Session-based memory storage
- Context summarization
- Semantic search (optional)
- Persistence
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.models.session import Session, SessionState, Message


class MemoryStore:
    """
    Manages conversation memory and sessions.

    Features:
    - SQLite persistence
    - Session management
    - Message history
    - Context window management
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        state_dir: Optional[Path] = None,
    ) -> None:
        if db_path:
            self._db_path = db_path
        elif state_dir:
            self._db_path = state_dir / "memory.db"
        else:
            from src.core.config import get_config_manager
            self._db_path = get_config_manager().state_dir / "memory.db"

        self._sessions: Dict[str, Session] = {}
        self._current_session_id: Optional[str] = None

        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    provider_key TEXT,
                    state TEXT,
                    summary TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    last_message_at TEXT,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at)")

    def create_session(
        self,
        title: str = "",
        provider_key: str = "deepseek",
    ) -> Session:
        """Create a new session."""
        session = Session(
            title=title,
            provider_key=provider_key,
        )
        self._sessions[session.id] = session
        self._persist_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        if session_id in self._sessions:
            return self._sessions[session_id]

        session = self._load_session(session_id)
        if session:
            self._sessions[session_id] = session
        return session

    def get_current_session(self) -> Optional[Session]:
        """Get the current active session."""
        if self._current_session_id:
            return self.get_session(self._current_session_id)
        return None

    def set_current_session(self, session_id: str) -> bool:
        """Set the current active session."""
        session = self.get_session(session_id)
        if session:
            self._current_session_id = session_id
            return True
        return False

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        **metadata: Any,
    ) -> Optional[Message]:
        """Add a message to a session."""
        session = self.get_session(session_id)
        if not session:
            return None

        message = session.add_message(role, content, **metadata)
        self._persist_message(session_id, message)
        self._persist_session(session)
        return message

    def get_context(
        self,
        session_id: str,
        max_messages: int = 20,
    ) -> List[Dict[str, str]]:
        """
        Get conversation context for AI input.

        Returns list of {role, content} dicts.
        """
        session = self.get_session(session_id)
        if not session:
            return []

        messages = session.get_context_window(max_messages)
        return [{"role": m.role, "content": m.content} for m in messages]

    def search_messages(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search messages by content."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row

            if session_id:
                cursor = conn.execute("""
                    SELECT * FROM messages
                    WHERE session_id = ? AND content LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (session_id, f"%{query}%", limit))
            else:
                cursor = conn.execute("""
                    SELECT * FROM messages
                    WHERE content LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (f"%{query}%", limit))

            return [dict(row) for row in cursor.fetchall()]

    def list_sessions(
        self,
        state: Optional[SessionState] = None,
        limit: int = 50,
    ) -> List[Session]:
        """List sessions, optionally filtered by state."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row

            if state:
                cursor = conn.execute(
                    "SELECT id FROM sessions WHERE state = ? ORDER BY updated_at DESC LIMIT ?",
                    (state.value, limit)
                )
            else:
                cursor = conn.execute(
                    "SELECT id FROM sessions ORDER BY updated_at DESC LIMIT ?",
                    (limit,)
                )

            session_ids = [row["id"] for row in cursor.fetchall()]
            return [self.get_session(sid) for sid in session_ids if self.get_session(sid)]

    def archive_session(self, session_id: str) -> bool:
        """Archive a session."""
        session = self.get_session(session_id)
        if not session:
            return False

        session.archive()
        self._persist_session(session)
        return True

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its messages."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

        if session_id in self._sessions:
            del self._sessions[session_id]

        if self._current_session_id == session_id:
            self._current_session_id = None

        return True

    def _persist_session(self, session: Session) -> None:
        """Persist session to database."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sessions (
                    id, title, provider_key, state, summary,
                    created_at, updated_at, last_message_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.id,
                session.title,
                session.provider_key,
                session.state.value,
                session.summary,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                session.last_message_at.isoformat() if session.last_message_at else None,
                json.dumps(session.metadata),
            ))

    def _persist_message(self, session_id: str, message: Message) -> None:
        """Persist message to database."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                INSERT INTO messages (session_id, role, content, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session_id,
                message.role,
                message.content,
                message.timestamp.isoformat(),
                json.dumps(message.metadata),
            ))

    def _load_session(self, session_id: str) -> Optional[Session]:
        """Load session from database."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            session = Session(
                id=row["id"],
                title=row["title"] or "",
                provider_key=row["provider_key"] or "deepseek",
                state=SessionState(row["state"] or "active"),
                summary=row["summary"] or "",
                metadata=json.loads(row["metadata"] or "{}"),
            )

            if row["created_at"]:
                session.created_at = datetime.fromisoformat(row["created_at"])
            if row["updated_at"]:
                session.updated_at = datetime.fromisoformat(row["updated_at"])
            if row["last_message_at"]:
                session.last_message_at = datetime.fromisoformat(row["last_message_at"])

            # Load messages
            cursor = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            )
            for msg_row in cursor.fetchall():
                session.messages.append(Message(
                    role=msg_row["role"],
                    content=msg_row["content"],
                    timestamp=datetime.fromisoformat(msg_row["timestamp"]),
                    metadata=json.loads(msg_row["metadata"] or "{}"),
                ))

            return session

    def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics."""
        with sqlite3.connect(self._db_path) as conn:
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE state = 'active'"
            ).fetchone()[0]

            return {
                "total_sessions": sessions,
                "total_messages": messages,
                "active_sessions": active,
            }


class SessionManager:
    """
    High-level session management interface.

    Provides convenience methods for common session operations.
    """

    def __init__(self, store: Optional[MemoryStore] = None) -> None:
        self._store = store or MemoryStore()

    def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        provider_key: str = "deepseek",
    ) -> Session:
        """Get existing session or create a new one."""
        if session_id:
            session = self._store.get_session(session_id)
            if session:
                return session

        session = self._store.create_session(provider_key=provider_key)
        self._store.set_current_session(session.id)
        return session

    def remember(
        self,
        role: str,
        content: str,
        session_id: Optional[str] = None,
    ) -> Message:
        """
        Add a memory (message) to the session.

        Convenience method for adding messages.
        """
        session = self._store.get_current_session()

        if not session:
            if session_id:
                session = self._store.get_session(session_id)
            if not session:
                session = self._store.create_session()
                self._store.set_current_session(session.id)

        message = self._store.add_message(session.id, role, content)
        if not message:
            raise RuntimeError(f"Failed to add message to session {session.id}")

        return message

    def recall(
        self,
        max_messages: int = 20,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Recall recent conversation context.

        Returns list of {role, content} dicts.
        """
        target_id = session_id or self._store._current_session_id
        if not target_id:
            return []

        return self._store.get_context(target_id, max_messages)

    def search(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search through memories."""
        return self._store.search_messages(query, session_id)

    def list_sessions(self, limit: int = 20) -> List[Session]:
        """List recent sessions."""
        return self._store.list_sessions(limit=limit)

    def switch_session(self, session_id: str) -> bool:
        """Switch to a different session."""
        return self._store.set_current_session(session_id)

    def clear_current_session(self) -> bool:
        """Clear the current session reference."""
        if self._store._current_session_id:
            return self._store.archive_session(self._store._current_session_id)
        return False
