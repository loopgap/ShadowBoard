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


async def initialize_services() -> None:
    """Initialize all services asynchronously and perform maintenance."""
    # 1. Basic initialization
    await get_task_tracker().initialize()
    await get_memory_store().initialize()
    await get_monitor().initialize()
    if hasattr(get_workflow_engine(), "initialize"):
        await get_workflow_engine().initialize()  # type: ignore

    # 2. Run maintenance tasks
    await run_maintenance()


async def run_maintenance() -> None:
    """Perform resource cleanup and optimization."""
    from src.core.config import get_config_manager
    import time

    config = get_config_manager()
    
    # A. Clean old error snapshots (> 7 days)
    error_dir = config.error_dir
    if error_dir.exists():
        now = time.time()
        for f in error_dir.glob("error_*"):
            if now - f.stat().st_mtime > 7 * 24 * 3600:
                try:
                    f.unlink()
                except Exception:
                    pass

    # B. Compact databases
    try:
        await get_task_tracker().vacuum()
        await get_memory_store().vacuum()
    except Exception:
        pass

    # C. Log workspace status to monitor
    try:
        monitor = get_monitor()
        # Estimate storage (rough)
        storage_bytes = sum(f.stat().st_size for f in config.state_dir.rglob('*') if f.is_file())
        await monitor.metrics.gauge("workspace_storage_mb", round(storage_bytes / (1024 * 1024), 2))
    except Exception:
        pass
