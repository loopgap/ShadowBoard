# ShadowBoard 企业级架构升级规划

**文档版本**: 1.0  
**最后更新**: 2026-04-13  
**规划等级**: 企业级 (Enterprise Grade)  
**目标**: 零漏洞、高可靠、可审计的生产级系统

---

## 📋 执行摘要

ShadowBoard 当前是一个功能性的原型系统，具有创新的 AI 多角色决策架构。为了达到企业级标准，需要在以下几个维度进行系统性升级：

| 维度 | 当前状态 | 目标状态 | 优先级 |
|------|--------|--------|-------|
| **安全性** | 无认证/授权机制 | RBAC + 审计日志 | 🔴 Critical |
| **可靠性** | 基础错误处理 | 完整故障恢复 + 自愈 | 🔴 Critical |
| **可维护性** | 单体架构 | 分层服务架构 | 🟠 High |
| **可观测性** | 基础日志 | 分布式追踪 + 指标 | 🟠 High |
| **性能** | 无连接池 | 连接池 + 缓存 | 🟡 Medium |
| **文档** | 基础文档 | 完整 API + 部署文档 | 🟡 Medium |

---

## 🔴 第一部分: 关键安全隐患分析

### 1.1 身份认证与授权缺失
**严重程度**: 🔴 **CRITICAL**

#### 当前问题
```python
# web_app.py - 无任何认证检查
LOGIN_STATE: Dict[str, Any] = {"p": None, "context": None, "page": None}
LAST_INPUT: Dict[str, str] = {}
# 任何人可以访问所有功能
```

#### 风险
- 完全开放的系统，任何人可远程访问
- 无法审计谁执行了什么操作
- 多租户场景下数据完全混淆
- 无角色/权限隔离

#### 改进方案 - Phase 1A
```yaml
架构层次:
  1. 认证层 (Authentication)
     - JWT token + refresh token
     - 支持多种认证方式 (API Key, OAuth2, LDAP)
     - 会话管理与 token 黑名单
  
  2. 授权层 (Authorization)
     - RBAC (Role-Based Access Control)
     - 资源级权限检查 (Resource-level)
     - 属性级访问控制 (Attribute-based)
  
  3. 审计层 (Audit)
     - 所有操作记录时间戳+操作者
     - 变更日志持久化
     - 审计事件 API

实施位置:
  - src/core/auth/ (新建)
    - auth_manager.py - 认证核心
    - rbac_manager.py - 授权核心
    - audit.py - 审计日志
  - src/core/middleware/ (新建)
    - auth_middleware.py - 请求级检查
    - audit_middleware.py - 操作记录
```

---

### 1.2 输入验证与注入攻击风险
**严重程度**: 🔴 **CRITICAL**

#### 当前问题
```python
# src/utils/helpers.py - 直接字符串格式化
def build_prompt(template_key: str, user_input: str) -> str:
    template = TEMPLATES.get(template_key, "{user_input}")
    return template.format(user_input=user_input)  # 无验证！

# web_app.py - 直接使用用户输入
LAST_INPUT: Dict[str, str] = {"template": "摘要总结", "content": ""}
# 没有长度限制
# 没有字符集检查
# 没有 SQL/XSS 防护
```

#### 风险分析
| 攻击类型 | 影响 | 当前防护 | 概率 |
|---------|------|--------|------|
| **Prompt Injection** | AI 生成恶意内容 | ❌ 无 | 高 |
| **SQL Injection** | 数据库泄露 | ⚠️ SQLite ORM 部分防护 | 中 |
| **XSS (Web UI)** | DOM 篡改 | ⚠️ Gradio 框架部分防护 | 中 |
| **Path Traversal** | 文件访问 | ❌ 无 | 中 |

