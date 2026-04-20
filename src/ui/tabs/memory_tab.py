"""
Memory Tab Logic and Event Handlers (Async)
"""

from __future__ import annotations

import json
from typing import Any, List, Tuple

from src.core.dependencies import get_memory_store, get_session_manager


async def create_session(title: str) -> Tuple[str, List[List[Any]]]:
    """Create a new session (Async)."""
    manager = get_session_manager()
    session = await manager._store.create_session(title=title)
    await manager._store.set_current_session(session.id)
    # Return success message and updated session list
    sessions = await manager.list_sessions()
    session_list = [
        [
            s.id,
            s.title,
            s.message_count,
            s.state.value,
            s.updated_at.strftime("%Y-%m-%d %H:%M"),
        ]
        for s in sessions
    ]
    return f"Session created: {session.id}", session_list


async def list_sessions() -> List[List[Any]]:
    """List all sessions (Async)."""
    manager = get_session_manager()
    sessions = await manager.list_sessions()
    return [
        [
            s.id,
            s.title,
            s.message_count,
            s.state.value,
            s.updated_at.strftime("%Y-%m-%d %H:%M"),
        ]
        for s in sessions
    ]


async def get_session_context(session_id: str) -> str:
    """Get context from a session (Async)."""
    if not session_id or not session_id.strip():
        return "Please enter a session ID"
    store = get_memory_store()
    context = await store.get_context(session_id.strip())
    if not context:
        return "No messages in session or session not found"
    return "\n".join(
        [f"[{m['role']}]: {m['content'][:200]}{'...' if len(m['content']) > 200 else ''}" for m in context]
    )


async def switch_session(session_id: str) -> Tuple[str, str]:
    """Switch to a different session (Async)."""
    if not session_id or not session_id.strip():
        return "Please enter a session ID", ""
    manager = get_session_manager()
    if await manager.switch_session(session_id.strip()):
        context = await get_session_context(session_id.strip())
        return f"Switched to session: {session_id}", context
    return f"Failed to switch to session: {session_id}", ""


async def get_memory_statistics() -> str:
    """Get memory/session statistics (Async)."""
    store = get_memory_store()
    stats = await store.get_statistics()
    return json.dumps(stats, ensure_ascii=False, indent=2)
