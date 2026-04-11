"""
Monitoring and Alerting Service

Provides system monitoring with:
- Metrics collection
- Health checks
- Alert management
- Performance tracking
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MetricType(Enum):
    """Types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass
class Metric:
    """Represents a single metric measurement."""
    name: str
    value: float
    metric_type: MetricType
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type.value,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }


@dataclass
class Alert:
    """Represents an alert event."""
    id: str = ""
    name: str = ""
    level: AlertLevel = AlertLevel.INFO
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
            "metadata": self.metadata,
        }


@dataclass
class HealthStatus:
    """Represents health check result."""
    component: str
    healthy: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.now)


class MetricsCollector:
    """
    Collects and aggregates metrics.

    Features:
    - Counter, gauge, and histogram metrics
    - Time-series aggregation
    - Tag-based filtering
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        state_dir: Optional[Path] = None,
    ) -> None:
        if db_path:
            self._db_path = db_path
        elif state_dir:
            self._db_path = state_dir / "metrics.db"
        else:
            from src.core.config import get_config_manager
            self._db_path = get_config_manager().state_dir / "metrics.db"

        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)

        self._init_db()

    def _init_db(self) -> None:
        """Initialize metrics database."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    value REAL,
                    type TEXT,
                    timestamp TEXT,
                    tags TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics(timestamp)")

    def increment(
        self,
        name: str,
        value: float = 1.0,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a counter metric."""
        self._counters[name] += value
        self._record_metric(name, value, MetricType.COUNTER, tags or {})

    def gauge(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge metric value."""
        self._gauges[name] = value
        self._record_metric(name, value, MetricType.GAUGE, tags or {})

    def observe(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record an observation for histogram metrics."""
        self._histograms[name].append(value)
        self._record_metric(name, value, MetricType.HISTOGRAM, tags or {})

    def time(self, name: str, tags: Optional[Dict[str, str]] = None):
        """Context manager to time an operation."""
        class Timer:
            def __init__(self, collector: "MetricsCollector", n: str, t: Optional[Dict[str, str]]):
                self.collector = collector
                self.name = n
                self.tags = t or {}
                self.start = 0.0

            def __enter__(self):
                self.start = time.perf_counter()
                return self

            def __exit__(self, *args):
                elapsed = time.perf_counter() - self.start
                self.collector.observe(self.name, elapsed, self.tags)

        return Timer(self, name, tags)

    def _record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType,
        tags: Dict[str, str],
    ) -> None:
        """Record metric to database."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO metrics (name, value, type, timestamp, tags) VALUES (?, ?, ?, ?, ?)",
                (name, value, metric_type.value, datetime.now().isoformat(), json.dumps(tags))
            )

    def get_counter(self, name: str) -> float:
        """Get current counter value."""
        return self._counters.get(name, 0.0)

    def get_gauge(self, name: str) -> float:
        """Get current gauge value."""
        return self._gauges.get(name, 0.0)

    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """Get histogram statistics."""
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "avg": 0, "p95": 0}

        sorted_values = sorted(values)
        count = len(sorted_values)
        p95_idx = int(count * 0.95)

        return {
            "count": count,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "avg": sum(sorted_values) / count,
            "p95": sorted_values[min(p95_idx, count - 1)],
        }

    def get_metrics_since(
        self,
        since: datetime,
        name_prefix: Optional[str] = None,
    ) -> List[Metric]:
        """Get metrics recorded since a timestamp."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row

            if name_prefix:
                cursor = conn.execute(
                    "SELECT * FROM metrics WHERE timestamp >= ? AND name LIKE ? ORDER BY timestamp",
                    (since.isoformat(), f"{name_prefix}%")
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM metrics WHERE timestamp >= ? ORDER BY timestamp",
                    (since.isoformat(),)
                )

            return [
                Metric(
                    name=row["name"],
                    value=row["value"],
                    metric_type=MetricType(row["type"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    tags=json.loads(row["tags"] or "{}"),
                )
                for row in cursor.fetchall()
            ]


class AlertManager:
    """
    Manages alerts and notifications.

    Features:
    - Alert level thresholds
    - Alert deduplication
    - Notification callbacks
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        state_dir: Optional[Path] = None,
    ) -> None:
        if db_path:
            self._db_path = db_path
        elif state_dir:
            self._db_path = state_dir / "alerts.db"
        else:
            from src.core.config import get_config_manager
            self._db_path = get_config_manager().state_dir / "alerts.db"

        self._listeners: List[Callable[[Alert], None]] = []
        self._init_db()

    def _init_db(self) -> None:
        """Initialize alerts database."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    level TEXT,
                    message TEXT,
                    timestamp TEXT,
                    acknowledged INTEGER,
                    metadata TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(timestamp)")

    def add_listener(self, callback: Callable[[Alert], None]) -> None:
        """Add an alert listener."""
        self._listeners.append(callback)

    def fire(
        self,
        name: str,
        level: AlertLevel,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """Fire an alert."""
        import uuid
        alert = Alert(
            id=uuid.uuid4().hex[:8],
            name=name,
            level=level,
            message=message,
            metadata=metadata or {},
        )

        # Persist
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO alerts (id, name, level, message, timestamp, acknowledged, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (alert.id, alert.name, alert.level.value, alert.message,
                 alert.timestamp.isoformat(), 0, json.dumps(alert.metadata))
            )

        # Notify listeners
        for listener in self._listeners:
            try:
                listener(alert)
            except Exception as e:
                print(f"Alert listener error: {e}")

        return alert

    def acknowledge(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "UPDATE alerts SET acknowledged = 1 WHERE id = ?",
                (alert_id,)
            )
            return cursor.rowcount > 0

    def get_active_alerts(self, limit: int = 50) -> List[Alert]:
        """Get unacknowledged alerts."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM alerts WHERE acknowledged = 0 ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )

            return [
                Alert(
                    id=row["id"],
                    name=row["name"],
                    level=AlertLevel(row["level"]),
                    message=row["message"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    acknowledged=bool(row["acknowledged"]),
                    metadata=json.loads(row["metadata"] or "{}"),
                )
                for row in cursor.fetchall()
            ]

    def get_recent_alerts(
        self,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """Get recent alerts."""
        since = since or datetime.now() - timedelta(hours=24)

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM alerts WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                (since.isoformat(), limit)
            )

            return [
                Alert(
                    id=row["id"],
                    name=row["name"],
                    level=AlertLevel(row["level"]),
                    message=row["message"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    acknowledged=bool(row["acknowledged"]),
                    metadata=json.loads(row["metadata"] or "{}"),
                )
                for row in cursor.fetchall()
            ]


class Monitor:
    """
    Comprehensive system monitoring.

    Combines metrics collection, alerting, and health checks.
    """

    def __init__(self, state_dir: Optional[Path] = None) -> None:
        self.metrics = MetricsCollector(state_dir=state_dir)
        self.alerts = AlertManager(state_dir=state_dir)
        self._health_checks: Dict[str, Callable[[], HealthStatus]] = {}

    def register_health_check(
        self,
        component: str,
        check_func: Callable[[], HealthStatus],
    ) -> None:
        """Register a health check function."""
        self._health_checks[component] = check_func

    def run_health_checks(self) -> Dict[str, HealthStatus]:
        """Run all health checks."""
        results = {}
        for component, check_func in self._health_checks.items():
            try:
                results[component] = check_func()
            except Exception as e:
                results[component] = HealthStatus(
                    component=component,
                    healthy=False,
                    message=f"Health check failed: {e}",
                )
        return results

    def get_system_health(self) -> HealthStatus:
        """Get overall system health."""
        checks = self.run_health_checks()
        healthy = all(c.healthy for c in checks.values())

        failed = [name for name, status in checks.items() if not status.healthy]

        message = "All systems healthy" if healthy else f"Issues: {', '.join(failed)}"
        return HealthStatus(
            component="system",
            healthy=healthy,
            message=message,
            details={name: status.message for name, status in checks.items()},
        )

    def record_task_execution(
        self,
        success: bool,
        duration_seconds: float,
        template: str,
    ) -> None:
        """Record task execution metrics."""
        self.metrics.increment(
            "tasks_total",
            tags={"status": "success" if success else "failed"}
        )
        self.metrics.observe(
            "task_duration_seconds",
            duration_seconds,
            tags={"template": template}
        )

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for monitoring dashboard."""
        health = self.get_system_health()
        duration_stats = self.metrics.get_histogram_stats("task_duration_seconds")

        return {
            "health": {
                "healthy": health.healthy,
                "message": health.message,
                "components": health.details,
            },
            "metrics": {
                "tasks_total": self.metrics.get_counter("tasks_total"),
                "task_duration": duration_stats,
            },
            "active_alerts": len(self.alerts.get_active_alerts()),
        }