#### 改进方案 - Phase 1B
```python
# src/core/validation/validator.py (新建)

from typing import Any
import re
from dataclasses import dataclass

@dataclass
class ValidationRule:
    max_length: int = 100000  # 100KB 限制
    min_length: int = 1
    pattern: Optional[str] = None
    allowed_chars: Optional[str] = None
    forbidden_keywords: list = None

class InputValidator:
    """企业级输入验证"""
    
    # 预定义规则集
    RULES = {
        'prompt': ValidationRule(
            max_length=100000,
            forbidden_keywords=['DROP', 'DELETE', 'EXEC', 'SCRIPT']
        ),
        'template_key': ValidationRule(
            pattern=r'^[a-z_]+$',  # 仅小写字母和下划线
            max_length=50
        ),
        'url': ValidationRule(
            pattern=r'^https?://',
            max_length=2048
        ),
    }
    
    @staticmethod
    def validate(value: Any, rule_name: str) -> tuple[bool, str]:
        """验证输入并返回 (是否有效, 错误消息)"""
        rule = InputValidator.RULES.get(rule_name)
        if not rule:
            raise ValueError(f"Unknown rule: {rule_name}")
        
        # 1. 类型检查
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value)}"
        
        # 2. 长度检查
        if len(value) < rule.min_length:
            return False, f"Too short (min: {rule.min_length})"
        if len(value) > rule.max_length:
            return False, f"Too long (max: {rule.max_length})"
        
        # 3. 模式检查
        if rule.pattern and not re.match(rule.pattern, value):
            return False, f"Invalid format (pattern: {rule.pattern})"
        
        # 4. 字符集检查
        if rule.allowed_chars:
            invalid = set(value) - set(rule.allowed_chars)
            if invalid:
                return False, f"Invalid characters: {invalid}"
        
        # 5. 关键词检查
        if rule.forbidden_keywords:
            for keyword in rule.forbidden_keywords:
                if keyword.upper() in value.upper():
                    return False, f"Forbidden keyword: {keyword}"
        
        return True, ""

# 使用示例
class TaskService:
    def create_task(self, template_key: str, user_input: str) -> Task:
        # 1. 验证输入
        valid, msg = InputValidator.validate(template_key, 'template_key')
        if not valid:
            raise ValueError(f"Invalid template_key: {msg}")
        
        valid, msg = InputValidator.validate(user_input, 'prompt')
        if not valid:
            raise ValueError(f"Invalid prompt: {msg}")
        
        # 2. 安全处理
        prompt = self._sanitize_prompt(user_input)
        
        # 3. 创建任务
        return Task(template_key=template_key, user_input=prompt)
    
    @staticmethod
    def _sanitize_prompt(text: str) -> str:
        """清理提示文本防止注入"""
        # 移除控制字符
        text = ''.join(c for c in text if ord(c) >= 32 or c in '\n\t')
        # 限制连续空白
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
```

---

### 1.3 敏感数据加密与保护
**严重程度**: 🔴 **CRITICAL**

#### 当前问题
```python
# 凭据以明文存储
CONFIG_PATH = STATE_DIR / "config.json"
HISTORY_PATH = STATE_DIR / "history.jsonl"

# 数据库无加密
self._db_path = state_dir / "memory.db"  # 完全明文 SQLite
```

#### 改进方案 - Phase 1C
```python
# src/core/security/encryption.py (新建)

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
import base64
import os

class EncryptionManager:
    """企业级数据加密"""
    
    def __init__(self, master_key: str = None):
        """
        初始化加密管理器
        
        Args:
            master_key: 主密钥（环境变量优先）
        """
        self.master_key = master_key or os.getenv('SHADOW_MASTER_KEY')
        if not self.master_key:
            raise ValueError(
                "Master key required: set SHADOW_MASTER_KEY environment variable"
            )
        
        self._cipher = self._derive_cipher(self.master_key)
    
    @staticmethod
    def _derive_cipher(master_key: str) -> Fernet:
        """从主密钥派生加密密钥"""
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'shadowboard_salt',
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        return Fernet(key)
    
    def encrypt_value(self, value: str) -> str:
        """加密单个值"""
        encrypted = self._cipher.encrypt(value.encode())
        return encrypted.decode()
    
    def decrypt_value(self, encrypted: str) -> str:
        """解密单个值"""
        decrypted = self._cipher.decrypt(encrypted.encode())
        return decrypted.decode()
    
    def encrypt_dict(self, data: dict, keys: list) -> dict:
        """加密字典中的特定键"""
        result = data.copy()
        for key in keys:
            if key in result:
                result[key] = self.encrypt_value(str(result[key]))
        return result
    
    def decrypt_dict(self, data: dict, keys: list) -> dict:
        """解密字典中的特定键"""
        result = data.copy()
        for key in keys:
            if key in result:
                result[key] = self.decrypt_value(result[key])
        return result

# 使用示例
class SecureConfigManager:
    def __init__(self, enc_manager: EncryptionManager):
        self.enc = enc_manager
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        with open(CONFIG_PATH) as f:
            encrypted_config = json.load(f)
        
        # 解密敏感字段
        return self.enc.decrypt_dict(
            encrypted_config,
            keys=['api_key', 'password', 'auth_token']
        )
    
    def save_config(self, config: dict):
        # 加密敏感字段
        encrypted = self.enc.encrypt_dict(
            config,
            keys=['api_key', 'password', 'auth_token']
        )
        
        with open(CONFIG_PATH, 'w') as f:
            json.dump(encrypted, f)
```

