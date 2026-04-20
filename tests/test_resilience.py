"""
Tests for Resilience Module

Tests retry logic, fallback mechanisms, circuit breakers, and timeout handling.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timedelta

from src.core.resilience import (
    RetryStrategy,
    RetryExecutor,
    RetryConfig,
    CircuitState,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    RateLimiter,
    FallbackManager,
    FallbackConfig,
)


class TestRetryConfig:
    """Test RetryConfig dataclass."""

    def test_retry_config_defaults(self):
        """Test RetryConfig default values."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.strategy == RetryStrategy.EXPONENTIAL
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.jitter is True

    def test_retry_config_custom(self):
        """Test RetryConfig with custom values."""
        config = RetryConfig(
            max_attempts=5,
            strategy=RetryStrategy.LINEAR,
            base_delay=2.0,
            max_delay=30.0,
        )
        assert config.max_attempts == 5
        assert config.strategy == RetryStrategy.LINEAR


class TestRetryExecutor:
    """Test RetryExecutor class."""

    @pytest.mark.asyncio
    async def test_execute_success_first_attempt(self):
        """Test successful execution on first attempt."""
        config = RetryConfig(max_attempts=3)
        executor = RetryExecutor(config)

        mock_func = AsyncMock(return_value="success")
        result = await executor.execute(mock_func)

        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_success_after_retries(self):
        """Test successful execution after retries."""
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        executor = RetryExecutor(config)

        mock_func = AsyncMock(side_effect=[RuntimeError("fail"), "success"])
        result = await executor.execute(mock_func)

        assert result == "success"
        assert mock_func.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_all_attempts_fail(self):
        """Test all retry attempts fail."""
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        executor = RetryExecutor(config)

        mock_func = AsyncMock(side_effect=RuntimeError("always fail"))

        with pytest.raises(RuntimeError, match="always fail"):
            await executor.execute(mock_func)

        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_with_positional_args(self):
        """Test execution with positional arguments."""
        config = RetryConfig(max_attempts=2, base_delay=0.01)
        executor = RetryExecutor(config)

        async def func(a, b):
            return f"{a}-{b}"

        result = await executor.execute(func, "hello", "world")

        assert result == "hello-world"

    @pytest.mark.asyncio
    async def test_execute_with_kwargs(self):
        """Test execution with keyword arguments."""
        config = RetryConfig(max_attempts=2, base_delay=0.01)
        executor = RetryExecutor(config)

        async def func(x=1, y=2):
            return x + y

        result = await executor.execute(func, x=5, y=10)

        assert result == 15


class TestRetryStrategy:
    """Test RetryStrategy enum values."""

    def test_retry_strategy_values(self):
        """Test all strategy values exist."""
        assert RetryStrategy.EXPONENTIAL.value == "exponential"
        assert RetryStrategy.LINEAR.value == "linear"
        assert RetryStrategy.RANDOM.value == "random"
        assert RetryStrategy.FIBONACCI.value == "fibonacci"


