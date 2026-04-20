#!/usr/bin/env python
"""
ShadowBoard 企业级升级 - 快速启动脚本

快速检查和初始化企业级功能
"""

import asyncio
import importlib.util
import logging
import os
import secrets
import string
import sys
from pathlib import Path


def _generate_password(length: int = 16) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


async def check_environment():
    """检查环境配置"""
    print("=" * 60)
    print("🔍 环境检查")
    print("=" * 60)

    checks = []

    # 检查 Python 版本
    version = sys.version_info
    python_ok = version.major == 3 and version.minor >= 9
    checks.append(("Python 3.9+", python_ok, f"{version.major}.{version.minor}"))

    # 检查依赖
    checks.append(
        (
            "PyJWT",
            importlib.util.find_spec("jwt") is not None,
            "installed" if importlib.util.find_spec("jwt") else "missing",
        )
    )
    checks.append(
        (
            "cryptography",
            importlib.util.find_spec("cryptography") is not None,
            "installed" if importlib.util.find_spec("cryptography") else "missing",
        )
    )
    checks.append(
        (
            "Playwright",
            importlib.util.find_spec("playwright") is not None,
            "installed" if importlib.util.find_spec("playwright") else "missing",
        )
    )

    # 检查环境变量
    jwt_secret = os.getenv("SHADOW_JWT_SECRET")
    checks.append(
        (
            "SHADOW_JWT_SECRET",
            bool(jwt_secret),
            "configured" if jwt_secret else "missing",
        )
    )

    master_key = os.getenv("SHADOW_MASTER_KEY")
    checks.append(
        (
            "SHADOW_MASTER_KEY",
            bool(master_key),
            "configured" if master_key else "missing",
        )
    )

    # 检查目录结构
    dirs_to_check = [
        "src/core/auth",
        "src/core/security",
        "src/core/browser",
        "src/core/resilience",
        ".semi_agent",
    ]

    for dir_path in dirs_to_check:
        exists = Path(dir_path).exists()
        status = "exists" if exists else "missing"
        checks.append((f"Directory: {dir_path}", exists, status))

    # 打印检查结果
    print()
    all_ok = True
    for check_name, passed, detail in checks:
        status = "✅" if passed else "❌"
        print(f"{status} {check_name:30} {detail}")
        if not passed:
            all_ok = False

    print()
    if all_ok:
        print("✨ 所有环境检查通过！")
    else:
        print("⚠️  存在环境配置问题，请参考下面的解决方案")

    return all_ok


async def init_auth_system():
    """初始化认证系统"""
    print("\n" + "=" * 60)
    print("🔐 初始化认证系统")
    print("=" * 60 + "\n")

    try:
        from src.core.auth import get_auth_manager, Role

        auth = get_auth_manager()

        # 检查是否已有管理员
        import sqlite3

        with sqlite3.connect(auth.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]

        if user_count > 0:
            print(f"✅ 认证系统已初始化，现有 {user_count} 个用户")
            return

        print("📝 创建初始用户...")

        # 获取或生成密码
        admin_password = os.getenv("SHADOW_ADMIN_PASSWORD") or _generate_password()
        operator_password = os.getenv("SHADOW_OPERATOR_PASSWORD") or _generate_password()
        viewer_password = os.getenv("SHADOW_VIEWER_PASSWORD") or _generate_password()

        # 创建管理员
        admin = await auth.create_user(
            username="admin",
            email="admin@shadowboard.local",
            password=admin_password,
            role=Role.ADMIN,
        )
        print(f"✅ 管理员用户: {admin.username} ({admin.email})")

        # 创建测试操作员
        operator = await auth.create_user(
            username="operator",
            email="operator@shadowboard.local",
            password=operator_password,
            role=Role.OPERATOR,
        )
        print(f"✅ 操作员用户: {operator.username}")

        # 创建查看者
        viewer = await auth.create_user(
            username="viewer",
            email="viewer@shadowboard.local",
            password=viewer_password,
            role=Role.VIEWER,
        )
        print(f"✅ 查看者用户: {viewer.username}")

        print("\n✨ 认证系统初始化完成！")
        print("\n📋 初始凭证:")
        print(f"  Admin: admin / {admin_password}")
        print(f"  Operator: operator / {operator_password}")
        print(f"  Viewer: viewer / {viewer_password}")

    except Exception as e:
        print(f"❌ 认证系统初始化失败: {e}")
        import traceback

        traceback.print_exc()


