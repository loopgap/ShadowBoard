"""
Memory Storage Service (Async)

Provides conversation memory management with:
- Session-based memory storage
- Context summarization
- Semantic search (optional)
- Persistence
"""

from __future__ import annotations

import json
import aiosqlite
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.models.session import Session, SessionState, Message
from src.utils.i18n import t


class MemoryStore:
    """
    Manages conversation memory and sessions (Async version).

    Features:
    - SQLite persistence via aiosqlite
    - Session management
    - Message history
    - Context window management
    - LRU cache eviction (max 100 sessions in memory)
    """

    MAX_SESSIONS = 100

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

        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._current_session_id: Optional[str] = None

    async def initialize(self) -> None:
        """Initialize database schema asynchronously."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("""
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

            await conn.execute("""
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

            await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at)")
            await conn.commit()

    def _evict_if_needed(self) -> None:
        """LRU eviction: remove oldest session when over limit."""
        while len(self._sessions) > self.MAX_SESSIONS:
            self._sessions.popitem(last=False)

    def set_session(self, session_id: str, session: Session) -> None:
        """Set session with LRU eviction."""
        if session_id in self._sessions:
            del self._sessions[session_id]
        self._sessions[session_id] = session
        self._evict_if_needed()

    async def create_session(
        self,
        title: str = "",
        provider_key: str = "deepseek",
    ) -> Session:
        """Create a new session (Async)."""
        session = Session(
            title=title,
            provider_key=provider_key,
        )
        self.set_session(session.id, session)
        await self._persist_session(session)
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID (Async)."""
        if session_id in self._sessions:
            return self._sessions[session_id]

        session = await self._load_session(session_id)
        if session:
            self.set_session(session_id, session)
        return session

    async def get_current_session(self) -> Optional[Session]:
        """Get the current active session (Async)."""
        if self._current_session_id:
            return await self.get_session(self._current_session_id)
        return None

    async def set_current_session(self, session_id: str) -> bool:
        """Set the current active session (Async)."""
        session = await self.get_session(session_id)
        if session:
            self._current_session_id = session_id
            return True
        return False

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        **metadata: Any,
    ) -> Optional[Message]:
        """Add a message to a session (Async)."""
        session = await self.get_session(session_id)
        if not session:
            return None

        message = session.add_message(role, content, **metadata)
        await self._persist_message(session_id, message)
        await self._persist_session(session)
        return message

    async def get_context(
        self,
        session_id: str,
        max_messages: int = 20,
    ) -> List[Dict[str, str]]:
        """
        Get conversation context for AI input (Async).

        Returns list of {role, content} dicts.
        """
        session = await self.get_session(session_id)
        if not session:
            return []

        messages = session.get_context_window(max_messages)
        return [{"role": m.role, "content": m.content} for m in messages]

    async def search_messages(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search messages by content (Async)."""
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row

            if session_id:
                async with conn.execute(
                    """
                    SELECT * FROM messages
                    WHERE session_id = ? AND content LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """,
                    (session_id, f"%{query}%", limit),
                ) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with conn.execute(
                    """
                    SELECT * FROM messages
                    WHERE content LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """,
                    (f"%{query}%", limit),
                ) as cursor:
                    rows = await cursor.fetchall()

            return [dict(row) for row in rows]

    async def list_sessions(
        self,
        state: Optional[SessionState] = None,
        limit: int = 50,
    ) -> List[Session]:
        """List sessions, optionally filtered by state (Async)."""
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row

            if state:
                async with conn.execute(
                    "SELECT * FROM sessions WHERE state = ? ORDER BY updated_at DESC LIMIT ?",
                    (state.value, limit),
                ) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)) as cursor:
                    rows = await cursor.fetchall()

            sessions = []
            for row in rows:
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
                sessions.append(session)
            return sessions

    async def archive_session(self, session_id: str) -> bool:
        """Archive a session (Async)."""
        session = await self.get_session(session_id)
        if not session:
            return False

        session.archive()
        await self._persist_session(session)
        return True

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and its messages (Async)."""
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await conn.commit()

        if session_id in self._sessions:
            del self._sessions[session_id]

        if self._current_session_id == session_id:
            self._current_session_id = None

        return True

    async def _persist_session(self, session: Session) -> None:
        """Persist session to database (Async)."""
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO sessions (
                    id, title, provider_key, state, summary,
                    created_at, updated_at, last_message_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    session.id,
                    session.title,
                    session.provider_key,
                    session.state.value,
                    session.summary,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                    (session.last_message_at.isoformat() if session.last_message_at else None),
                    json.dumps(session.metadata),
                ),
            )
            await conn.commit()

    async def _persist_message(self, session_id: str, message: Message) -> None:
        """Persist message to database (Async)."""
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO messages (session_id, role, content, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    session_id,
                    message.role,
                    message.content,
                    message.timestamp.isoformat(),
                    json.dumps(message.metadata),
                ),
            )
            await conn.commit()

    async def _load_session(self, session_id: str) -> Optional[Session]:
        """Load session from database (Async)."""
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()

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
            async with conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ) as cursor:
                for msg_row in await cursor.fetchall():
                    session.messages.append(
                        Message(
                            role=msg_row["role"],
                            content=msg_row["content"],
                            timestamp=datetime.fromisoformat(msg_row["timestamp"]),
                            metadata=json.loads(msg_row["metadata"] or "{}"),
                        )
                    )

            return session

    async def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics (Async)."""
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute("SELECT COUNT(*) FROM sessions") as cursor:
                sessions = (await cursor.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM messages") as cursor:
                messages = (await cursor.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM sessions WHERE state = 'active'") as cursor:
                active = (await cursor.fetchone())[0]

            return {
                "total_sessions": sessions,
                "total_messages": messages,
                "active_sessions": active,
            }

    async def vacuum(self) -> None:
        """Maintenance: Compact database file."""
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("VACUUM")


class SessionManager:
    """
    High-level session management interface (Async).

    Provides convenience methods for common session operations.
    """

    def __init__(self, store: Optional[MemoryStore] = None) -> None:
        self._store = store or MemoryStore()

    async def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        provider_key: str = "deepseek",
    ) -> Session:
        """Get existing session or create a new one (Async)."""
        if session_id:
            session = await self._store.get_session(session_id)
            if session:
                return session

        session = await self._store.create_session(provider_key=provider_key)
        await self._store.set_current_session(session.id)
        return session

    async def remember(
        self,
        role: str,
        content: str,
        session_id: Optional[str] = None,
    ) -> Message:
        """
        Add a memory (message) to the session (Async).

        Convenience method for adding messages.
        """
        session = await self._store.get_current_session()

        if not session:
            if session_id:
                session = await self._store.get_session(session_id)
            if not session:
                session = await self._store.create_session()
                await self._store.set_current_session(session.id)

        message = await self._store.add_message(session.id, role, content)
        if not message:
            raise RuntimeError(t("errors.message_add_failed", session_id=session.id))

        return message

    async def recall(
        self,
        max_messages: int = 20,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Recall recent conversation context (Async).

        Returns list of {role, content} dicts.
        """
        target_id = session_id or self._store._current_session_id
        if not target_id:
            return []

        return await self._store.get_context(target_id, max_messages)

    async def search(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search through memories (Async)."""
        return await self._store.search_messages(query, session_id)

    async def list_sessions(self, limit: int = 20) -> List[Session]:
        """List recent sessions (Async)."""
        return await self._store.list_sessions(limit=limit)

    async def switch_session(self, session_id: str) -> bool:
        """Switch to a different session (Async)."""
        return await self._store.set_current_session(session_id)

    async def clear_current_session(self) -> bool:
        """Clear the current session reference (Async)."""
        if self._store._current_session_id:
            return await self._store.archive_session(self._store._current_session_id)
        return False