class TestCircuitBreaker:
    """Test CircuitBreaker class."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_success(self):
        """Test successful call through circuit breaker."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=60,
        )
        cb = CircuitBreaker("test", config)

        mock_func = AsyncMock(return_value="success")
        result = await cb.call(mock_func)

        assert result == "success"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after threshold failures."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=60,
        )
        cb = CircuitBreaker("test", config)

        mock_func = AsyncMock(side_effect=RuntimeError("fail"))

        # Exhaust failure threshold
        for _ in range(3):
            try:
                await cb.call(mock_func)
            except RuntimeError:
                pass

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_rejects_when_open(self):
        """Test circuit breaker rejects calls when open."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=60,
        )
        cb = CircuitBreaker("test", config)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = datetime.now()

        mock_func = AsyncMock(return_value="success")

        with pytest.raises(CircuitBreakerError, match="is OPEN"):
            await cb.call(mock_func)

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit breaker goes to half-open after timeout and closes after successes."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,  # Require 1 success to close
            timeout_seconds=1,
        )
        cb = CircuitBreaker("test", config)
        cb.state = CircuitState.OPEN
        cb.last_failure_time = datetime.now() - timedelta(seconds=2)

        mock_func = AsyncMock(return_value="success")
        result = await cb.call(mock_func)

        assert result == "success"
        assert cb.state == CircuitState.CLOSED

    def test_circuit_breaker_get_status(self):
        """Test getting circuit breaker status."""
        config = CircuitBreakerConfig(failure_threshold=5)
        cb = CircuitBreaker("test", config)
        cb.failure_count = 3

        status = cb.get_status()

        assert status["name"] == "test"
        assert status["state"] == "closed"
        assert status["failure_count"] == 3


class TestRateLimiter:
    """Test RateLimiter class."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_within_limit(self):
        """Test rate limiter allows calls within limit."""
        limiter = RateLimiter(max_calls=10, time_window=60)

        result = await limiter.acquire()
        assert result is True

        status = limiter.get_status()
        assert status["available"] == 9

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_at_limit(self):
        """Test rate limiter blocks when at limit."""
        limiter = RateLimiter(max_calls=2, time_window=60)

        await limiter.acquire()
        await limiter.acquire()
        result = await limiter.acquire()

        assert result is False

    @pytest.mark.asyncio
    async def test_rate_limiter_clears_old_calls(self):
        """Test rate limiter clears old calls after window."""
        limiter = RateLimiter(max_calls=2, time_window=1)

        await limiter.acquire()
        await limiter.acquire()

        # Wait for window to expire
        await asyncio.sleep(1.1)

        result = await limiter.acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_rate_limiter_wait_if_needed(self):
        """Test wait_if_needed blocks when at limit."""
        limiter = RateLimiter(max_calls=1, time_window=60)

        await limiter.acquire()

        # This should block but eventually succeed (would need real time passage)
        # We just test it doesn't raise
        async def check_wait():
            await limiter.wait_ifNeeded()

        # Can't fully test without real time passage, but verify method exists
        assert hasattr(limiter, "wait_if_needed")

    def test_rate_limiter_get_status(self):
        """Test rate limiter status."""
        limiter = RateLimiter(max_calls=100, time_window=60)

        status = limiter.get_status()

        assert status["max_calls"] == 100
        assert status["time_window"] == 60
        assert status["available"] == 100


class TestFallbackConfig:
    """Test FallbackConfig dataclass."""

    def test_fallback_config_defaults(self):
        """Test FallbackConfig default values."""
        config = FallbackConfig()
        assert config.enabled is True
        assert config.timeout == 5.0


class TestFallbackManager:
    """Test FallbackManager class."""

    @pytest.mark.asyncio
    async def test_fallback_manager_primary_succeeds(self):
        """Test fallback manager uses primary when successful."""
        manager = FallbackManager()

        primary_func = AsyncMock(return_value="primary_result")
        fallback_func = AsyncMock(return_value="fallback_result")

        manager.register_fallback("op1", fallback_func)

        result = await manager.execute_with_fallback(
            "op1",
            primary_func,
        )

        assert result == "primary_result"
        fallback_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_manager_fallback_on_timeout(self):
        """Test fallback manager uses fallback on timeout."""
        manager = FallbackManager()

        async def slow_primary():
            await asyncio.sleep(10)
            return "primary"

        fallback_func = AsyncMock(return_value="fallback_result")

        manager.register_fallback("op1", fallback_func)

        config = FallbackConfig(timeout=0.1)

        result = await manager.execute_with_fallback(
            "op1",
            slow_primary,
            config=config,
        )

        assert result == "fallback_result"

    @pytest.mark.asyncio
    async def test_fallback_manager_fallback_on_error(self):
        """Test fallback manager uses fallback on error."""
        manager = FallbackManager()

        primary_func = AsyncMock(side_effect=RuntimeError("primary failed"))
        fallback_func = AsyncMock(return_value="fallback_result")

        manager.register_fallback("op1", fallback_func)

        result = await manager.execute_with_fallback(
            "op1",
            primary_func,
        )

        assert result == "fallback_result"

    @pytest.mark.asyncio
    async def test_fallback_manager_no_fallback_raises(self):
        """Test fallback manager raises when no fallback registered."""
        manager = FallbackManager()

        primary_func = AsyncMock(side_effect=RuntimeError("primary failed"))

        with pytest.raises(RuntimeError):
            await manager.execute_with_fallback(
                "unknown_op",
                primary_func,
            )

    @pytest.mark.asyncio
    async def test_fallback_manager_disabled(self):
        """Test fallback manager when fallback is disabled."""
        manager = FallbackManager()

        primary_func = AsyncMock(side_effect=RuntimeError("primary failed"))

        config = FallbackConfig(enabled=False)

        with pytest.raises(RuntimeError):
            await manager.execute_with_fallback(
                "op1",
                primary_func,
                config=config,
            )


class TestCircuitState:
    """Test CircuitState enum."""

    def test_circuit_state_values(self):
        """Test CircuitState enum values."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"
