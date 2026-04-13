"""
Dependency Injection & Service Registry Module

Provides centralized access to global service singletons:
- TaskTracker
- MemoryStore
- SessionManager
- WorkflowEngine
- Monitor
"""

from __future__ import annotations

import threading
from typing import Optional

from src.services.task_tracker import TaskTracker
from src.services.memory_store import MemoryStore, SessionManager
from src.services.workflow import WorkflowEngine
from src.services.monitor import Monitor


# Global service instances and their initialization locks
_task_tracker: Optional[TaskTracker] = None
_memory_store: Optional[MemoryStore] = None
_session_manager: Optional[SessionManager] = None
_workflow_engine: Optional[WorkflowEngine] = None
_monitor: Optional[Monitor] = None

_init_lock = threading.Lock()


def get_task_tracker() -> TaskTracker:
    """Get or create the global TaskTracker instance (Thread-safe)."""
    global _task_tracker
    if _task_tracker is None:
        with _init_lock:
            if _task_tracker is None:
                _task_tracker = TaskTracker()
    return _task_tracker


def get_memory_store() -> MemoryStore:
    """Get or create the global MemoryStore instance (Thread-safe)."""
    global _memory_store
    if _memory_store is None:
        with _init_lock:
            if _memory_store is None:
                _memory_store = MemoryStore()
    return _memory_store


def get_session_manager() -> SessionManager:
    """Get or create the global SessionManager instance (Thread-safe)."""
    global _session_manager
    if _session_manager is None:
        with _init_lock:
            if _session_manager is None:
                _session_manager = SessionManager(get_memory_store())
    return _session_manager


def get_workflow_engine() -> WorkflowEngine:
    """Get or create the global WorkflowEngine instance (Thread-safe)."""
    global _workflow_engine
    if _workflow_engine is None:
        with _init_lock:
            if _workflow_engine is None:
                _workflow_engine = WorkflowEngine()
    return _workflow_engine


def get_monitor() -> Monitor:
    """Get or create the global Monitor instance (Thread-safe)."""
    global _monitor
    if _monitor is None:
        with _init_lock:
            if _monitor is None:
                _monitor = Monitor()
    return _monitor