---

### 1.4 会话与令牌安全
**严重程度**: 🟠 **HIGH**

#### 当前问题
```python
# web_app.py - 无会话管理
LOGIN_STATE: Dict[str, Any] = {"p": None, "context": None, "page": None}
# 全局状态，无隔离
# 无超时机制
# 无 token 黑名单
```

#### 改进方案 - Phase 1D
```python
# src/core/session/session_manager.py (新建)

import jwt
import secrets
from datetime import datetime, timedelta
from typing import Optional

class SessionManager:
    """企业级会话管理"""
    
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.token_blacklist = set()  # 实际应使用 Redis
        self._session_store = {}      # 实际应使用 Redis
    
    def create_session(
        self,
        user_id: str,
        expires_in: int = 3600,  # 1 小时
        extra_claims: dict = None
    ) -> dict:
        """创建会话和访问令牌"""
        
        # 生成不可猜测的会话 ID
        session_id = secrets.token_urlsafe(32)
        
        # 准备 JWT 声明
        now = datetime.utcnow()
        claims = {
            'sub': user_id,
            'sid': session_id,
            'iat': now,
            'exp': now + timedelta(seconds=expires_in),
            'type': 'access',
        }
        
        if extra_claims:
            claims.update(extra_claims)
        
        # 签署 JWT
        access_token = jwt.encode(
            claims,
            self.secret_key,
            algorithm=self.algorithm
        )
        
        # 生成刷新令牌
        refresh_claims = {
            'sub': user_id,
            'sid': session_id,
            'type': 'refresh',
            'iat': now,
            'exp': now + timedelta(days=7),  # 7 天
        }
        
        refresh_token = jwt.encode(
            refresh_claims,
            self.secret_key,
            algorithm=self.algorithm
        )
        
        # 存储会话元数据
        self._session_store[session_id] = {
            'user_id': user_id,
            'created_at': now.isoformat(),
            'last_activity': now.isoformat(),
            'ip_address': None,  # 应从请求获取
            'user_agent': None,  # 应从请求获取
        }
        
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': expires_in,
            'token_type': 'Bearer',
        }
    
    def verify_token(self, token: str) -> Optional[dict]:
        """验证并解码令牌"""
        
        # 检查黑名单
        if token in self.token_blacklist:
            raise ValueError("Token has been revoked")
        
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")
    
    def revoke_token(self, token: str):
        """撤销令牌（加入黑名单）"""
        self.token_blacklist.add(token)
    
    def refresh_access_token(self, refresh_token: str) -> dict:
        """使用刷新令牌获取新的访问令牌"""
        payload = self.verify_token(refresh_token)
        
        if payload.get('type') != 'refresh':
            raise ValueError("Invalid token type")
        
        return self.create_session(
            user_id=payload['sub'],
            extra_claims={'original_sid': payload['sid']}
        )
```

---

## 🟠 第二部分: 可靠性与故障转移

### 2.1 浏览器进程管理与资源泄漏
**严重程度**: 🔴 **CRITICAL**

#### 当前问题
```python
# src/core/browser.py
def launch(self, headless: bool = False, channel: Optional[str] = None):
    # 存在异常路径导致资源泄漏
    try:
        # 可能抛出异常
        self._context = await playwright.chromium.launch_persistent_context(...)
    except Exception as inner_e:
        await self.close()  # 这里可能也抛出异常！
        raise BrowserError(...)
```

