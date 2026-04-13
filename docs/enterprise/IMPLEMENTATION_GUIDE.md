# ShadowBoard 企业级升级 - 集成指南

## 快速开始

本指南说明如何将新的企业级模块集成到现有 ShadowBoard 系统中。

---

## Phase 1: 安全基础集成

### Step 1.1: 认证系统集成

#### 1. 环境准备

```bash
# 安装所需包
pip install pyjwt cryptography

# 设置环境变量
export SHADOW_JWT_SECRET="your-super-secret-key-change-in-production"
export SHADOW_MASTER_KEY="your-master-encryption-key"
```

#### 2. 初始化认证管理器

```python
# src/core/auth/__init__.py (新建)

from .auth_manager import (
    AuthManager,
    RBACManager,
    Role,
    Permission,
    User,
    AuditEvent,
)

__all__ = [
    'AuthManager',
    'RBACManager', 
    'Role',
    'Permission',
    'User',
    'AuditEvent',
]

# 全局单例
_auth_manager = None

def get_auth_manager() -> AuthManager:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager
```

#### 3. 创建初始管理员用户

```python
# scripts/init_admin.py

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.auth import get_auth_manager, Role

async def main():
    auth = get_auth_manager()
    
    # 创建管理员
    admin = await auth.create_user(
        username="admin",
        email="admin@shadowboard.local",
        password="change-me-in-production!",
        role=Role.ADMIN,
    )
    
    print(f"✓ Admin user created: {admin.username} ({admin.email})")
    
    # 创建测试用户
    operator = await auth.create_user(
        username="operator",
        email="operator@shadowboard.local",
        password="operator-password",
        role=Role.OPERATOR,
    )
    
    print(f"✓ Operator user created: {operator.username}")

if __name__ == '__main__':
    asyncio.run(main())
```

```bash
# 运行初始化脚本
python scripts/init_admin.py
```

### Step 1.2: 输入验证集成

#### 1. 在任务创建中使用验证

```python
# src/services/task_tracker.py (修改)

from src.core.security.validation import (
    InputValidator,
    ValidationError,
    SecureInputBuilder,
)

class TaskTracker:
    async def create_task(
        self,
        template_key: str,
        user_input: str,
        user_id: str,  # 新增
    ) -> Task:
        """创建任务（安全版本）"""
        
        # 验证输入
        valid, error = InputValidator.validate(template_key, 'template_key')
        if not valid:
            raise ValidationError(error, field_name='template_key')
        
        valid, error = InputValidator.validate(user_input, 'prompt')
        if not valid:
            raise ValidationError(error, field_name='user_input')
        
        # 检查权限
        from src.core.auth import get_auth_manager, Permission, Role
        auth = get_auth_manager()
        
        # 获取用户角色
        user_role = await self._get_user_role(user_id)
        if not RBACManager.has_permission(user_role, Permission.TASK_CREATE):
            raise PermissionError("Task creation not allowed")
        
        # 安全构建 prompt
        prompt = SecureInputBuilder.build_safe_prompt(
            template_key,
            user_input,
            self.templates
        )
        
        # 创建任务
        task = Task(
            template_key=template_key,
            user_input=user_input,
            prompt=prompt,
            user_id=user_id,  # 记录操作者
        )
        
        # 记录审计事件
        event = AuditEvent(
            user_id=user_id,
            action="task_created",
            resource_type="task",
            resource_id=task.id,
            details={'template': template_key},
        )
        await auth.record_audit(event)
        
        return task
```

#### 2. 在 Web UI 中添加验证

```python
# src/ui/app.py (修改)

from gradio import gr
from src.core.security.validation import InputValidator, ValidationError

async def create_task_handler(template_label, user_input):
    """任务创建处理器"""
    try:
        # 获取当前用户
        current_user = gr.context.session_state.current_user
        if not current_user:
            return "❌ 未授权", ""
        
        template_key = TEMPLATE_LABEL_TO_KEY.get(template_label)
        
        # 验证
        valid, error = InputValidator.validate(template_key, 'template_key')
        if not valid:
            return f"❌ 模板验证失败: {error}", ""
        
        valid, error = InputValidator.validate(user_input, 'prompt')
        if not valid:
            return f"❌ 输入验证失败: {error}", ""
        
        # 创建任务
        task = await get_task_tracker().create_task(
            template_key,
            user_input,
            current_user.id
        )
        
        return f"✓ 任务已创建: {task.id}", task.id
        
    except ValidationError as e:
        return f"❌ 验证错误: {e.message}", ""
    except PermissionError as e:
        return f"❌ 权限错误: {e}", ""
    except Exception as e:
        return f"❌ 错误: {e}", ""
```

