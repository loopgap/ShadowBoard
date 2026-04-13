"""
Resilience Patterns - 企业级故障恢复

提供:
- 重试策略
- 熔断器模式
- 速率限制
- 降级策略
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """重试策略"""
    EXPONENTIAL = "exponential"    # 2^n
    LINEAR = "linear"              # n
    RANDOM = "random"              # 随机
    FIBONACCI = "fibonacci"        # 斐波那契


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"          # 正常允许请求
    OPEN = "open"              # 熔断拒绝请求
    HALF_OPEN = "half_open"    # 半开允许试验


class CircuitBreakerError(Exception):
    """熔断器异常"""
    pass


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True
    exponential_base: float = 2.0


class RetryExecutor:
    """重试执行器"""
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
    
    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """执行函数并按需重试"""
        last_error = None
        
        for attempt in range(self.config.max_attempts):
            try:
                result = await func(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(
                        f"Succeeded after {attempt + 1} attempts "
                        f"(strategy: {self.config.strategy.value})"
                    )
                
                return result
                
            except Exception as e:
                last_error = e
                
                # 最后一次不再重试
                if attempt >= self.config.max_attempts - 1:
                    break
                
                # 计算延迟
                delay = self._calculate_delay(attempt)
                
                logger.warning(
                    f"Attempt {attempt + 1}/{self.config.max_attempts} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                
                await asyncio.sleep(delay)
        
        raise last_error or RuntimeError("Retry failed")
    
    def _calculate_delay(self, attempt: int) -> float:
        """根据策略计算延迟"""
        base = self.config.base_delay
        
        if self.config.strategy == RetryStrategy.EXPONENTIAL:
            delay = base * (self.config.exponential_base ** attempt)
        
        elif self.config.strategy == RetryStrategy.LINEAR:
            delay = base * (attempt + 1)
        
        elif self.config.strategy == RetryStrategy.RANDOM:
            max_delay = base * (self.config.exponential_base ** attempt)
            delay = random.uniform(base, max_delay)
        
        elif self.config.strategy == RetryStrategy.FIBONACCI:
            fib_seq = self._fibonacci_sequence(attempt + 2)
            delay = base * fib_seq[attempt + 1]
        
        else:
            delay = base
        
        # 应用最大延迟限制
        delay = min(delay, self.config.max_delay)
        
        # 添加抖动
        if self.config.jitter:
            jitter = random.uniform(0, delay * 0.1)
            delay += jitter
        
        return delay
    
    @staticmethod
    def _fibonacci_sequence(n: int) -> list:
        """生成斐波那契数列"""
        if n <= 0:
            return []
        
        seq = [1, 1]
        for _ in range(n - 2):
            seq.append(seq[-1] + seq[-2])
        
        return seq


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5        # 失败次数阈值
    success_threshold: int = 2        # 成功次数阈值（半开状态）
    timeout_seconds: int = 60         # 熔断恢复超时


class CircuitBreaker:
    """企业级熔断器"""
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # 状态
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.last_error = None
    
    async def call(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """在熔断器保护下执行函数"""
        
        # 检查熔断器状态
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                logger.info(f"Circuit breaker '{self.name}' attempting reset")
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Last error: {self.last_error}"
                )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
            
        except Exception as e:
            self._on_failure(e)
            raise
    
    def _on_success(self):
        """成功时的处理"""
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            
            if self.success_count >= self.config.success_threshold:
                logger.info(
                    f"Circuit breaker '{self.name}' HALF_OPEN -> CLOSED "
                    f"({self.success_count} successes)"
                )
                self.state = CircuitState.CLOSED
                self.last_error = None
    
    def _on_failure(self, error: Exception):
        """失败时的处理"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.last_error = str(error)
        
        if self.state == CircuitState.HALF_OPEN:
            logger.warning(
                f"Circuit breaker '{self.name}' HALF_OPEN -> OPEN "
                f"(failed during reset)"
            )
            self.state = CircuitState.OPEN
        
        elif self.failure_count >= self.config.failure_threshold:
            logger.error(
                f"Circuit breaker '{self.name}' CLOSED -> OPEN "
                f"({self.failure_count} failures)"
            )
            self.state = CircuitState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """检查是否应尝试重置"""
        if not self.last_failure_time:
            return True
        
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.config.timeout_seconds
    
    def get_status(self) -> dict:
        """获取状态信息"""
        return {
            'name': self.name,
            'state': self.state.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'last_error': self.last_error,
            'last_failure_time': (
                self.last_failure_time.isoformat() 
                if self.last_failure_time else None
            ),
        }


class RateLimiter:
    """速率限制器"""
    
    def __init__(
        self,
        max_calls: int = 100,
        time_window: int = 60,
    ):
        """
        Args:
            max_calls: 时间窗口内的最大调用数
            time_window: 时间窗口（秒）
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self._calls = []
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> bool:
        """获取令牌"""
        async with self._lock:
            now = datetime.now()
            window_start = now - timedelta(seconds=self.time_window)
            
            # 清理过期的调用记录
            self._calls = [
                call_time for call_time in self._calls
                if call_time > window_start
            ]
            
            # 检查是否超限
            if len(self._calls) + tokens <= self.max_calls:
                for _ in range(tokens):
                    self._calls.append(now)
                return True
            
            return False
    
    async def wait_if_needed(self, tokens: int = 1):
        """如需要则等待"""
        while not await self.acquire(tokens):
            await asyncio.sleep(0.1)
    
    def get_status(self) -> dict:
        """获取状态"""
        now = datetime.now()
        window_start = now - timedelta(seconds=self.time_window)
        
        active_calls = [
            call_time for call_time in self._calls
            if call_time > window_start
        ]
        
        return {
            'max_calls': self.max_calls,
            'time_window': self.time_window,
            'current_calls': len(active_calls),
            'available': self.max_calls - len(active_calls),
        }


@dataclass
class FallbackConfig:
    """降级配置"""
    enabled: bool = True
    timeout: float = 5.0


class FallbackManager:
    """降级管理器"""
    
    def __init__(self):
        self._fallbacks: dict = {}
    
    def register_fallback(
        self,
        operation_name: str,
        fallback_func: Callable,
    ):
        """注册降级函数"""
        self._fallbacks[operation_name] = fallback_func
    
    async def execute_with_fallback(
        self,
        operation_name: str,
        primary_func: Callable,
        *args,
        config: FallbackConfig = None,
        **kwargs
    ) -> Any:
        """执行并支持降级"""
        config = config or FallbackConfig()
        
        if not config.enabled:
            return await primary_func(*args, **kwargs)
        
        try:
            # 尝试主函数
            result = await asyncio.wait_for(
                primary_func(*args, **kwargs),
                timeout=config.timeout
            )
            return result
            
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(
                f"Primary operation '{operation_name}' failed, "
                f"attempting fallback: {e}"
            )
            
            # 尝试降级
            fallback_func = self._fallbacks.get(operation_name)
            if fallback_func:
                try:
                    result = await fallback_func(*args, **kwargs)
                    logger.info(f"Fallback for '{operation_name}' succeeded")
                    return result
                    
                except Exception as fallback_error:
                    logger.error(
                        f"Fallback for '{operation_name}' also failed: {fallback_error}"
                    )
                    raise
            
            raise