#### 改进方案 - Phase 2A
```python
# src/core/browser/browser_pool.py (新建)

import contextlib
import weakref
from typing import AsyncGenerator

class BrowserPool:
    """连接池模式的浏览器管理"""
    
    def __init__(self, max_size: int = 5, timeout: int = 300):
        self.max_size = max_size
        self.timeout = timeout
        self._available = asyncio.Queue(maxsize=max_size)
        self._all_browsers = []
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self):
        """初始化连接池"""
        async with self._lock:
            if self._initialized:
                return
            
            for _ in range(self.max_size):
                browser = await self._create_browser()
                self._all_browsers.append(browser)
                await self._available.put(browser)
            
            self._initialized = True
    
    async def _create_browser(self) -> BrowserContext:
        """创建单个浏览器实例"""
        playwright = await self._ensure_playwright()
        
        # 使用超时防止无限等待
        try:
            context = await asyncio.wait_for(
                playwright.chromium.launch_persistent_context(
                    headless=True,
                    viewport={"width": 1280, "height": 800},
                ),
                timeout=30.0
            )
            return context
        except asyncio.TimeoutError:
            raise BrowserError("Browser launch timeout")
    
    @contextlib.asynccontextmanager
    async def acquire(self) -> AsyncGenerator[BrowserContext, None]:
        """获取浏览器（自动归还）"""
        browser = None
        try:
            # 尝试从池获取
            browser = await asyncio.wait_for(
                self._available.get(),
                timeout=self.timeout
            )
            
            yield browser
            
        except asyncio.TimeoutError:
            raise BrowserError("No available browser in pool")
        finally:
            # 确保归还或清理
            if browser:
                if await self._is_healthy(browser):
                    await self._available.put(browser)
                else:
                    # 不健康的实例，销毁并创建新的
                    await self._destroy_browser(browser)
                    try:
                        new_browser = await self._create_browser()
                        await self._available.put(new_browser)
                    except Exception as e:
                        logger.error(f"Failed to create replacement browser: {e}")
    
    async def _is_healthy(self, browser: BrowserContext) -> bool:
        """检查浏览器健康状态"""
        try:
            if not browser.pages:
                return False
            
            # 简单的活动检查
            page = browser.pages[0]
            await asyncio.wait_for(page.evaluate("1+1"), timeout=5.0)
            return True
        except Exception:
            return False
    
    async def _destroy_browser(self, browser: BrowserContext):
        """销毁浏览器实例并清理资源"""
        try:
            for page in browser.pages:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"Failed to close page: {e}")
            
            await browser.close()
        except Exception as e:
            logger.error(f"Error destroying browser: {e}")
    
    async def close_all(self):
        """关闭所有浏览器"""
        async with self._lock:
            for browser in self._all_browsers:
                await self._destroy_browser(browser)
            
            self._all_browsers.clear()
            self._initialized = False
```

---

### 2.2 错误恢复与自愈机制
**严重程度**: 🟠 **HIGH**

