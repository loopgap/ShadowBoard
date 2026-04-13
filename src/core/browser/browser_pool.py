"""
Browser Connection Pool - 企业级浏览器资源管理

提供:
- 浏览器实例池化
- 自动资源回收
- 健康检查
- 故障自愈
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class BrowserHealth(Enum):
    """浏览器健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class BrowserMetrics:
    """浏览器指标"""
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    times_used: int = 0
    error_count: int = 0
    page_count: int = 0
    memory_mb: float = 0.0
    
    def touch(self):
        """更新最后使用时间"""
        self.last_used = datetime.now()
    
    def record_error(self):
        """记录错误"""
        self.error_count += 1
    
    def is_healthy(self) -> bool:
        """判断是否健康"""
        # 3 次错误后认为不健康
        return self.error_count < 3


class BrowserPoolConfig:
    """浏览器池配置"""
    
    def __init__(
        self,
        min_size: int = 2,
        max_size: int = 10,
        acquire_timeout: float = 30.0,
        health_check_interval: float = 60.0,
        idle_timeout: float = 300.0,
        max_reuse_count: int = 100,
    ):
        """
        Args:
            min_size: 最小池大小
            max_size: 最大池大小
            acquire_timeout: 获取超时（秒）
            health_check_interval: 健康检查间隔（秒）
            idle_timeout: 空闲超时（秒）
            max_reuse_count: 最大重用次数
        """
        self.min_size = min_size
        self.max_size = max_size
        self.acquire_timeout = acquire_timeout
        self.health_check_interval = health_check_interval
        self.idle_timeout = idle_timeout
        self.max_reuse_count = max_reuse_count