---

## Phase 2: 可靠性集成

### Step 2.1: 浏览器连接池集成

#### 1. 替换旧的浏览器管理

```python
# src/core/browser/__init__.py (修改)

from .browser_pool import BrowserPool, BrowserPoolConfig

# 全局连接池
_pool = None

async def get_browser_pool() -> BrowserPool:
    global _pool
    if _pool is None:
        config = BrowserPoolConfig(
            min_size=2,
            max_size=10,
            acquire_timeout=30.0,
            health_check_interval=60.0,
        )
        _pool = BrowserPool(config)
        await _pool.initialize()
    return _pool

async def close_browser_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
```

#### 2. 更新 main.py 使用连接池

```python
# main.py (修改)

async def execute_task(task: Task):
    """执行任务"""
    pool = await get_browser_pool()
    
    # 使用上下文管理器自动管理浏览器生命周期
    async with pool.acquire() as browser:
        try:
            # 执行任务逻辑
            result = await _send_to_ai(browser, task.prompt)
            return result
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            raise

async def main():
    # 启动时初始化
    pool = await get_browser_pool()
    
    try:
        # 主程序逻辑
        pass
    finally:
        # 关闭时清理
        await close_browser_pool()
```

### Step 2.2: 重试与熔断集成

#### 1. 配置重试策略

```python
# src/services/task_tracker.py (修改)

from src.core.resilience.retry_policy import (
    RetryExecutor,
    RetryConfig,
    CircuitBreaker,
    CircuitBreakerConfig,
)

class TaskTrackerWithResilience(TaskTracker):
    def __init__(self):
        super().__init__()
        
        # 配置重试
        self.retry_config = RetryConfig(
            max_attempts=3,
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=1.0,
            max_delay=30.0,
        )
        self.retry_executor = RetryExecutor(self.retry_config)
        
        # 配置熔断器
        self.circuit_breaker = CircuitBreaker(
            name="ai_provider",
            config=CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=2,
                timeout_seconds=60,
            )
        )
    
    async def execute_with_resilience(self, task: Task):
        """带重试和熔断的执行"""
        
        # 使用重试执行
        async def _execute():
            return await self.circuit_breaker.call(
                self._execute_task,
                task
            )
        
        return await self.retry_executor.execute(_execute)
    
    async def _execute_task(self, task: Task):
        """实际执行逻辑"""
        # ...
        pass
```

#### 2. 监控熔断器状态

```python
# src/ui/monitor_tab.py (修改)

async def get_system_health():
    """获取系统健康状态"""
    tracker = get_task_tracker()
    
    health = {
        'circuit_breaker': tracker.circuit_breaker.get_status(),
        'browser_pool': await get_browser_pool().get_stats(),
    }
    
    return health
```

---

## Phase 3: 测试与验证

### 单元测试

```python
# tests/test_auth.py (新建)

import asyncio
import pytest
from src.core.auth import AuthManager, Role, Permission, RBACManager

@pytest.mark.asyncio
async def test_user_creation():
    """测试用户创建"""
    auth = AuthManager()
    
    user = await auth.create_user(
        username="testuser",
        email="test@example.com",
        password="test123!@#",
        role=Role.OPERATOR,
    )
    
    assert user.username == "testuser"
    assert user.role == Role.OPERATOR
    assert user.active


@pytest.mark.asyncio
async def test_authentication():
    """测试认证"""
    auth = AuthManager()
    
    # 创建用户
    await auth.create_user(
        username="testuser",
        email="test@example.com",
        password="test123!@#",
    )
    
    # 认证
    tokens = await auth.authenticate("testuser", "test123!@#")
    assert 'access_token' in tokens
    assert tokens['token_type'] == 'Bearer'


@pytest.mark.asyncio
async def test_token_verification():
    """测试令牌验证"""
    auth = AuthManager()
    
    # 创建令牌
    tokens = auth.create_tokens("user123", "testuser", Role.OPERATOR)
    
    # 验证
    payload = await auth.verify_token(tokens['access_token'])
    assert payload['sub'] == "user123"
    assert payload['role'] == "operator"


def test_rbac():
    """测试 RBAC"""
    
    # 检查权限
    assert RBACManager.has_permission(Role.ADMIN, Permission.TASK_CREATE)
    assert RBACManager.has_permission(Role.OPERATOR, Permission.TASK_CREATE)
    assert not RBACManager.has_permission(Role.VIEWER, Permission.TASK_CREATE)
```

