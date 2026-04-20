"""
Tests for Auth Module

Tests token management, session validation, RBAC, and audit logging.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
import os
from datetime import datetime, timedelta, timezone

# Mock jwt before importing auth modules
with patch("jwt.encode", MagicMock(return_value="mock_token")):
    with patch(
        "jwt.decode",
        MagicMock(
            return_value={
                "sub": "user123",
                "username": "testuser",
                "role": "admin",
                "type": "access",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            }
        ),
    ):
        from src.core.auth import (
            AuthManager,
            RBACManager,
            Role,
            Permission,
            User,
            AuditEvent,
            ROLE_PERMISSIONS,
        )


class TestRole:
    """Test Role enum."""

    def test_role_values(self):
        """Test Role enum values."""
        assert Role.ADMIN.value == "admin"
        assert Role.OPERATOR.value == "operator"
        assert Role.VIEWER.value == "viewer"
        assert Role.SERVICE.value == "service"


class TestPermission:
    """Test Permission enum."""

    def test_permission_task_permissions(self):
        """Test task permission values."""
        assert Permission.TASK_CREATE.value == "task:create"
        assert Permission.TASK_READ.value == "task:read"
        assert Permission.TASK_UPDATE.value == "task:update"
        assert Permission.TASK_DELETE.value == "task:delete"
        assert Permission.TASK_EXECUTE.value == "task:execute"

    def test_permission_workflow_permissions(self):
        """Test workflow permission values."""
        assert Permission.WORKFLOW_CREATE.value == "workflow:create"
        assert Permission.WORKFLOW_READ.value == "workflow:read"
        assert Permission.WORKFLOW_EXECUTE.value == "workflow:execute"

    def test_permission_system_permissions(self):
        """Test system permission values."""
        assert Permission.CONFIG_READ.value == "config:read"
        assert Permission.CONFIG_WRITE.value == "config:write"
        assert Permission.SYSTEM_ADMIN.value == "system:admin"
        assert Permission.AUDIT_READ.value == "audit:read"


class TestRolePermissions:
    """Test ROLE_PERMISSIONS mapping."""

    def test_admin_has_all_permissions(self):
        """Test admin role has all permissions."""
        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
        assert len(admin_perms) == len(Permission)

    def test_operator_permissions(self):
        """Test operator role has correct permissions."""
        operator_perms = ROLE_PERMISSIONS[Role.OPERATOR]
        assert Permission.TASK_CREATE in operator_perms
        assert Permission.TASK_READ in operator_perms
        assert Permission.TASK_EXECUTE in operator_perms
        assert Permission.WORKFLOW_READ in operator_perms
        assert Permission.SYSTEM_ADMIN not in operator_perms

    def test_viewer_permissions(self):
        """Test viewer role has read-only permissions."""
        viewer_perms = ROLE_PERMISSIONS[Role.VIEWER]
        assert Permission.TASK_READ in viewer_perms
        assert Permission.WORKFLOW_READ in viewer_perms
        assert Permission.TASK_CREATE not in viewer_perms
        assert Permission.TASK_DELETE not in viewer_perms

    def test_service_permissions(self):
        """Test service role has execute permissions."""
        service_perms = ROLE_PERMISSIONS[Role.SERVICE]
        assert Permission.TASK_EXECUTE in service_perms
        assert Permission.WORKFLOW_EXECUTE in service_perms
        assert Permission.TASK_CREATE not in service_perms


class TestUser:
    """Test User dataclass."""

    def test_user_creation(self):
        """Test User creation with default values."""
        user = User(
            id="user123",
            username="testuser",
            email="test@example.com",
            role=Role.VIEWER,
        )
        assert user.id == "user123"
        assert user.username == "testuser"
        assert user.role == Role.VIEWER
        assert user.active is True

    def test_user_to_dict_without_sensitive(self):
        """Test User to_dict excludes sensitive data by default."""
        user = User(
            id="user123",
            username="testuser",
            email="test@example.com",
            role=Role.VIEWER,
            password_hash="secret_hash",
        )
        result = user.to_dict()
        assert "password_hash" not in result
        assert result["username"] == "testuser"

    def test_user_to_dict_with_sensitive(self):
        """Test User to_dict includes sensitive when requested."""
        user = User(
            id="user123",
            username="testuser",
            email="test@example.com",
            role=Role.VIEWER,
            password_hash="secret_hash",
        )
        result = user.to_dict(include_sensitive=True)
        assert result["password_hash"] == "secret_hash"


class TestAuditEvent:
    """Test AuditEvent dataclass."""

    def test_audit_event_creation(self):
        """Test AuditEvent creation with defaults."""
        event = AuditEvent(
            user_id="user123",
            action="login",
            resource_type="session",
        )
        assert event.user_id == "user123"
        assert event.action == "login"
        assert event.status == "success"

    def test_audit_event_to_dict(self):
        """Test AuditEvent to_dict conversion."""
        event = AuditEvent(
            user_id="user123",
            action="login",
            resource_type="session",
            resource_id="sess456",
            status="success",
        )
        result = event.to_dict()
        assert result["user_id"] == "user123"
        assert result["action"] == "login"
        assert result["status"] == "success"


class TestRBACManager:
    """Test RBACManager class."""

    def test_get_permissions_admin(self):
        """Test getting admin permissions."""
        perms = RBACManager.get_permissions(Role.ADMIN)
        assert Permission.SYSTEM_ADMIN in perms

    def test_get_permissions_viewer(self):
        """Test getting viewer permissions."""
        perms = RBACManager.get_permissions(Role.VIEWER)
        assert Permission.TASK_READ in perms
        assert Permission.TASK_CREATE not in perms

    def test_has_permission_true(self):
        """Test has_permission returns True for valid permission."""
        result = RBACManager.has_permission(Role.OPERATOR, Permission.TASK_CREATE)
        assert result is True

    def test_has_permission_false(self):
        """Test has_permission returns False for missing permission."""
        result = RBACManager.has_permission(Role.VIEWER, Permission.TASK_CREATE)
        assert result is False

    def test_require_permission_passes(self):
        """Test require_permission passes for valid permission."""
        # Should not raise
        RBACManager.require_permission(Role.ADMIN, Permission.SYSTEM_ADMIN)

    def test_require_permission_raises(self):
        """Test require_permission raises for missing permission."""
        with pytest.raises(PermissionError, match="Permission denied"):
            RBACManager.require_permission(Role.VIEWER, Permission.SYSTEM_ADMIN)


class TestAuthManager:
    """Test AuthManager class."""

    def test_auth_manager_requires_secret_key(self):
        """Test AuthManager requires secret key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="JWT secret key required"):
                AuthManager(secret_key=None)

    def test_auth_manager_with_secret_key(self, tmp_path):
        """Test AuthManager initializes with secret key."""
        with patch.dict(os.environ, {}, clear=True):
            manager = AuthManager(
                secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
                db_path=tmp_path / "test.db",
            )
            assert manager.secret_key == "Str0ng!Secret_Key_32Chars_Min#@!"

    def test_auth_manager_rejects_short_secret_key(self):
        """Test AuthManager rejects secret key that is too short."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="too short"):
                AuthManager(secret_key="shortkey")

    def test_auth_manager_rejects_weak_secret_key_alphanumeric(self):
        """Test AuthManager rejects purely alphanumeric secret key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="special characters"):
                AuthManager(secret_key="abcdefghijklmnopqrstuvwxyz123456")

    def test_auth_manager_rejects_weak_secret_key_common_word(self):
        """Test AuthManager rejects secret key with common weak words."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Weak JWT secret key"):
                AuthManager(secret_key="password1234567890abcdefghijk!!!Pass")

    def test_auth_manager_rejects_secret_key_repeated_chars(self):
        """Test AuthManager rejects secret key with repeated characters."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Weak JWT secret key"):
                AuthManager(secret_key="aaaa1111bbbb2222cccc3333dddd!!!!")

    def test_auth_manager_accepts_strong_secret_key(self):
        """Test AuthManager accepts strong secret key with special chars."""
        with patch.dict(os.environ, {}, clear=True):
            manager = AuthManager(
                secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
            )
            assert manager.secret_key == "Str0ng!Secret_Key_32Chars_Min#@!"

    def test_auth_manager_accepts_long_alphanumeric_key(self):
        """Test AuthManager accepts long key with multiple character types."""
        with patch.dict(os.environ, {}, clear=True):
            # 34 chars, has upper, lower, digit but no special char - should pass (3 types)
            manager = AuthManager(
                secret_key="Abcdefgh1234567890Xyz45678Pqrs90",
            )
            assert manager.secret_key == "Abcdefgh1234567890Xyz45678Pqrs90"

    def test_hash_password_returns_hash(self):
        """Test hash_password returns expected format."""
        password_hash = AuthManager.hash_password("testPassword123")
        assert "$" in password_hash
        parts = password_hash.split("$")
        assert len(parts) == 2

    def test_verify_password_correct(self):
        """Test verify_password returns True for correct password."""
        password_hash = AuthManager.hash_password("testPassword123")
        result = AuthManager.verify_password("testPassword123", password_hash)
        assert result is True

    def test_verify_password_incorrect(self):
        """Test verify_password returns False for incorrect password."""
        password_hash = AuthManager.hash_password("testPassword123")
        result = AuthManager.verify_password("wrongPassword", password_hash)
        assert result is False

    def test_verify_password_malformed_hash(self):
        """Test verify_password returns False for malformed hash."""
        result = AuthManager.verify_password("password", "not_a_valid_hash")
        assert result is False

    def test_create_tokens(self):
        """Test create_tokens returns token dict."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
                token_expiry=3600,
            )
            tokens = manager.create_tokens("user123", "testuser", Role.ADMIN)

            assert "access_token" in tokens
            assert "refresh_token" in tokens
            assert tokens["token_type"] == "Bearer"
            assert tokens["expires_in"] == 3600

    @pytest.mark.asyncio
    async def test_verify_token_valid(self):
        """Test verify_token succeeds for valid token."""
        with patch(
            "jwt.decode",
            MagicMock(
                return_value={
                    "sub": "user123",
                    "username": "testuser",
                    "role": "admin",
                    "type": "access",
                    "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                }
            ),
        ):
            manager = AuthManager(
                secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
                token_expiry=3600,
            )
            payload = await manager.verify_token("valid_token")
            assert payload["sub"] == "user123"

    @pytest.mark.asyncio
    async def test_verify_token_revoked(self):
        """Test verify_token raises for revoked token."""
        manager = AuthManager(
            secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
            token_expiry=3600,
        )
        manager.token_blacklist.add("revoked_token")

        with pytest.raises(ValueError, match="revoked"):
            await manager.verify_token("revoked_token")

    @pytest.mark.asyncio
    async def test_verify_token_wrong_type(self):
        """Test verify_token raises for non-access token."""
        with patch(
            "jwt.decode",
            MagicMock(
                return_value={
                    "sub": "user123",
                    "type": "refresh",  # Not access
                }
            ),
        ):
            manager = AuthManager(
                secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
                token_expiry=3600,
            )

            with pytest.raises(ValueError, match="Invalid token type"):
                await manager.verify_token("refresh_token")

    @pytest.mark.asyncio
    async def test_revoke_token(self):
        """Test revoke_token adds token to blacklist."""
        manager = AuthManager(
            secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
            token_expiry=3600,
        )

        await manager.revoke_token("token_to_revoke")
        assert "token_to_revoke" in manager.token_blacklist

    @pytest.mark.asyncio
    async def test_record_audit(self, tmp_path):
        """Test record_audit stores event."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            event = AuditEvent(
                user_id="user123",
                action="login",
                resource_type="session",
                status="success",
            )

            await manager.record_audit(event)

            # Verify it was stored
            events = await manager.get_audit_logs(user_id="user123")
            assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_get_audit_logs(self, tmp_path):
        """Test get_audit_logs returns events."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            events = await manager.get_audit_logs(limit=10)
            assert isinstance(events, list)


class TestAuthManagerIntegration:
    """Integration tests for AuthManager with mocked DB."""

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, tmp_path):
        """Test authenticate raises for nonexistent user."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            with pytest.raises(ValueError, match="Invalid username or password"):
                await manager.authenticate("nonexistent", "password")

    @pytest.mark.asyncio
    async def test_create_and_authenticate_user(self, tmp_path):
        """Test creating and authenticating a user."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="Str0ng!Secret_Key_32Chars_Min#@!",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            # Create user
            user = await manager.create_user(
                username="testuser",
                email="test@example.com",
                password="testPassword123",
                role=Role.VIEWER,
            )
            assert user.username == "testuser"

            # Authenticate
            tokens = await manager.authenticate("testuser", "testPassword123")
            assert "access_token" in tokens