class BrowserPool:
    """企业级浏览器连接池"""
    
    def __init__(
        self,
        config: BrowserPoolConfig = None,
    ):
        """初始化浏览器池"""
        self.config = config or BrowserPoolConfig()
        
        # 池状态
        self._available = asyncio.Queue(maxsize=self.config.max_size)
        self._in_use = set()
        self._all_browsers = []
        self._metrics = {}
        
        # 同步机制
        self._lock = asyncio.Lock()
        self._init_event = asyncio.Event()
        self._initialized = False
        self._closed = False
        
        # 后台任务
        self._health_check_task = None
        self._cleanup_task = None
    
    async def initialize(self):
        """初始化池"""
        async with self._lock:
            if self._initialized:
                return
            
            try:
                # 创建最小数量的浏览器
                for _ in range(self.config.min_size):
                    browser = await self._create_browser()
                    self._all_browsers.append(browser)
                    await self._available.put(browser)
                
                self._initialized = True
                self._init_event.set()
                logger.info(f"Browser pool initialized with {self.config.min_size} browsers")
                
                # 启动后台任务
                self._health_check_task = asyncio.create_task(self._health_check_loop())
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
                
            except Exception as e:
                logger.error(f"Failed to initialize browser pool: {e}")
                raise
    
    async def _create_browser(self):
        """创建单个浏览器实例"""
        from playwright.async_api import async_playwright
        
        try:
            playwright = await async_playwright().start()
            browser = await asyncio.wait_for(
                playwright.chromium.launch(headless=True),
                timeout=30.0
            )
            
            self._metrics[id(browser)] = BrowserMetrics()
            logger.debug(f"Created browser instance {id(browser)}")
            return browser
            
        except asyncio.TimeoutError:
            raise TimeoutError("Browser launch timeout (30s)")
        except Exception as e:
            logger.error(f"Failed to create browser: {e}")
            raise
    
    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator:
        """获取浏览器实例"""
        await self._init_event.wait()
        
        browser = None
        
        try:
            # 尝试从池获取
            try:
                browser = await asyncio.wait_for(
                    self._available.get(),
                    timeout=self.config.acquire_timeout
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"No available browser in pool (timeout: {self.config.acquire_timeout}s)"
                )
            
            # 检查浏览器健康状态
            if not await self._is_healthy(browser):
                logger.warning(f"Browser {id(browser)} is unhealthy, creating replacement")
                await self._destroy_browser(browser)
                browser = await self._create_browser()
            
            # 执行健康检查
            try:
                await asyncio.wait_for(
                    self._verify_browser(browser),
                    timeout=5.0
                )
            except Exception as e:
                logger.warning(f"Browser health check failed: {e}")
                metrics = self._metrics.get(id(browser))
                if metrics:
                    metrics.record_error()
                raise
            
            # 标记为使用中
            self._in_use.add(id(browser))
            metrics = self._metrics.get(id(browser))
            if metrics:
                metrics.touch()
                metrics.times_used += 1
            
            yield browser
            
        except Exception as e:
            logger.error(f"Error acquiring browser: {e}")
            raise
            
        finally:
            # 尝试归还或销毁
            if browser:
                self._in_use.discard(id(browser))
                
                try:
                    metrics = self._metrics.get(id(browser))
                    if metrics:
                        # 检查是否超过重用次数
                        if metrics.times_used >= self.config.max_reuse_count:
                            logger.info(
                                f"Browser {id(browser)} reached max reuse count, "
                                f"destroying and creating new instance"
                            )
                            await self._destroy_browser(browser)
                            if len(self._all_browsers) < self.config.min_size:
                                new_browser = await self._create_browser()
                                self._all_browsers.append(new_browser)
                                await self._available.put(new_browser)
                        else:
                            # 归还到池
                            await self._available.put(browser)
                    
                except Exception as e:
                    logger.error(f"Error returning browser to pool: {e}")
    
    async def _is_healthy(self, browser) -> bool:
        """检查浏览器健康状态"""
        try:
            metrics = self._metrics.get(id(browser))
            if not metrics or not metrics.is_healthy():
                return False
            
            # 检查浏览器是否仍有效
            if not browser.is_connected():
                return False
            
            return True
            
        except Exception:
            return False
    
    async def _verify_browser(self, browser):
        """验证浏览器可用性"""
        try:
            # 简单的活动测试
            page = await browser.new_page()
            await page.evaluate("1 + 1")
            await page.close()
        except Exception as e:
            raise RuntimeError(f"Browser verification failed: {e}")
    
    async def _destroy_browser(self, browser):
        """销毁浏览器实例"""
        try:
            # 关闭所有页面
            for context in browser.contexts:
                for page in context.pages:
                    try:
                        await page.close()
                    except Exception as e:
                        logger.warning(f"Failed to close page: {e}")
                try:
                    await context.close()
                except Exception as e:
                    logger.warning(f"Failed to close context: {e}")
            
            # 关闭浏览器
            await browser.close()
            
            # 清理指标
            metrics_id = id(browser)
            if metrics_id in self._metrics:
                del self._metrics[metrics_id]
            
            if browser in self._all_browsers:
                self._all_browsers.remove(browser)
            
            logger.debug(f"Destroyed browser instance {metrics_id}")
            
        except Exception as e:
            logger.error(f"Error destroying browser: {e}")
    
    async def _health_check_loop(self):
        """后台健康检查"""
        while not self._closed:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                
                # 检查所有浏览器
                unhealthy = []
                for browser in self._all_browsers:
                    if id(browser) not in self._in_use:
                        if not await self._is_healthy(browser):
                            unhealthy.append(browser)
                
                # 销毁不健康的浏览器
                for browser in unhealthy:
                    try:
                        await self._destroy_browser(browser)
                        
                        # 创建替换实例
                        if len(self._all_browsers) < self.config.min_size:
                            replacement = await self._create_browser()
                            self._all_browsers.append(replacement)
                            await self._available.put(replacement)
                    except Exception as e:
                        logger.error(f"Error during health check: {e}")
                
                if unhealthy:
                    logger.info(f"Health check: replaced {len(unhealthy)} unhealthy browsers")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
    
    async def _cleanup_loop(self):
        """后台清理循环"""
        while not self._closed:
            try:
                await asyncio.sleep(self.config.idle_timeout)
                
                # 清理长时间未使用的浏览器
                current_time = datetime.now()
                to_remove = []
                
                for i, browser in enumerate(self._all_browsers):
                    if id(browser) in self._in_use:
                        continue
                    
                    metrics = self._metrics.get(id(browser))
                    if metrics:
                        idle_time = (current_time - metrics.last_used).total_seconds()
                        if idle_time > self.config.idle_timeout:
                            to_remove.append((i, browser))
                
                # 移除和替换
                for _, browser in reversed(to_remove):
                    try:
                        await self._destroy_browser(browser)
                    except Exception as e:
                        logger.error(f"Error cleaning up browser: {e}")
                
                if to_remove:
                    logger.info(f"Cleanup: removed {len(to_remove)} idle browsers")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    async def get_stats(self) -> dict:
        """获取池统计信息"""
        total_browsers = len(self._all_browsers)
        available = self._available.qsize()
        in_use = len(self._in_use)
        
        return {
            'total': total_browsers,
            'available': available,
            'in_use': in_use,
            'config': {
                'min_size': self.config.min_size,
                'max_size': self.config.max_size,
            },
            'metrics': {
                id_: vars(m) 
                for id_, m in self._metrics.items()
            }
        }
    
    async def close(self):
        """关闭浏览器池"""
        async with self._lock:
            if self._closed:
                return
            
            self._closed = True
            
            # 取消后台任务
            if self._health_check_task:
                self._health_check_task.cancel()
            if self._cleanup_task:
                self._cleanup_task.cancel()
            
            # 等待任务完成
            await asyncio.gather(
                self._health_check_task,
                self._cleanup_task,
                return_exceptions=True
            )
            
            # 销毁所有浏览器
            for browser in self._all_browsers[:]:
                try:
                    await self._destroy_browser(browser)
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
            
            logger.info("Browser pool closed")
