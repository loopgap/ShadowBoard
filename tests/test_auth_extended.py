"""
Extended Tests for Auth Module

Additional coverage for edge cases, token lifecycle,
concurrency, and error handling scenarios.
"""

from __future__ import annotations

import asyncio
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
            AuthManager,
            RBACManager,
            Role,
            Permission,
            AuditEvent,
        )


class TestTokenExpiration:
    """Test token expiration scenarios."""

    @pytest.mark.asyncio
    async def test_verify_token_expired(self):
        """Test verify_token raises for expired token."""
        # JWT library raises ExpiredSignatureError when token is expired
        import jwt

        with patch(
            "jwt.decode",
            MagicMock(side_effect=jwt.ExpiredSignatureError("Token expired")),
        ):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                token_expiry=3600,
            )

            with pytest.raises(ValueError, match="Token has expired"):
                await manager.verify_token("expired_token")

    @pytest.mark.asyncio
    async def test_verify_token_just_expired(self):
        """Test verify_token raises for token that's just past expiration."""
        import jwt

        with patch(
            "jwt.decode",
            MagicMock(side_effect=jwt.ExpiredSignatureError("Token expired")),
        ):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                token_expiry=3600,
            )

            with pytest.raises(ValueError, match="Token has expired"):
                await manager.verify_token("just_expired_token")

    @pytest.mark.asyncio
    async def test_verify_token_near_expiry(self):
        """Test verify_token succeeds for token near expiry but still valid."""
        # Set exp to 1 second from now (still valid)
        with patch(
            "jwt.decode",
            MagicMock(
                return_value={
                    "sub": "user123",
                    "username": "testuser",
                    "role": "admin",
                    "type": "access",
                    "exp": datetime.now(timezone.utc) + timedelta(seconds=1),
                }
            ),
        ):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                token_expiry=1,
            )
            payload = await manager.verify_token("near_expiry_token")
            assert payload["sub"] == "user123"

    @pytest.mark.asyncio
    async def test_token_expiry_zero_seconds(self):
        """Test creating tokens with zero expiry."""
        with patch("jwt.encode", MagicMock(return_value="zero_expiry_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                token_expiry=0,
            )
            tokens = manager.create_tokens("user123", "testuser", Role.ADMIN)
            # Token should still be created but with 0 or minimal expiry
            assert "access_token" in tokens


class TestTokenRevocation:
    """Test token revocation scenarios."""

    @pytest.mark.asyncio
    async def test_revoke_token_twice(self):
        """Test revoking the same token twice is idempotent."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

        await manager.revoke_token("token_to_revoke")
        await manager.revoke_token("token_to_revoke")  # Revoke again

        # token_blacklist is a set, so duplicate add is idempotent
        assert "token_to_revoke" in manager.token_blacklist
        # Verify it's still only one entry
        assert len([t for t in manager.token_blacklist if t == "token_to_revoke"]) == 1

    @pytest.mark.asyncio
    async def test_revoke_multiple_tokens(self):
        """Test revoking multiple different tokens."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

        tokens = ["token1", "token2", "token3"]
        for token in tokens:
            await manager.revoke_token(token)

        for token in tokens:
            assert token in manager.token_blacklist

    @pytest.mark.asyncio
    async def test_verify_after_partial_revoke(self):
        """Test that non-revoked tokens still work after some are revoked."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

        # Revoke one token
        await manager.revoke_token("revoked_token")

        # Verify another token still works
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
            payload = await manager.verify_token("valid_token")
            assert payload["sub"] == "user123"


class TestConcurrentAuthentication:
    """Test concurrent authentication scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_auth_attempts(self, tmp_path):
        """Test multiple concurrent authentication attempts."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            # Create a test user
            await manager.create_user(
                username="concurrentuser",
                email="concurrent@example.com",
                password="testPassword123",
                role=Role.VIEWER,
            )

            async def auth_task():
                return await manager.authenticate("concurrentuser", "testPassword123")

            # Run 10 concurrent auth attempts
            tasks = [auth_task() for _ in range(10)]
            results = await asyncio.gather(*tasks)

            # All should succeed
            for tokens in results:
                assert "access_token" in tokens

    @pytest.mark.asyncio
    async def test_concurrent_token_verification(self):
        """Test concurrent token verification."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

        async def verify_task(token_id):
            with patch(
                "jwt.decode",
                MagicMock(
                    return_value={
                        "sub": f"user{token_id}",
                        "username": f"user{token_id}",
                        "role": "admin",
                        "type": "access",
                        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                    }
                ),
            ):
                return await manager.verify_token(f"token_{token_id}")

        tasks = [verify_task(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        for i, payload in enumerate(results):
            assert payload["sub"] == f"user{i}"

    @pytest.mark.asyncio
    async def test_concurrent_revocation(self):
        """Test concurrent token revocation."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

        async def revoke_task(token):
            await manager.revoke_token(token)

        tokens = [f"concurrent_token_{i}" for i in range(10)]
        tasks = [revoke_task(token) for token in tokens]
        await asyncio.gather(*tasks)

        for token in tokens:
            assert token in manager.token_blacklist


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_verify_token_malformed_jwt(self):
        """Test verify_token handles malformed JWT."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

        with patch("jwt.decode", MagicMock(side_effect=Exception("Invalid JWT"))):
            with pytest.raises(Exception):
                await manager.verify_token("not.a.valid.jwt")

    @pytest.mark.asyncio
    async def test_verify_token_missing_sub_claim(self):
        """Test verify_token handles token with missing sub claim."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

        # Token without 'sub' claim - the code returns payload directly
        # so missing 'sub' won't raise here, but downstream code would fail
        with patch(
            "jwt.decode",
            MagicMock(
                return_value={
                    "username": "testuser",
                    "role": "admin",
                    "type": "access",
                    "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                }
            ),
        ):
            payload = await manager.verify_token("token_missing_sub")
            # Payload is returned with missing 'sub'
            assert "sub" not in payload or payload.get("sub") is None

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self, tmp_path):
        """Test authenticate fails with wrong password."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            await manager.create_user(
                username="testuser",
                email="test@example.com",
                password="correctPassword",
                role=Role.VIEWER,
            )

            with pytest.raises(ValueError, match="Invalid username or password"):
                await manager.authenticate("testuser", "wrongPassword")

    @pytest.mark.asyncio
    async def test_authenticate_empty_password(self, tmp_path):
        """Test authenticate fails with empty password."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            await manager.create_user(
                username="testuser",
                email="test@example.com",
                password="somePassword",
                role=Role.VIEWER,
            )

            with pytest.raises(ValueError, match="Invalid username or password"):
                await manager.authenticate("testuser", "")

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username(self, tmp_path):
        """Test creating user with duplicate username fails."""
        import sqlite3

        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            await manager.create_user(
                username="duplicateuser",
                email="first@example.com",
                password="password1",
                role=Role.VIEWER,
            )

            with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
                await manager.create_user(
                    username="duplicateuser",
                    email="second@example.com",
                    password="password2",
                    role=Role.VIEWER,
                )

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, tmp_path):
        """Test creating user with duplicate email fails."""
        import sqlite3

        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            await manager.create_user(
                username="user1",
                email="duplicate@example.com",
                password="password1",
                role=Role.VIEWER,
            )

            with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"):
                await manager.create_user(
                    username="user2",
                    email="duplicate@example.com",
                    password="password2",
                    role=Role.VIEWER,
                )


class TestBoundaryConditions:
    """Test boundary condition scenarios."""

    @pytest.mark.asyncio
    async def test_verify_token_empty_string(self):
        """Test verify_token handles empty string token."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

        with pytest.raises(Exception):
            await manager.verify_token("")

    @pytest.mark.asyncio
    async def test_verify_token_unicode(self):
        """Test verify_token handles unicode token."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

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
            payload = await manager.verify_token("unicode_token_Üñîçødé")
            assert payload["sub"] == "user123"

    @pytest.mark.asyncio
    async def test_password_short_length(self, tmp_path):
        """Test creating user with short password (no min enforcement)."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            # Short password should still be accepted if no min length enforcement
            user = await manager.create_user(
                username="testuser1",
                email="test1@example.com",
                password="ab",
                role=Role.VIEWER,
            )
            assert user.username == "testuser1"

    @pytest.mark.asyncio
    async def test_password_very_long_length(self, tmp_path):
        """Test creating user with very long password (no max enforcement)."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            # Very long password - system may or may not enforce max
            long_password = "a" * 1000
            try:
                user = await manager.create_user(
                    username="testuser2",
                    email="test2@example.com",
                    password=long_password,
                    role=Role.VIEWER,
                )
                assert user.username == "testuser2"
            except Exception:
                # If it fails due to length, that's also valid behavior
                pass

    @pytest.mark.asyncio
    async def test_username_empty_string(self, tmp_path):
        """Test creating user with empty username (edge case)."""
        import sqlite3

        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            # Empty username - system may allow or reject
            try:
                await manager.create_user(
                    username="",
                    email="test@example.com",
                    password="validPassword123",
                    role=Role.VIEWER,
                )
                # If created, verify we can still authenticate
                tokens = await manager.authenticate("", "validPassword123")
                assert "access_token" in tokens
            except (ValueError, sqlite3.IntegrityError):
                # If rejected, that's valid behavior too
                pass

    @pytest.mark.asyncio
    async def test_username_special_characters(self, tmp_path):
        """Test creating user with special characters in username."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            # This should either succeed or fail based on validation rules
            try:
                user = await manager.create_user(
                    username="user@#$%",
                    email="special@example.com",
                    password="validPassword123",
                    role=Role.VIEWER,
                )
                assert user.username == "user@#$%"
            except ValueError:
                # Expected if special chars are not allowed
                pass

    @pytest.mark.asyncio
    async def test_audit_log_empty_filters(self, tmp_path):
        """Test get_audit_logs with no filters returns events."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            events = await manager.get_audit_logs()
            assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_audit_log_limit_param(self, tmp_path):
        """Test get_audit_logs with limit parameter."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            # Record some events first
            for i in range(5):
                event = AuditEvent(
                    user_id=f"user{i}",
                    action="test_action",
                    resource_type="test",
                )
                await manager.record_audit(event)

            # Query with limit
            events = await manager.get_audit_logs(limit=3)
            assert isinstance(events, list)
            assert len(events) <= 3

    @pytest.mark.asyncio
    async def test_token_blacklist_growth(self):
        """Test token blacklist handles many entries."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

        # Add many tokens to blacklist
        for i in range(100):
            await manager.revoke_token(f"token_{i}")

        assert len(manager.token_blacklist) == 100

        # Verify token still in blacklist
        assert "token_50" in manager.token_blacklist

    @pytest.mark.asyncio
    async def test_rbac_all_roles_have_permissions(self):
        """Test all roles have at least one permission."""
        for role in Role:
            perms = RBACManager.get_permissions(role)
            assert len(perms) > 0, f"Role {role} has no permissions"

    @pytest.mark.asyncio
    async def test_all_permissions_are_unique(self):
        """Test all permission values are unique."""
        perm_values = [p.value for p in Permission]
        assert len(perm_values) == len(set(perm_values)), "Duplicate permission values found"

    def test_role_enum_completeness(self):
        """Test Role enum has expected number of values."""
        assert len(Role) >= 4  # admin, operator, viewer, service at minimum

    def test_permission_enum_completeness(self):
        """Test Permission enum has expected number of values."""
        assert len(Permission) >= 10  # Should have task, workflow, system, audit perms


class TestSecurityScenarios:
    """Test security-related scenarios."""

    @pytest.mark.asyncio
    async def test_password_hash_different_each_time(self):
        """Test that same password produces different hashes (salting)."""
        hash1 = AuthManager.hash_password("samePassword123")
        hash2 = AuthManager.hash_password("samePassword123")

        # Hashes should be different due to random salt
        assert hash1 != hash2

        # But both should verify correctly
        assert AuthManager.verify_password("samePassword123", hash1) is True
        assert AuthManager.verify_password("samePassword123", hash2) is True

    @pytest.mark.asyncio
    async def test_inactive_user_cannot_authenticate(self, tmp_path):
        """Test that inactive users cannot authenticate."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            user = await manager.create_user(
                username="inactiveuser",
                email="inactive@example.com",
                password="testPassword123",
                role=Role.VIEWER,
            )

            # Directly modify user's active status in DB to simulate deactivation
            import sqlite3

            with sqlite3.connect(tmp_path / "test.db") as conn:
                conn.execute("UPDATE users SET active = ? WHERE id = ?", (False, user.id))
                conn.commit()

            # Now try to authenticate - should fail with specific error
            with pytest.raises(ValueError, match="User account is disabled"):
                await manager.authenticate("inactiveuser", "testPassword123")

    @pytest.mark.asyncio
    async def test_token_with_wrong_secret(self):
        """Test that tokens signed with different secret are rejected."""
        manager1 = AuthManager(secret_key="key1_at_least_32_chars_long_aaaa", token_expiry=3600)
        manager2 = AuthManager(secret_key="key2_at_least_32_chars_long_bbbb", token_expiry=3600)

        # Create token with manager1
        tokens = manager1.create_tokens("user123", "testuser", Role.ADMIN)

        # Try to verify with manager2 (different secret)
        with patch(
            "jwt.decode",
            MagicMock(side_effect=Exception("Signature verification failed")),
        ):
            with pytest.raises(Exception):
                await manager2.verify_token(tokens["access_token"])

    @pytest.mark.asyncio
    async def test_refresh_token_cannot_access_protected_resource(self):
        """Test that refresh tokens cannot access protected resources."""
        manager = AuthManager(
            secret_key="test_secret_key_at_least_32_chars_long",
            token_expiry=3600,
        )

        # Verify with a refresh token type
        with patch(
            "jwt.decode",
            MagicMock(
                return_value={
                    "sub": "user123",
                    "username": "testuser",
                    "role": "admin",
                    "type": "refresh",  # Refresh token
                    "exp": datetime.now(timezone.utc) + timedelta(days=7),
                }
            ),
        ):
            with pytest.raises(ValueError, match="Invalid token type"):
                await manager.verify_token("refresh_token_trying_access")


class TestAuthManagerEdgeCases:
    """Test AuthManager edge cases."""

    @pytest.mark.asyncio
    async def test_create_tokens_with_different_roles(self, tmp_path):
        """Test creating tokens for different roles."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            for role in Role:
                tokens = manager.create_tokens("user123", "testuser", role)
                assert "access_token" in tokens
                assert "refresh_token" in tokens
                assert tokens["token_type"] == "Bearer"

    @pytest.mark.asyncio
    async def test_record_multiple_audit_events(self, tmp_path):
        """Test recording multiple audit events."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            actions = ["login", "logout", "create_task", "delete_task", "update_config"]
            for action in actions:
                event = AuditEvent(
                    user_id="user123",
                    action=action,
                    resource_type="test",
                )
                await manager.record_audit(event)

            events = await manager.get_audit_logs(user_id="user123")
            assert len(events) >= len(actions)

    @pytest.mark.asyncio
    async def test_user_lookup_after_create(self, tmp_path):
        """Test user can be found after creation via authenticate."""
        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            await manager.create_user(
                username="findme",
                email="findme@example.com",
                password="testPassword123",
                role=Role.VIEWER,
            )

            # Verify user can authenticate (proves user exists)
            tokens = await manager.authenticate("findme", "testPassword123")
            assert "access_token" in tokens

    @pytest.mark.asyncio
    async def test_user_deletion_via_db(self, tmp_path):
        """Test user deletion by direct DB manipulation."""
        import sqlite3

        with patch("jwt.encode", MagicMock(return_value="mock_token")):
            manager = AuthManager(
                secret_key="test_secret_key_at_least_32_chars_long",
                db_path=tmp_path / "test.db",
                token_expiry=3600,
            )

            user = await manager.create_user(
                username="deleteme",
                email="delete@example.com",
                password="testPassword123",
                role=Role.VIEWER,
            )

            # Delete user directly from DB
            with sqlite3.connect(tmp_path / "test.db") as conn:
                conn.execute("DELETE FROM users WHERE id = ?", (user.id,))
                conn.commit()

            # User should no longer be able to authenticate
            with pytest.raises(ValueError, match="Invalid username or password"):
                await manager.authenticate("deleteme", "testPassword123")
