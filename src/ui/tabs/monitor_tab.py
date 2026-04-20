"""
Monitor Tab Logic and Event Handlers
"""

from __future__ import annotations

import json
from src.core.dependencies import get_task_tracker, get_monitor


async def get_task_statistics() -> str:
    """Get task statistics from TaskTracker."""
    tracker = get_task_tracker()
    stats = await tracker.get_statistics()
    return json.dumps(stats, ensure_ascii=False, indent=2)


async def get_dashboard_data() -> str:
    """Get comprehensive dashboard data."""
    monitor = get_monitor()
    data = await monitor.get_dashboard_data()
    return json.dumps(data, ensure_ascii=False, indent=2)
