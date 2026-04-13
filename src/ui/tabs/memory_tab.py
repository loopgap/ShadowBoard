"""
Memory Tab Logic and Event Handlers
"""

from __future__ import annotations

import json
from typing import Any, List, Tuple

from src.core.dependencies import get_memory_store, get_session_manager

def create_session(title: str) -> Tuple[str, List[List[Any]]]:
    """Create a new session."""
    manager = get_session_manager()
    session = manager._store.create_session(title=title)
    manager._store.set_current_session(session.id)
    # Return success message and updated session list
    sessions = manager.list_sessions()
    session_list = [[s.id, s.title, s.message_count, s.state.value, s.updated_at.strftime("%Y-%m-%d %H:%M")] for s in sessions]
    return f"Session created: {session.id}", session_list

def list_sessions() -> List[List[Any]]:
    """List all sessions."""
    manager = get_session_manager()
    sessions = manager.list_sessions()
    return [[s.id, s.title, s.message_count, s.state.value, s.updated_at.strftime("%Y-%m-%d %H:%M")] for s in sessions]

def get_session_context(session_id: str) -> str:
    """Get context from a session."""
    if not session_id or not session_id.strip():
        return "Please enter a session ID"
    store = get_memory_store()
    context = store.get_context(session_id.strip())
    if not context:
        return "No messages in session or session not found"
    return "\n".join([f"[{m['role']}]: {m['content'][:200]}{'...' if len(m['content']) > 200 else ''}" for m in context])

def switch_session(session_id: str) -> Tuple[str, str]:
    """Switch to a different session."""
    if not session_id or not session_id.strip():
        return "Please enter a session ID", ""
    manager = get_session_manager()
    if manager.switch_session(session_id.strip()):
        context = get_session_context(session_id.strip())
        return f"Switched to session: {session_id}", context
    return f"Failed to switch to session: {session_id}", ""

def get_memory_statistics() -> str:
    """Get memory/session statistics."""
    store = get_memory_store()
    stats = store.get_statistics()
    return json.dumps(stats, ensure_ascii=False, indent=2)