#### 改进方案 - Phase 2B
```python
# src/core/resilience/retry_policy.py (新建)

import asyncio
from enum import Enum
from typing import Callable, Optional
import random

class RetryStrategy(Enum):
    """重试策略"""
    EXPONENTIAL = "exponential"    # 指数退避
    LINEAR = "linear"              # 线性退避
    RANDOM = "random"              # 随机退避
    FIBONACCI = "fibonacci"        # 斐波那契

class CircuitBreakerState(Enum):
    """熔断器状态"""
    CLOSED = "closed"          # 正常
    OPEN = "open"              # 熔断（拒绝请求）
    HALF_OPEN = "half_open"    # 半开（允许试验）

class CircuitBreaker:
    """企业级熔断器模式"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: int = 60,
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_error = None
        self.last_error_time = None
    
    async def call(
        self,
        func: Callable,
        *args,
        **kwargs
    ):
        """执行受熔断器保护的函数"""
        
        if self.state == CircuitBreakerState.OPEN:
            # 检查是否应该尝试半开
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
            else:
                raise CircuitBreakerError(
                    f"Circuit breaker open. Last error: {self.last_error}"
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
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitBreakerState.CLOSED
    
    def _on_failure(self, error: Exception):
        """失败时的处理"""
        self.failure_count += 1
        self.last_error = str(error)
        self.last_error_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试重置"""
        if not self.last_error_time:
            return True
        
        elapsed = (datetime.now() - self.last_error_time).total_seconds()
        return elapsed >= self.timeout_seconds

class RetryPolicyExecutor:
    """重试政策执行器"""
    
    def __init__(
        self,
        max_attempts: int = 3,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        base_delay: float = 1.0,
    ):
        self.max_attempts = max_attempts
        self.strategy = strategy
        self.base_delay = base_delay
    
    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ):
        """执行带重试的函数"""
        last_error = None
        
        for attempt in range(self.max_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                
                if attempt < self.max_attempts - 1:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
        
        raise last_error
    
    def _calculate_delay(self, attempt: int) -> float:
        """根据策略计算延迟"""
        if self.strategy == RetryStrategy.EXPONENTIAL:
            return self.base_delay * (2 ** attempt)
        
        elif self.strategy == RetryStrategy.LINEAR:
            return self.base_delay * (attempt + 1)
        
        elif self.strategy == RetryStrategy.RANDOM:
            return self.base_delay * random.uniform(1, 2 ** attempt)
        
        elif self.strategy == RetryStrategy.FIBONACCI:
            fib = [1, 1]
            for _ in range(attempt - 1):
                fib.append(fib[-1] + fib[-2])
            return self.base_delay * fib[attempt]
        
        return self.base_delay
```

---

## 🟡 第三部分: 架构现代化

### 3.1 分层架构与依赖注入
**严重程度**: 🟡 **MEDIUM**

#### 当前问题
```python
# src/core/dependencies.py - 使用全局单例
_task_tracker: Optional[TaskTracker] = None

def get_task_tracker() -> TaskTracker:
    global _task_tracker
    if _task_tracker is None:
        with _init_lock:
            if _task_tracker is None:
                _task_tracker = TaskTracker()  # 硬编码
    return _task_tracker
```

#### 改进方案 - Phase 3A
```python
# src/core/di/__init__.py (新建)

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Type, TypeVar

T = TypeVar('T')

class ServiceContainer:
    """企业级依赖注入容器"""
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, Any] = {}
    
    def register(
        self,
        service_type: Type[T],
        implementation: Optional[T] = None,
        factory: Optional[Callable[[], T]] = None,
        singleton: bool = True,
    ):
        """注册服务"""
        service_name = service_type.__name__
        
        if factory:
            self._factories[service_name] = factory
        elif implementation:
            self._services[service_name] = implementation
        else:
            raise ValueError("Either implementation or factory must be provided")
    
    def resolve(self, service_type: Type[T]) -> T:
        """解析并获取服务实例"""
        service_name = service_type.__name__
        
        # 检查是否已有单例
        if service_name in self._singletons:
            return self._singletons[service_name]
        
        # 检查是否已注册
        if service_name in self._services:
            instance = self._services[service_name]
        elif service_name in self._factories:
            instance = self._factories[service_name]()
        else:
            raise ValueError(f"Service {service_name} not registered")
        
        # 缓存单例
        self._singletons[service_name] = instance
        return instance
    
    def clear(self):
        """清除所有单例（用于测试）"""
        self._singletons.clear()

# 全局容器实例
_container = ServiceContainer()

# 注册所有服务
def configure_container():
    """配置依赖注入容器"""
    from src.services.task_tracker import TaskTracker
    from src.services.memory_store import MemoryStore
    from src.services.workflow import WorkflowEngine
    from src.services.monitor import Monitor
    
    _container.register(TaskTracker, singleton=True)
    _container.register(MemoryStore, singleton=True)
    _container.register(WorkflowEngine, singleton=True)
    _container.register(Monitor, singleton=True)

# 工厂函数
def get_container() -> ServiceContainer:
    return _container
```

---

### 3.2 异步优先设计
**严重程度**: 🟡 **MEDIUM**

