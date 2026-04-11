"""
Tests for Monitoring Service
"""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.monitor import (
    Monitor,
    MetricsCollector,
    AlertManager,
    AlertLevel,
    HealthStatus,
)


@pytest.fixture
def metrics(tmp_path):
    """Create a MetricsCollector instance."""
    return MetricsCollector(state_dir=tmp_path)


@pytest.fixture
def alerts(tmp_path):
    """Create an AlertManager instance."""
    return AlertManager(state_dir=tmp_path)


@pytest.fixture
def monitor(tmp_path):
    """Create a Monitor instance."""
    return Monitor(state_dir=tmp_path)


# MetricsCollector Tests

def test_counter_increment(metrics):
    """Test counter increment."""
    metrics.increment("test_counter")
    assert metrics.get_counter("test_counter") == 1.0
    
    metrics.increment("test_counter", 5.0)
    assert metrics.get_counter("test_counter") == 6.0


def test_gauge_set(metrics):
    """Test gauge value setting."""
    metrics.gauge("test_gauge", 42.0)
    assert metrics.get_gauge("test_gauge") == 42.0
    
    metrics.gauge("test_gauge", 100.0)
    assert metrics.get_gauge("test_gauge") == 100.0


def test_histogram_observe(metrics):
    """Test histogram observations."""
    for i in range(100):
        metrics.observe("test_histogram", float(i))
    
    stats = metrics.get_histogram_stats("test_histogram")
    assert stats["count"] == 100
    assert stats["min"] == 0.0
    assert stats["max"] == 99.0
    assert stats["p95"] >= 94.0  # 95th percentile


def test_timer_context(metrics):
    """Test timer context manager."""
    import time
    
    with metrics.time("test_timer"):
        time.sleep(0.1)
    
    stats = metrics.get_histogram_stats("test_timer")
    assert stats["count"] == 1
    assert stats["min"] >= 0.1


def test_get_metrics_since(metrics):
    """Test retrieving metrics since a timestamp."""
    metrics.increment("old_metric")
    
    from datetime import timedelta
    recent = datetime.now() - timedelta(hours=1)
    
    # Add new metric
    metrics.increment("new_metric")
    
    recent_metrics = metrics.get_metrics_since(recent)
    # Should include both metrics since they're recent
    assert len(recent_metrics) >= 1


# AlertManager Tests

def test_fire_alert(alerts):
    """Test firing an alert."""
    alert = alerts.fire(
        name="test_alert",
        level=AlertLevel.WARNING,
        message="Test warning message",
    )
    
    assert alert.id is not None
    assert alert.name == "test_alert"
    assert alert.level == AlertLevel.WARNING


def test_acknowledge_alert(alerts):
    """Test acknowledging an alert."""
    alert = alerts.fire("test", AlertLevel.INFO, "Test")
    
    result = alerts.acknowledge(alert.id)
    assert result is True
    
    # Check it's no longer in active alerts
    active = alerts.get_active_alerts()
    active_ids = [a.id for a in active]
    assert alert.id not in active_ids


def test_get_active_alerts(alerts):
    """Test getting active alerts."""
    alerts.fire("alert1", AlertLevel.INFO, "Test 1")
    alerts.fire("alert2", AlertLevel.WARNING, "Test 2")
    
    active = alerts.get_active_alerts()
    assert len(active) == 2


def test_alert_listeners(alerts):
    """Test alert listener functionality."""
    received = []
    
    def listener(alert):
        received.append(alert)
    
    alerts.add_listener(listener)
    alerts.fire("test", AlertLevel.INFO, "Test message")
    
    assert len(received) == 1
    assert received[0].name == "test"


def test_get_recent_alerts(alerts):
    """Test getting recent alerts."""
    alerts.fire("recent1", AlertLevel.INFO, "Test 1")
    alerts.fire("recent2", AlertLevel.INFO, "Test 2")
    
    recent = alerts.get_recent_alerts()
    assert len(recent) == 2


# Monitor Tests

def test_register_health_check(monitor):
    """Test registering a health check."""
    def check():
        return HealthStatus(
            component="test_component",
            healthy=True,
            message="All good",
        )
    
    monitor.register_health_check("test_component", check)
    
    results = monitor.run_health_checks()
    assert "test_component" in results
    assert results["test_component"].healthy


def test_system_health(monitor):
    """Test system health check."""
    monitor.register_health_check("healthy_component", lambda: HealthStatus(
        component="healthy_component",
        healthy=True,
    ))
    
    health = monitor.get_system_health()
    assert health.healthy
    
    # Add failing health check
    monitor.register_health_check("failing_component", lambda: HealthStatus(
        component="failing_component",
        healthy=False,
        message="Something is wrong",
    ))
    
    health = monitor.get_system_health()
    assert not health.healthy


def test_record_task_execution(monitor):
    """Test recording task execution metrics."""
    monitor.record_task_execution(True, 1.5, "summary")
    monitor.record_task_execution(False, 2.0, "translation")
    monitor.record_task_execution(True, 1.0, "summary")
    
    stats = monitor.metrics.get_histogram_stats("task_duration_seconds")
    assert stats["count"] == 3
    
    counter = monitor.metrics.get_counter("tasks_total")
    assert counter == 3


def test_get_dashboard_data(monitor):
    """Test getting dashboard data."""
    monitor.register_health_check("test", lambda: HealthStatus(
        component="test",
        healthy=True,
    ))
    
    data = monitor.get_dashboard_data()
    
    assert "health" in data
    assert "metrics" in data
    assert "active_alerts" in data
    assert data["health"]["healthy"] is True
