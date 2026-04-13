"""
Authentication Manager - 企业级认证与授权

提供完整的认证流程:
- JWT 令牌管理
- 角色-权限管理 (RBAC)
- 审计日志
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Set

import jwt
import sqlite3


class Role(Enum):
    """预定义角色"""
    ADMIN = "admin"           # 系统管理员
    OPERATOR = "operator"     # 操作员
    VIEWER = "viewer"         # 查看者
    SERVICE = "service"       # 服务账户


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
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role.value,
            'active': self.active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        
        if include_sensitive:
            data['password_hash'] = self.password_hash
        
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
            db_path: 数据库路径
            token_expiry: 令牌过期时间（秒）
        """
        import os
        self.secret_key = secret_key or os.getenv('SHADOW_JWT_SECRET')
        if not self.secret_key:
            raise ValueError("JWT secret key required")
        
        self.db_path = db_path or Path(".semi_agent/auth.db")
        self.token_expiry = token_expiry
        self.token_blacklist: Set[str] = set()
        self._lock = asyncio.Lock()
        
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
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
            
            # 索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_events(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp)")
            conn.commit()
    
    @staticmethod
    def hash_password(password: str, salt: str = None) -> str:
        """密码哈希"""
        if salt is None:
            salt = secrets.token_hex(16)
        
        hashed = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            salt.encode(),
            100000
        )
        
        return f"{salt}${hashed.hex()}"
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """验证密码"""
        try:
            salt, _ = password_hash.split('$')
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
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO users 
                    (id, username, email, role, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user.id,
                    user.username,
                    user.email,
                    user.role.value,
                    user.password_hash,
                    now.isoformat(),
                    now.isoformat(),
                ))
                conn.commit()
            
            return user
    
    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> Dict[str, str]:
        """用户登录"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            )
            row = cursor.fetchone()
        
        if not row:
            raise ValueError("Invalid username or password")
        
        user_id, username, email, role, password_hash, active, _, _ = row
        
        if not active:
            raise ValueError("User account is disabled")
        
        if not self.verify_password(password, password_hash):
            raise ValueError("Invalid username or password")
        
        # 生成令牌
        return self.create_tokens(user_id, username, Role[role.upper()])
    
    def create_tokens(
        self,
        user_id: str,
        username: str,
        role: Role,
    ) -> Dict[str, str]:
        """生成访问和刷新令牌"""
        now = datetime.utcnow()
        
        # 访问令牌
        access_payload = {
            'sub': user_id,
            'username': username,
            'role': role.value,
            'type': 'access',
            'iat': now,
            'exp': now + timedelta(seconds=self.token_expiry),
        }
        
        access_token = jwt.encode(
            access_payload,
            self.secret_key,
            algorithm='HS256'
        )
        
        # 刷新令牌
        refresh_payload = {
            'sub': user_id,
            'type': 'refresh',
            'iat': now,
            'exp': now + timedelta(days=7),
        }
        
        refresh_token = jwt.encode(
            refresh_payload,
            self.secret_key,
            algorithm='HS256'
        )
        
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'Bearer',
            'expires_in': self.token_expiry,
        }
    
    async def verify_token(self, token: str) -> Dict[str, Any]:
        """验证令牌"""
        if token in self.token_blacklist:
            raise ValueError("Token has been revoked")
        
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=['HS256']
            )
            
            if payload.get('type') != 'access':
                raise ValueError("Invalid token type")
            
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {e}")
    
    async def revoke_token(self, token: str):
        """撤销令牌"""
        async with self._lock:
            self.token_blacklist.add(token)
    
    async def record_audit(
        self,
        event: AuditEvent,
    ) -> None:
        """记录审计事件"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO audit_events 
                (id, timestamp, user_id, action, resource_type, resource_id, status, details, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
            ))
            conn.commit()
    
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
        with sqlite3.connect(self.db_path) as conn:
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
            raise PermissionError(
                f"Permission denied: {role.value} requires {permission.value}"
            )