#### 改进方案 - Phase 3B
```python
# src/core/async_utils.py (新建)

import asyncio
from typing import Callable, Any
from concurrent.futures import ThreadPoolExecutor

class AsyncExecutor:
    """异步执行工具"""
    
    def __init__(self, max_workers: int = 10):
        self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)
    
    async def run_in_thread(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """在线程池中运行同步函数"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._thread_pool,
            func,
            *args
        )
    
    async def gather_with_timeout(
        self,
        tasks: list,
        timeout: float
    ) -> list:
        """带超时的批量执行"""
        try:
            return await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            # 取消所有待处理任务
            for task in tasks:
                if isinstance(task, asyncio.Task):
                    task.cancel()
            raise
```

---

## 🟢 第四部分: 可观测性与监控

### 4.1 分布式追踪
**严重程度**: 🟡 **MEDIUM**

#### 改进方案 - Phase 4A
```python
# src/core/observability/tracing.py (新建)

import uuid
from contextvars import ContextVar
from typing import Optional, Dict, Any
import json

# 全局上下文变量
_trace_id: ContextVar[str] = ContextVar('trace_id', default='')
_span_id: ContextVar[str] = ContextVar('span_id', default='')

class Span:
    """追踪跨度"""
    
    def __init__(
        self,
        name: str,
        trace_id: str,
        parent_span_id: Optional[str] = None,
    ):
        self.name = name
        self.trace_id = trace_id
        self.span_id = str(uuid.uuid4())
        self.parent_span_id = parent_span_id
        self.attributes: Dict[str, Any] = {}
        self.start_time = None
        self.end_time = None
        self.status = "UNSET"
        self.error = None
    
    def set_attribute(self, key: str, value: Any):
        """设置属性"""
        self.attributes[key] = value
    
    def record_exception(self, error: Exception):
        """记录异常"""
        self.error = str(error)
        self.status = "ERROR"
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        return {
            'name': self.name,
            'trace_id': self.trace_id,
            'span_id': self.span_id,
            'parent_span_id': self.parent_span_id,
            'attributes': self.attributes,
            'status': self.status,
            'error': self.error,
        }

class Tracer:
    """分布式追踪器"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
    
    def start_trace(self) -> str:
        """开始新的追踪"""
        trace_id = str(uuid.uuid4())
        _trace_id.set(trace_id)
        return trace_id
    
    def create_span(self, name: str) -> Span:
        """创建子跨度"""
        trace_id = _trace_id.get()
        parent_span_id = _span_id.get()
        
        span = Span(
            name=name,
            trace_id=trace_id,
            parent_span_id=parent_span_id or None,
        )
        
        _span_id.set(span.span_id)
        return span
    
    def get_current_context(self) -> Dict[str, str]:
        """获取当前追踪上下文"""
        return {
            'trace_id': _trace_id.get(),
            'span_id': _span_id.get(),
        }
```

---

## 📊 第五部分: 实施路线图

### Phase 1: 安全加固 (Weeks 1-2)
**目标**: 建立安全基础

| 任务 | 优先级 | 工作量 | 所有者 |
|------|--------|--------|--------|
| 1A. 认证与授权系统 | 🔴 | 3d | Security |
| 1B. 输入验证框架 | 🔴 | 2d | Backend |
| 1C. 加密管理模块 | 🔴 | 2d | Security |
| 1D. 会话管理 | 🟠 | 2d | Backend |
| **小计** | - | **9d** | - |

### Phase 2: 可靠性 (Weeks 3-4)
**目标**: 故障转移与自愈

| 任务 | 优先级 | 工作量 | 所有者 |
|------|--------|--------|--------|
| 2A. 浏览器连接池 | 🔴 | 2d | Backend |
| 2B. 重试与熔断 | 🟠 | 2d | Backend |
| 2C. 资源管理 | 🟠 | 1d | Infra |
| **小计** | - | **5d** | - |

### Phase 3: 架构现代化 (Weeks 5-6)
**目标**: 可维护与可扩展

| 任务 | 优先级 | 工作量 | 所有者 |
|------|--------|--------|--------|
| 3A. DI 容器 | 🟡 | 1d | Backend |
| 3B. 异步优先 | 🟡 | 2d | Backend |
| 3C. 错误处理标准化 | 🟡 | 1d | Backend |
| **小计** | - | **4d** | - |

### Phase 4: 可观测性 (Weeks 7-8)
**目标**: 监控与诊断