### 集成测试

```python
# tests/test_validation.py (新建)

from src.core.security.validation import InputValidator, ValidationError

def test_prompt_validation():
    """测试提示验证"""
    
    # 有效的提示
    valid, msg = InputValidator.validate("Hello world", "prompt")
    assert valid is True
    
    # 太长的提示
    valid, msg = InputValidator.validate("x" * 100001, "prompt")
    assert valid is False
    
    # 包含禁用关键词
    valid, msg = InputValidator.validate("DROP TABLE users", "prompt")
    assert valid is False


def test_template_validation():
    """测试模板验证"""
    
    # 有效的模板
    valid, msg = InputValidator.validate("custom_template", "template_key")
    assert valid is True
    
    # 无效格式
    valid, msg = InputValidator.validate("CUSTOM-TEMPLATE", "template_key")
    assert valid is False
```

---

## Phase 4: 部署检查清单

### 生产部署前检查

- [ ] 所有环境变量已设置
  ```bash
  SHADOW_JWT_SECRET=production-key
  SHADOW_MASTER_KEY=production-key
  ```

- [ ] 数据库已初始化
  ```bash
  python scripts/init_admin.py
  ```

- [ ] 所有测试通过
  ```bash
  pytest --cov=src
  ```

- [ ] 安全审计完成
  ```bash
  bandit -r src/
  ```

- [ ] 日志配置正确
  ```python
  import logging
  logging.basicConfig(
      level=logging.INFO,
      format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  )
  ```

---

## Phase 5: 监控与维护

### 关键指标

监控以下关键指标：

1. **认证指标**
   - 登录成功率
   - 令牌撤销率
   - 审计事件数

2. **浏览器池指标**
   - 连接池利用率
   - 浏览器健康状态
   - 故障率

3. **任务执行指标**
   - 平均执行时间
   - 重试率
   - 熔断器触发次数

### 常见问题排查

#### Q: 认证总是失败
```python
# 检查 Secret 密钥
import os
print(os.getenv('SHADOW_JWT_SECRET'))

# 验证用户存在
from src.core.auth import get_auth_manager
auth = get_auth_manager()
# 通过 sqlite CLI 检查
# sqlite3 .semi_agent/auth.db "SELECT * FROM users;"
```

#### Q: 浏览器连接超时
```python
# 检查浏览器池状态
pool = await get_browser_pool()
stats = await pool.get_stats()
print(stats)

# 增加超时配置
config = BrowserPoolConfig(acquire_timeout=60.0)
```

---

## 进度跟踪

| 阶段 | 状态 | 完成日期 |
|------|------|--------|
| Phase 1: 安全基础 | ⏳ 进行中 | TBD |
| Phase 2: 可靠性 | ⏳ 进行中 | TBD |
| Phase 3: 架构现代化 | 📋 计划中 | TBD |
| Phase 4: 可观测性 | 📋 计划中 | TBD |
| Phase 5: 测试文档 | 📋 计划中 | TBD |

---

## 下一步

1. **立即行动** (本周)
   - [ ] 安装依赖包
   - [ ] 设置环境变量
   - [ ] 初始化数据库

2. **第一周** 
   - [ ] 集成认证系统
   - [ ] 集成验证框架
   - [ ] 编写单元测试

3. **第二周**
   - [ ] 集成浏览器连接池
   - [ ] 集成重试与熔断
   - [ ] 性能测试和优化

---

**最后更新**: 2026-04-13  
**版本**: 1.0 - 初始版本
