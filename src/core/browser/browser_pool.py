"""
Browser Connection Pool - 企业级浏览器资源管理 (强化版)

提供:
- 浏览器实例池化
- 自动资源回收
- 健康检查
- 故障自愈
- 严格的资源生命周期管理 (防止僵尸进程)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import AsyncGenerator

from src.utils.i18n import t

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
    """企业级浏览器连接池 (强化资源管理版)"""

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

        # Playwright 核心对象
        self._playwright = None

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
                from playwright.async_api import async_playwright

                # 启动全局 Playwright 实例
                self._playwright = await async_playwright().start()

                # 创建最小数量的浏览器
                for _ in range(self.config.min_size):
                    browser = await self._create_browser_instance()
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
                # 尝试部分清理
                if self._playwright:
                    await self._playwright.stop()
                raise

    async def _create_browser_instance(self):
        """创建单个浏览器实例 (内部方法)"""
        if not self._playwright:
            raise RuntimeError("Playwright not initialized")

        try:
            browser = await asyncio.wait_for(self._playwright.chromium.launch(headless=True), timeout=30.0)

            self._metrics[id(browser)] = BrowserMetrics()
            logger.debug(f"Created browser instance {id(browser)}")
            return browser

        except asyncio.TimeoutError:
            raise TimeoutError(t("errors.browser_launch_timeout"))
        except Exception as e:
            logger.error(f"Failed to create browser: {e}")
            raise

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator:
        """获取浏览器实例"""
        if not self._initialized:
            await self.initialize()

        await self._init_event.wait()
        if self._closed:
            raise RuntimeError("Browser pool is closed")

        browser = None

        try:
            # 尝试从池获取
            try:
                browser = await asyncio.wait_for(self._available.get(), timeout=self.config.acquire_timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(t("errors.no_available_browser", timeout=self.config.acquire_timeout))

            # 检查浏览器健康状态
            if not await self._is_healthy(browser):
                logger.warning(f"Browser {id(browser)} is unhealthy, creating replacement")
                await self._destroy_browser(browser)
                browser = await self._create_browser_instance()
                self._all_browsers.append(browser)

            # 标记为使用中
            self._in_use.add(id(browser))
            metrics = self._metrics.get(id(browser))
            if metrics:
                metrics.touch()
                metrics.times_used += 1

            yield browser

        except Exception as e:
            logger.error(f"Error acquiring browser: {e}")
            if browser:
                # 如果发生异常，销毁该浏览器以确保安全
                await self._destroy_browser(browser)
                browser = None
            raise

        finally:
            # 尝试归还或销毁
            if browser and not self._closed:
                self._in_use.discard(id(browser))

                try:
                    metrics = self._metrics.get(id(browser))
                    if metrics and metrics.times_used >= self.config.max_reuse_count:
                        logger.info(f"Browser {id(browser)} reached max reuse, replacing")
                        await self._destroy_browser(browser)
                        # 补充实例以维持最小规模
                        if len(self._all_browsers) < self.config.min_size:
                            new_browser = await self._create_browser_instance()
                            self._all_browsers.append(new_browser)
                            await self._available.put(new_browser)
                    else:
                        # 归还到池
                        await self._available.put(browser)
                except Exception as e:
                    logger.error(f"Error returning browser to pool: {e}")
                    await self._destroy_browser(browser)

    async def _is_healthy(self, browser) -> bool:
        """检查浏览器健康状态"""
        try:
            metrics = self._metrics.get(id(browser))
            if not metrics or not metrics.is_healthy():
                return False

            if not browser.is_connected():
                return False

            return True
        except Exception:
            return False

    async def _destroy_browser(self, browser):
        """销毁浏览器实例"""
        try:
            browser_id = id(browser)
            # 关闭浏览器 (Playwright 会自动关闭关联的 contexts 和 pages)
            await asyncio.wait_for(browser.close(), timeout=10.0)

            # 清理状态
            if browser_id in self._metrics:
                del self._metrics[browser_id]

            if browser in self._all_browsers:
                self._all_browsers.remove(browser)

            self._in_use.discard(browser_id)

            logger.debug(f"Destroyed browser instance {browser_id}")
        except Exception as e:
            logger.error(f"Error destroying browser {id(browser)}: {e}")
            # 即使报错也尝试从列表中移除
            if browser in self._all_browsers:
                self._all_browsers.remove(browser)

    async def _health_check_loop(self):
        """后台健康检查"""
        while not self._closed:
            try:
                await asyncio.sleep(self.config.health_check_interval)

                async with self._lock:
                    unhealthy = []
                    for browser in self._all_browsers:
                        if id(browser) not in self._in_use:
                            if not await self._is_healthy(browser):
                                unhealthy.append(browser)

                    for browser in unhealthy:
                        await self._destroy_browser(browser)
                        if len(self._all_browsers) < self.config.min_size:
                            replacement = await self._create_browser_instance()
                            self._all_browsers.append(replacement)
                            await self._available.put(replacement)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")

    async def _cleanup_loop(self):
        """后台清理循环"""
        while not self._closed:
            try:
                await asyncio.sleep(self.config.idle_timeout)

                async with self._lock:
                    current_time = datetime.now()
                    to_remove = []

                    for browser in self._all_browsers:
                        if id(browser) in self._in_use:
                            continue

                        metrics = self._metrics.get(id(browser))
                        if metrics:
                            idle_time = (current_time - metrics.last_used).total_seconds()
                            if idle_time > self.config.idle_timeout and len(self._all_browsers) > self.config.min_size:
                                to_remove.append(browser)

                    for browser in to_remove:
                        await self._destroy_browser(browser)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")

    async def get_stats(self) -> dict:
        """获取池统计信息"""
        return {
            "total": len(self._all_browsers),
            "available": self._available.qsize(),
            "in_use": len(self._in_use),
            "metrics": {str(id_): vars(m) for id_, m in self._metrics.items()},
        }

    async def close(self):
        """关闭浏览器池并释放所有资源"""
        async with self._lock:
            if self._closed:
                return

            self._closed = True
            logger.info("Closing browser pool...")

            # 1. 取消后台任务
            if self._health_check_task:
                self._health_check_task.cancel()
            if self._cleanup_task:
                self._cleanup_task.cancel()

            # 2. 销毁所有浏览器实例
            for browser in list(self._all_browsers):
                await self._destroy_browser(browser)

            # 3. 停止 Playwright 核心 (至关重要: 防止僵尸进程)
            if self._playwright:
                try:
                    await self._playwright.stop()
                    self._playwright = None
                except Exception as e:
                    logger.error(f"Error stopping Playwright: {e}")

            logger.info("Browser pool closed successfully")