| 任务 | 优先级 | 工作量 | 所有者 |
|------|--------|--------|--------|
| 4A. 分布式追踪 | 🟡 | 1d | Infra |
| 4B. 指标收集 | 🟡 | 1d | Infra |
| 4C. 日志聚合 | 🟡 | 1d | Infra |
| **小计** | - | **3d** | - |

### Phase 5: 测试与文档 (Weeks 9-10)
**目标**: 质量门禁

| 任务 | 优先级 | 工作量 | 所有者 |
|------|--------|--------|--------|
| 5A. 单元测试 | 🟡 | 2d | QA |
| 5B. 集成测试 | 🟡 | 2d | QA |
| 5C. API 文档 | 🟡 | 1d | Tech |
| **小计** | - | **5d** | - |

---

## 📁 新建架构目录结构

```
src/
├── core/
│   ├── auth/              # ⭐ 新建
│   │   ├── __init__.py
│   │   ├── auth_manager.py
│   │   ├── rbac_manager.py
│   │   └── audit.py
│   ├── security/          # ⭐ 新建
│   │   ├── __init__.py
│   │   ├── encryption.py
│   │   ├── validation.py
│   │   └── secrets.py
│   ├── session/           # ⭐ 新建
│   │   ├── __init__.py
│   │   └── session_manager.py
│   ├── resilience/        # ⭐ 新建
│   │   ├── __init__.py
│   │   ├── retry_policy.py
│   │   └── circuit_breaker.py
│   ├── di/                # ⭐ 新建
│   │   ├── __init__.py
│   │   └── container.py
│   ├── observability/     # ⭐ 新建
│   │   ├── __init__.py
│   │   ├── tracing.py
│   │   ├── metrics.py
│   │   └── logging.py
│   ├── browser/           # 重构
│   │   ├── __init__.py
│   │   ├── browser_pool.py
│   │   └── browser_manager.py
│   ├── config.py          # 修改
│   ├── exceptions.py      # 扩展
│   └── dependencies.py    # 弃用 → 迁移至 di/
├── middleware/            # ⭐ 新建
│   ├── __init__.py
│   ├── auth_middleware.py
│   └── audit_middleware.py
└── ...
```

---

## ✅ 交付标准与验收准则

### 安全性验收准则
- [ ] 所有公开端点需认证检查
- [ ] 所有用户输入通过验证框架
- [ ] 敏感数据加密存储
- [ ] 完整的审计日志
- [ ] 通过 OWASP Top 10 检查

### 可靠性验收准则
- [ ] 浏览器故障自动转移
- [ ] 99.5% 可用性
- [ ] 零僵尸进程泄漏
- [ ] 任务自动重试成功率 > 95%
- [ ] 毁灭性故障下 RTO ≤ 5 分钟

### 性能验收准则
- [ ] API p99 < 1s
- [ ] 并发处理 ≥ 50 个会话
- [ ] 内存稳定（无泄漏）
- [ ] 启动时间 < 5s

### 文档完整性
- [ ] API 参考文档
- [ ] 部署指南
- [ ] 安全加固指南
- [ ] 故障排查指南

---

## 🚀 立即行动项

### 第一周任务
```bash
# 1. 创建安全会议（Day 1）
- 讨论威胁模型
- 确认优先级
- 分配所有者

# 2. 实施认证系统（Day 2-3）
- JWT 令牌管理
- RBAC 框架
- API 守卫

# 3. 输入验证框架（Day 4-5）
- 验证规则引擎
- 集成现有模块
- 单元测试

# 4. 代码审查（Day 5）
- 安全审计
- 架构审查
- 计划第二阶段
```

### 环境准备
```bash
# 依赖更新
pip install pyjwt cryptography sqlalchemy pytest-cov \
            opentelemetry-api opentelemetry-sdk

# 测试框架
pytest --cov=src --cov-report=html

# 安全检查
bandit -r src/
```

---

## 📞 支持与协作

- **安全问题**: security@shadowboard.dev
- **架构讨论**: arch-team@shadowboard.dev
- **实施支持**: dev-ops@shadowboard.dev

---

**版本历史**
| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-04-13 | 初始版本 |

**本文档受版本控制** - 请勿直接修改，通过 PR 更新
