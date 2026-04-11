"""
Tests for Memory Storage Service
"""

from __future__ import annotations

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.memory_store import MemoryStore, SessionManager
from src.models.session import SessionState


@pytest.fixture
def store(tmp_path):
    """Create a MemoryStore instance with temporary database."""
    return MemoryStore(state_dir=tmp_path)


@pytest.fixture
def manager(store):
    """Create a SessionManager instance."""
    return SessionManager(store)


def test_create_session(store):
    """Test session creation."""
    session = store.create_session(title="Test Session")
    assert session.id is not None
    assert session.title == "Test Session"
    assert session.state == SessionState.ACTIVE


def test_add_message(store):
    """Test adding messages to a session."""
    session = store.create_session()
    message = store.add_message(session.id, "user", "Hello!")
    
    assert message is not None
    assert message.role == "user"
    assert message.content == "Hello!"
    
    # Retrieve session and check message
    retrieved = store.get_session(session.id)
    assert len(retrieved.messages) == 1
    assert retrieved.message_count == 1


def test_get_context(store):
    """Test getting conversation context."""
    session = store.create_session()
    
    # Add multiple messages
    for i in range(5):
        store.add_message(session.id, "user" if i % 2 == 0 else "assistant", f"Message {i}")
    
    context = store.get_context(session.id, max_messages=3)
    assert len(context) == 3
    # Should get the last 3 messages
    assert context[-1]["content"] == "Message 4"


def test_search_messages(store):
    """Test searching messages."""
    session = store.create_session()
    
    store.add_message(session.id, "user", "What is Python?")
    store.add_message(session.id, "assistant", "Python is a programming language.")
    store.add_message(session.id, "user", "What is JavaScript?")
    
    results = store.search_messages("Python", session.id)
    assert len(results) == 2  # Both "Python" messages found


def test_list_sessions(store):
    """Test listing sessions."""
    # Create multiple sessions
    for i in range(3):
        store.create_session(title=f"Session {i}")
    
    sessions = store.list_sessions()
    assert len(sessions) == 3


def test_archive_session(store):
    """Test archiving a session."""
    session = store.create_session()
    store.archive_session(session.id)
    
    archived = store.get_session(session.id)
    assert archived.state == SessionState.ARCHIVED


def test_delete_session(store):
    """Test deleting a session."""
    session = store.create_session()
    store.add_message(session.id, "user", "Test message")
    
    result = store.delete_session(session.id)
    assert result is True
    
    # Session should not exist
    deleted = store.get_session(session.id)
    assert deleted is None


def test_session_manager_get_or_create(manager):
    """Test SessionManager get_or_create."""
    # Create new session
    session1 = manager.get_or_create_session()
    assert session1 is not None
    
    # Get existing session
    session2 = manager.get_or_create_session(session1.id)
    assert session2.id == session1.id


def test_session_manager_remember(manager):
    """Test SessionManager remember functionality."""
    manager.remember("user", "Hello!")
    manager.remember("assistant", "Hi there!")
    
    context = manager.recall()
    assert len(context) == 2
    assert context[0]["role"] == "user"  # Chronological order (oldest first)
    assert context[0]["content"] == "Hello!"
    assert context[1]["role"] == "assistant"
    assert context[1]["content"] == "Hi there!"


def test_statistics(store):
    """Test memory statistics."""
    session = store.create_session()
    store.add_message(session.id, "user", "Test")
    
    stats = store.get_statistics()
    assert stats["total_sessions"] >= 1
    assert stats["total_messages"] >= 1
    assert stats["active_sessions"] >= 1
