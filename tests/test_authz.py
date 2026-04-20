"""
Tests for Authorization (RBAC)

Tests role-based access control, resource protection,
and permission verification.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
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
            RBACManager,
            Role,
            Permission,
        )


class TestRBACAdminPermissions:
    """Test admin role has full permissions."""

    def test_admin_has_all_task_permissions(self):
        """Test admin can perform all task operations."""
        perms = RBACManager.get_permissions(Role.ADMIN)
        assert Permission.TASK_CREATE in perms
        assert Permission.TASK_READ in perms
        assert Permission.TASK_UPDATE in perms
        assert Permission.TASK_DELETE in perms
        assert Permission.TASK_EXECUTE in perms

    def test_admin_has_all_workflow_permissions(self):
        """Test admin can perform all workflow operations."""
        perms = RBACManager.get_permissions(Role.ADMIN)
        assert Permission.WORKFLOW_CREATE in perms
        assert Permission.WORKFLOW_READ in perms
        assert Permission.WORKFLOW_EXECUTE in perms

    def test_admin_has_all_system_permissions(self):
        """Test admin has all system permissions."""
        perms = RBACManager.get_permissions(Role.ADMIN)
        assert Permission.CONFIG_READ in perms
        assert Permission.CONFIG_WRITE in perms
        assert Permission.SYSTEM_ADMIN in perms
        assert Permission.AUDIT_READ in perms

    def test_admin_can_require_any_permission(self):
        """Test admin passes require_permission for any permission."""
        # Should not raise
        RBACManager.require_permission(Role.ADMIN, Permission.TASK_CREATE)
        RBACManager.require_permission(Role.ADMIN, Permission.SYSTEM_ADMIN)
        RBACManager.require_permission(Role.ADMIN, Permission.CONFIG_WRITE)


class TestRBACOperatorPermissions:
    """Test operator role permissions."""

    def test_operator_has_task_crud_permissions(self):
        """Test operator can create, read, update tasks."""
        perms = RBACManager.get_permissions(Role.OPERATOR)
        assert Permission.TASK_CREATE in perms
        assert Permission.TASK_READ in perms
        assert Permission.TASK_UPDATE in perms

    def test_operator_has_execute_permissions(self):
        """Test operator can execute tasks and workflows."""
        perms = RBACManager.get_permissions(Role.OPERATOR)
        assert Permission.TASK_EXECUTE in perms
        assert Permission.WORKFLOW_EXECUTE in perms

    def test_operator_missing_delete_permission(self):
        """Test operator cannot delete tasks."""
        perms = RBACManager.get_permissions(Role.OPERATOR)
        assert Permission.TASK_DELETE not in perms

    def test_operator_missing_system_admin(self):
        """Test operator cannot perform system administration."""
        perms = RBACManager.get_permissions(Role.OPERATOR)
        assert Permission.SYSTEM_ADMIN not in perms
        assert Permission.CONFIG_WRITE not in perms

    def test_operator_require_permission_raises_for_delete(self):
        """Test operator require_permission raises for delete."""
        with pytest.raises(PermissionError, match="Permission denied"):
            RBACManager.require_permission(Role.OPERATOR, Permission.TASK_DELETE)


class TestRBACViewerPermissions:
    """Test viewer role permissions."""

    def test_viewer_has_read_permissions(self):
        """Test viewer can read tasks and workflows."""
        perms = RBACManager.get_permissions(Role.VIEWER)
        assert Permission.TASK_READ in perms
        assert Permission.WORKFLOW_READ in perms

    def test_viewer_missing_write_permissions(self):
        """Test viewer cannot create or modify resources."""
        perms = RBACManager.get_permissions(Role.VIEWER)
        assert Permission.TASK_CREATE not in perms
        assert Permission.TASK_UPDATE not in perms
        assert Permission.TASK_DELETE not in perms
        assert Permission.WORKFLOW_CREATE not in perms

    def test_viewer_missing_execute_permissions(self):
        """Test viewer cannot execute anything."""
        perms = RBACManager.get_permissions(Role.VIEWER)
        assert Permission.TASK_EXECUTE not in perms
        assert Permission.WORKFLOW_EXECUTE not in perms

    def test_viewer_require_permission_raises_for_create(self):
        """Test viewer require_permission raises for create."""
        with pytest.raises(PermissionError, match="Permission denied"):
            RBACManager.require_permission(Role.VIEWER, Permission.TASK_CREATE)


class TestRBACServicePermissions:
    """Test service role permissions."""

    def test_service_has_execute_permissions(self):
        """Test service can execute tasks and workflows."""
        perms = RBACManager.get_permissions(Role.SERVICE)
        assert Permission.TASK_EXECUTE in perms
        assert Permission.WORKFLOW_EXECUTE in perms

    def test_service_missing_crud_permissions(self):
        """Test service cannot create, read, update, or delete."""
        perms = RBACManager.get_permissions(Role.SERVICE)
        assert Permission.TASK_CREATE not in perms
        assert Permission.TASK_READ not in perms
        assert Permission.TASK_UPDATE not in perms
        assert Permission.TASK_DELETE not in perms

    def test_service_require_permission_raises_for_read(self):
        """Test service require_permission raises for read."""
        with pytest.raises(PermissionError, match="Permission denied"):
            RBACManager.require_permission(Role.SERVICE, Permission.TASK_READ)


class TestResourceAccessControl:
    """Test resource access control scenarios."""

    def test_unauthorized_user_cannot_access_protected_resource(self):
        """Test viewer cannot access system admin resources."""
        result = RBACManager.has_permission(Role.VIEWER, Permission.SYSTEM_ADMIN)
        assert result is False

    def test_cross_role_access_operator_to_admin_resource(self):
        """Test operator cannot access admin-only config."""
        result = RBACManager.has_permission(Role.OPERATOR, Permission.CONFIG_WRITE)
        assert result is False

    def test_cross_role_access_viewer_to_workflow_create(self):
        """Test viewer cannot create workflows."""
        result = RBACManager.has_permission(Role.VIEWER, Permission.WORKFLOW_CREATE)
        assert result is False

    def test_admin_can_access_all_resource_types(self):
        """Test admin can access any resource type."""
        admin_perms = RBACManager.get_permissions(Role.ADMIN)
        resource_permissions = [
            Permission.TASK_CREATE,
            Permission.TASK_READ,
            Permission.TASK_UPDATE,
            Permission.TASK_DELETE,
            Permission.CONFIG_WRITE,
            Permission.AUDIT_READ,
            Permission.SYSTEM_ADMIN,
        ]
        for perm in resource_permissions:
            assert perm in admin_perms, f"Admin should have {perm}"


class TestPermissionChecks:
    """Test permission verification for CRUD operations."""

    def test_admin_can_create(self):
        """Test admin has create permission."""
        assert RBACManager.has_permission(Role.ADMIN, Permission.TASK_CREATE) is True

    def test_admin_can_read(self):
        """Test admin has read permission."""
        assert RBACManager.has_permission(Role.ADMIN, Permission.TASK_READ) is True

    def test_admin_can_update(self):
        """Test admin has update permission."""
        assert RBACManager.has_permission(Role.ADMIN, Permission.TASK_UPDATE) is True

    def test_admin_can_delete(self):
        """Test admin has delete permission."""
        assert RBACManager.has_permission(Role.ADMIN, Permission.TASK_DELETE) is True

    def test_viewer_cannot_create(self):
        """Test viewer lacks create permission."""
        assert RBACManager.has_permission(Role.VIEWER, Permission.TASK_CREATE) is False

    def test_viewer_cannot_update(self):
        """Test viewer lacks update permission."""
        assert RBACManager.has_permission(Role.VIEWER, Permission.TASK_UPDATE) is False

    def test_viewer_cannot_delete(self):
        """Test viewer lacks delete permission."""
        assert RBACManager.has_permission(Role.VIEWER, Permission.TASK_DELETE) is False


class TestEdgeCases:
    """Test edge cases for authorization."""

    def test_invalid_role_returns_empty_permissions(self):
        """Test invalid role has no permissions."""
        # Using a role that doesn't exist in ROLE_PERMISSIONS
        # Note: All Role enum values should be in ROLE_PERMISSIONS
        # So we test with role=None handling
        perms = RBACManager.get_permissions(None)
        assert perms == set()

    def test_has_permission_with_none_role(self):
        """Test has_permission returns False for None role."""
        result = RBACManager.has_permission(None, Permission.TASK_READ)
        assert result is False

    def test_require_permission_with_none_role_raises(self):
        """Test require_permission raises AttributeError for None role."""
        with pytest.raises(AttributeError):
            RBACManager.require_permission(None, Permission.TASK_READ)

    def test_require_permission_with_none_permission_raises(self):
        """Test require_permission raises AttributeError for None permission."""
        with pytest.raises(AttributeError):
            RBACManager.require_permission(Role.ADMIN, None)

    def test_admin_has_correct_permission_count(self):
        """Test admin has exactly all defined permissions."""
        admin_perms = RBACManager.get_permissions(Role.ADMIN)
        all_perms = set(Permission)
        assert admin_perms == all_perms


class TestRoleHierarchy:
    """Test role hierarchy and privilege escalation."""

    def test_admin_has_more_permissions_than_operator(self):
        """Test admin has more permissions than operator."""
        admin_perms = RBACManager.get_permissions(Role.ADMIN)
        operator_perms = RBACManager.get_permissions(Role.OPERATOR)
        assert len(admin_perms) > len(operator_perms)

    def test_admin_has_more_permissions_than_viewer(self):
        """Test admin has more permissions than viewer."""
        admin_perms = RBACManager.get_permissions(Role.ADMIN)
        viewer_perms = RBACManager.get_permissions(Role.VIEWER)
        assert len(admin_perms) > len(viewer_perms)

    def test_operator_has_more_permissions_than_viewer(self):
        """Test operator has more permissions than viewer."""
        operator_perms = RBACManager.get_permissions(Role.OPERATOR)
        viewer_perms = RBACManager.get_permissions(Role.VIEWER)
        assert len(operator_perms) > len(viewer_perms)