async def test_validation():
    """测试验证框架"""
    print("\n" + "=" * 60)
    print("✓ 测试验证框架")
    print("=" * 60 + "\n")

    try:
        from src.core.security.validation import InputValidator

        test_cases = [
            ("custom_template", "template_key", True),
            ("INVALID-TEMPLATE", "template_key", False),
            ("Hello world", "prompt", True),
            ("x" * 100001, "prompt", False),
            ("DROP TABLE users", "prompt", False),
        ]

        print("运行验证测试...\n")

        passed = 0
        for value, rule, expected_valid in test_cases:
            valid, msg = InputValidator.validate(value, rule)
            display_value = value[:30] + "..." if len(value) > 30 else value

            if valid == expected_valid:
                print(f"✅ {rule:15} {display_value:35} -> {valid}")
                passed += 1
            else:
                print(f"❌ {rule:15} {display_value:35} -> Expected {expected_valid}, got {valid}")

        print(f"\n通过: {passed}/{len(test_cases)} 测试")

    except Exception as e:
        print(f"❌ 验证框架测试失败: {e}")


async def test_browser_pool():
    """测试浏览器连接池"""
    print("\n" + "=" * 60)
    print("🌐 测试浏览器连接池")
    print("=" * 60 + "\n")

    try:
        from src.core.browser.browser_pool import BrowserPool, BrowserPoolConfig

        print("创建浏览器池...")
        config = BrowserPoolConfig(
            min_size=1,
            max_size=3,
            acquire_timeout=30.0,
        )

        pool = BrowserPool(config)
        await pool.initialize()

        print("✅ 浏览器池初始化成功")

        stats = await pool.get_stats()
        print("\n池统计信息:")
        print(f"  总数: {stats['total']}")
        print(f"  可用: {stats['available']}")
        print(f"  使用中: {stats['in_use']}")

        await pool.close()
        print("\n✅ 浏览器池已关闭")

    except ImportError:
        print("ℹ️  Playwright 未安装，跳过浏览器池测试")
    except Exception as e:
        print(f"❌ 浏览器池测试失败: {e}")


async def test_resilience():
    """测试可靠性模式"""
    print("\n" + "=" * 60)
    print("🔄 测试可靠性模式")
    print("=" * 60 + "\n")

    try:
        from src.core.resilience.retry_policy import (
            RetryExecutor,
            RetryConfig,
            CircuitBreaker,
            CircuitBreakerConfig,
        )

        print("测试重试执行器...\n")

        # 测试重试
        attempt_count = [0]

        async def failing_func():
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise ValueError(f"Attempt {attempt_count[0]} failed")
            return "Success"

        config = RetryConfig(max_attempts=4, base_delay=0.1)
        executor = RetryExecutor(config)

        result = await executor.execute(failing_func)
        print(f"✅ 重试成功: {result} (耗时 {attempt_count[0]} 次尝试)")

        print("\n测试熔断器...\n")

        # 测试熔断器
        cb_config = CircuitBreakerConfig(
            failure_threshold=3,
            timeout_seconds=1,
        )

        breaker = CircuitBreaker("test_service", cb_config)

        async def failing_service():
            raise ValueError("Service error")

        # 触发熔断
        for i in range(3):
            try:
                await breaker.call(failing_service)
            except Exception as exc:
                logging.warning(f"Error: {exc}")

        status = breaker.get_status()
        print(f"✅ 熔断器状态: {status['state']}")
        print(f"   失败计数: {status['failure_count']}")

    except Exception as e:
        print(f"❌ 可靠性模式测试失败: {e}")


async def show_next_steps():
    """显示后续步骤"""
    print("\n" + "=" * 60)
    print("📚 后续步骤")
    print("=" * 60 + "\n")

    steps = """
1️⃣  阅读架构文档
    📄 ARCHITECTURE_ENTERPRISE_UPGRADE.md
    
2️⃣  按照实施指南集成功能
    📄 IMPLEMENTATION_GUIDE.md
    
3️⃣  运行所有测试
    cmd: pytest tests/ --cov=src/
    
4️⃣  部署到生产环境
    📋 检查部署清单
    
5️⃣  监控系统健康
    📊 查看监控仪表板

📞 如需支持，请参考文档顶部的联系方式

"""
    print(steps)


async def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + "  🚀 ShadowBoard 企业级升级 - 快速启动脚本".center(58) + "║")
    print("║" + "  版本 1.0 | Production-Ready".center(58) + "║")
    print("╚" + "=" * 58 + "╝")

    # 环境检查
    env_ok = await check_environment()

    if not env_ok:
        print("\n" + "=" * 60)
        print("⚠️  环境配置建议")
        print("=" * 60 + "\n")
        print("""
1. 安装缺失的依赖包:
   pip install pyjwt cryptography
   
2. 配置环境变量:
   export SHADOW_JWT_SECRET="your-secret-key"
   export SHADOW_MASTER_KEY="your-master-key"
   
3. 创建必要的目录:
   mkdir -p src/core/auth
   mkdir -p src/core/security
   mkdir -p src/core/browser
   mkdir -p src/core/resilience
""")
        return

    # 初始化认证系统
    await init_auth_system()

    # 运行测试
    await test_validation()
    await test_resilience()
    await test_browser_pool()

    # 显示后续步骤
    await show_next_steps()

    print("=" * 60)
    print("✨ 快速启动完成！")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  启动中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
