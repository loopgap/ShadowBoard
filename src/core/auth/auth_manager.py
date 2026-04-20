"""
Authentication Manager - 企业级认证与授权

提供完整的认证流程:
- JWT 令牌管理
- 角色-权限管理 (RBAC)
- 审计日志

此模块是拆分后的主入口点，保持向后兼容。
实际实现已拆分到:
- session_manager: 会话管理
- password_reset: 密码重置
- lockout_manager: 账户锁定
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Set

import jwt
import sqlite3

from src.utils.i18n import t

# 导入拆分出去的模块
from src.core.auth.session_manager import (
    SessionManager,
    AuthSession,
)
from src.core.auth.password_reset import (
    PasswordResetManager,
    PasswordResetToken,
)
from src.core.auth.lockout_manager import (
    AccountLockoutManager,
    FailedLoginAttempt,
)

# 重新导出这些类，保持向后兼容
__all__ = [
    'Role',
    'Permission',
    'ROLE_PERMISSIONS',
    'User',
    'AuditEvent',
    'AuthSession',
    'PasswordResetToken',
    'FailedLoginAttempt',
    'AuthManager',
    'RBACManager',
    'SessionManager',
    'PasswordResetManager',
    'AccountLockoutManager',
]


class Role(Enum):
    """预定义角色"""

    ADMIN = "admin"  # 系统管理员
    OPERATOR = "operator"  # 操作员
    VIEWER = "viewer"  # 查看者
    SERVICE = "service"  # 服务账户


class Permission(Enum):
    """权限定义"""

    # 任务管理
    TASK_CREATE = "task:create"
    TASK_READ = "task:read"
    TASK_UPDATE = "task:update"
    TASK_DELETE = "task:delete"
    TASK_EXECUTE = "task:execute"

    # 工作流管理
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_EXECUTE = "workflow:execute"

    # 系统管理
    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"
    SYSTEM_ADMIN = "system:admin"
    AUDIT_READ = "audit:read"


# 角色权限映射
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.ADMIN: set(Permission),  # 所有权限
    Role.OPERATOR: {
        Permission.TASK_CREATE,
        Permission.TASK_READ,
        Permission.TASK_UPDATE,
        Permission.TASK_EXECUTE,
        Permission.WORKFLOW_READ,
        Permission.WORKFLOW_EXECUTE,
    },
    Role.VIEWER: {
        Permission.TASK_READ,
        Permission.WORKFLOW_READ,
    },
    Role.SERVICE: {
        Permission.TASK_EXECUTE,
        Permission.WORKFLOW_EXECUTE,
    },
}


@dataclass
class User:
    """用户信息"""

    id: str
    username: str
    email: str
    role: Role
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # 内部字段
    password_hash: str = ""  # 仅用于存储，不传输

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        if include_sensitive:
            data["password_hash"] = self.password_hash

        return data


@dataclass
class AuditEvent:
    """审计事件"""

    id: str = field(default_factory=lambda: secrets.token_urlsafe(8))
    timestamp: datetime = field(default_factory=datetime.now)
    user_id: str = ""
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    status: str = "success"  # success, failure
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    user_agent: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuthManager:
    """核心认证管理器"""

    # 类级别的默认数据库路径，用于单例
    _default_db_path = Path(".semi_agent/auth.db")

    def __init__(
        self,
        secret_key: str = None,
        db_path: Path = None,
        token_expiry: int = 3600,
    ):
        """
        初始化认证管理器

        Args:
            secret_key: JWT 密钥（从环境变量获取）
            db_path: 数据库路径（默认 :memory: 用于测试隔离）
            token_expiry: 令牌过期时间（秒）
        """
        self.secret_key = secret_key or os.getenv("SHADOW_JWT_SECRET")
        if not self.secret_key:
            raise ValueError(t("errors.jwt_secret_required"))

        # 如果指定了 db_path，使用它；否则使用共享内存数据库（隔离）
        if db_path is not None:
            self.db_path = db_path
            self._is_memory_db = False
        else:
            # 使用共享内存数据库URI，确保同一实例的连接共享数据
            self.db_path = None  # Will use URI
            self._is_memory_db = True

        self._validate_secret_key()

        self.token_expiry = token_expiry
        self.token_blacklist: Set[str] = set()
        self._lock = asyncio.Lock()

        # 为内存数据库保持一个持久连接
        if self._is_memory_db:
            self._memory_conn = sqlite3.connect("file::memory:?cache=shared", uri=True)
            self._init_db(self._memory_conn)
        else:
            self._memory_conn = None
            self._init_db()
            self._load_blacklist_from_db()

    def _get_connection(self):
        """获取数据库连接"""
        if self._is_memory_db:
            return self._memory_conn
        return sqlite3.connect(self.db_path)

    def _init_db(self, conn=None):
        """初始化数据库"""
        external_conn = conn is not None

        if not external_conn:
            conn = self._get_connection()

        try:
            if not self._is_memory_db:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            # 用户表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    active BOOLEAN DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            # 审计日志表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    user_id TEXT,
                    action TEXT,
                    resource_type TEXT,
                    resource_id TEXT,
                    status TEXT,
                    details TEXT,
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)

            # 令牌黑名单表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blacklisted_tokens (
                    token TEXT PRIMARY KEY,
                    revoked_at TEXT NOT NULL
                )
            """)

            # 索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_events(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp)")

            # 认证会话表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TEXT NOT NULL,
                    last_activity TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    active BOOLEAN DEFAULT 1
                )
            """)

            # 密码重置令牌表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used BOOLEAN DEFAULT 0
                )
            """)

            # 失败登录尝试表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failed_login_attempts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    ip_address TEXT,
                    attempted_at TEXT NOT NULL,
                    locked_until TEXT
                )
            """)

            # 会话相关索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON auth_sessions(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON auth_sessions(expires_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reset_tokens_user_id ON password_reset_tokens(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_failed_attempts_user_id ON failed_login_attempts(user_id)")

            conn.commit()
        finally:
            if not external_conn and not self._is_memory_db:
                conn.close()

    def _load_blacklist_from_db(self):
        """从数据库加载令牌黑名单"""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.execute("SELECT token FROM blacklisted_tokens")
                for row in cursor.fetchall():
                    self.token_blacklist.add(row[0])
            finally:
                if not self._is_memory_db:
                    conn.close()
        except sqlite3.OperationalError:
            # 表尚不存在（初始化期间）
            pass

    def _validate_secret_key(self):
        """验证JWT密钥强度"""
        # 长度检查 - 必须至少32字符
        if len(self.secret_key) < 32:
            raise ValueError(
                f"JWT secret key is too short ({len(self.secret_key)} chars). "
                f"Must be at least 32 characters."
            )

        # 弱密钥模式检测
        weak_patterns = [
            r"^(password|secret|jwt|token|auth)",  # 常见弱词
            r"(.)\1{3,}",  # 重复字符超过3次
        ]

        for pattern in weak_patterns:
            if re.match(pattern, self.secret_key, re.IGNORECASE):
                raise ValueError(
                    "Weak JWT secret key detected. "
                    "Consider using a longer, more complex key (32+ characters with special characters)."
                )

        # 检查是否仅包含字母数字（需要包含特殊字符或多种字符类型）
        is_pure_alphanumeric = self.secret_key.isalnum()
        has_uppercase = bool(re.search(r"[A-Z]", self.secret_key))
        has_lowercase = bool(re.search(r"[a-z]", self.secret_key))
        has_digit = bool(re.search(r"[0-9]", self.secret_key))
        has_special = bool(re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", self.secret_key))

        # 计算字符类型种类数
        char_type_count = sum([has_uppercase, has_lowercase, has_digit, has_special])

        # 如果是纯字母数字且只有1-2种类型，或者纯数字/纯字母
        if is_pure_alphanumeric and char_type_count <= 2:
            raise ValueError(
                f"JWT secret key must contain special characters or multiple character types "
                f"(uppercase, lowercase, digits). Current: alnum={is_pure_alphanumeric}, "
                f"types={char_type_count}."
            )

    @staticmethod
    def hash_password(password: str, salt: str = None) -> str:
        """密码哈希"""
        if salt is None:
            salt = secrets.token_hex(16)

        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)

        return f"{salt}${hashed.hex()}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """验证密码"""
        try:
            salt, _ = password_hash.split("$")
            hashed_attempt = AuthManager.hash_password(password, salt)
            return hashed_attempt == password_hash
        except (ValueError, AttributeError):
            return False

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        role: Role = Role.VIEWER,
    ) -> User:
        """创建用户"""
        async with self._lock:
            user_id = secrets.token_urlsafe(16)
            password_hash = self.hash_password(password)
            now = datetime.now()

            user = User(
                id=user_id,
                username=username,
                email=email,
                role=role,
                password_hash=password_hash,
                created_at=now,
                updated_at=now,
            )

            # 存储到数据库
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO users
                    (id, username, email, role, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        user.id,
                        user.username,
                        user.email,
                        user.role.value,
                        user.password_hash,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                conn.commit()
            finally:
                if not self._is_memory_db:
                    conn.close()

            return user

    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> Dict[str, str]:
        """用户登录"""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
        finally:
            if not self._is_memory_db:
                conn.close()

        if not row:
            raise ValueError(t("errors.invalid_credentials"))

        user_id, username, email, role, password_hash, active, _, _ = row

        if not active:
            raise ValueError(t("errors.account_disabled"))

        if not self.verify_password(password, password_hash):
            raise ValueError(t("errors.invalid_credentials"))

        # 生成令牌
        return self.create_tokens(user_id, username, Role[role.upper()])

    def create_tokens(
        self,
        user_id: str,
        username: str,
        role: Role,
    ) -> Dict[str, str]:
        """生成访问和刷新令牌"""
        now = datetime.now(timezone.utc)

        # 访问令牌
        access_payload = {
            "sub": user_id,
            "username": username,
            "role": role.value,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(seconds=self.token_expiry),
        }

        access_token = jwt.encode(access_payload, self.secret_key, algorithm="HS256")

        # 刷新令牌
        refresh_payload = {
            "sub": user_id,
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=7),
        }

        refresh_token = jwt.encode(refresh_payload, self.secret_key, algorithm="HS256")

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": self.token_expiry,
        }

    async def verify_token(self, token: str) -> Dict[str, Any]:
        """验证令牌"""
        if token in self.token_blacklist:
            raise ValueError(t("errors.token_revoked"))

        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])

            if payload.get("type") != "access":
                raise ValueError(t("errors.invalid_token_type"))

            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError(t("errors.token_expired"))
        except jwt.InvalidTokenError as e:
            raise ValueError(t("errors.invalid_token", error=str(e)))

    async def revoke_token(self, token: str):
        """撤销令牌"""
        async with self._lock:
            self.token_blacklist.add(token)
            # 持久化到数据库
            conn = self._get_connection()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO blacklisted_tokens (token, revoked_at) VALUES (?, ?)",
                    (token, datetime.now().isoformat()),
                )
                conn.commit()
            finally:
                if not self._is_memory_db:
                    conn.close()

    async def record_audit(
        self,
        event: AuditEvent,
    ) -> None:
        """记录审计事件"""
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO audit_events
                (id, timestamp, user_id, action, resource_type, resource_id, status, details, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    event.id,
                    event.timestamp.isoformat(),
                    event.user_id,
                    event.action,
                    event.resource_type,
                    event.resource_id,
                    event.status,
                    json.dumps(event.details),
                    event.ip_address,
                    event.user_agent,
                ),
            )
            conn.commit()
        finally:
            if not self._is_memory_db:
                conn.close()

    async def get_audit_logs(
        self,
        user_id: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """获取审计日志"""
        query = "SELECT * FROM audit_events"
        params = []

        if user_id:
            query += " WHERE user_id = ?"
            params.append(user_id)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        events = []
        conn = self._get_connection()
        try:
            cursor = conn.execute(query, params)
            for row in cursor.fetchall():
                event = AuditEvent(
                    id=row[0],
                    timestamp=datetime.fromisoformat(row[1]),
                    user_id=row[2],
                    action=row[3],
                    resource_type=row[4],
                    resource_id=row[5],
                    status=row[6],
                    details=json.loads(row[7]) if row[7] else {},
                    ip_address=row[8],
                    user_agent=row[9],
                )
                events.append(event)
        finally:
            if not self._is_memory_db:
                conn.close()

        return events


class RBACManager:
    """基于角色的访问控制"""

    @staticmethod
    def get_permissions(role: Role) -> Set[Permission]:
        """获取角色的权限集合"""
        return ROLE_PERMISSIONS.get(role, set())

    @staticmethod
    def has_permission(role: Role, permission: Permission) -> bool:
        """检查角色是否有权限"""
        permissions = RBACManager.get_permissions(role)
        return permission in permissions

    @staticmethod
    def require_permission(role: Role, permission: Permission) -> None:
        """要求权限（无则抛出异常）"""
        if not RBACManager.has_permission(role, permission):
            raise PermissionError(t("errors.permission_denied", role=role.value, permission=permission.value))