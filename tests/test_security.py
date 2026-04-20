"""
Tests for Security Module

Tests input validation, auth flows, and encryption operations.
"""

from __future__ import annotations

import pytest

from src.core.security import (
    InputValidator,
    ValidationError,
    ValidationContext,
    SecureInputBuilder,
    ValidationErrorCode,
    ValidationRule,
)


class TestInputValidator:
    """Test InputValidator class."""

    def test_validate_prompt_valid(self):
        """Test valid prompt passes validation."""
        valid, error = InputValidator.validate("Hello, world!", "prompt")
        assert valid is True
        assert error is None

    def test_validate_prompt_too_short(self):
        """Test empty prompt fails validation."""
        valid, error = InputValidator.validate("", "prompt")
        assert valid is False
        assert "required" in error.lower()

    def test_validate_prompt_forbidden_keyword(self):
        """Test prompt with forbidden keyword fails."""
        valid, error = InputValidator.validate("DROP TABLE users;", "prompt")
        assert valid is False
        assert "forbidden" in error.lower()

    def test_validate_template_key_valid(self):
        """Test valid template_key passes."""
        valid, error = InputValidator.validate("market_analyst", "template_key")
        assert valid is True
        assert error is None

    def test_validate_template_key_invalid_format(self):
        """Test invalid template_key format fails."""
        valid, error = InputValidator.validate("MarketAnalyst", "template_key")
        assert valid is False
        assert "pattern" in error.lower() or "format" in error.lower()

    def test_validate_template_key_uppercase_fails(self):
        """Test uppercase template_key fails pattern."""
        valid, error = InputValidator.validate("MARKET_ANALYST", "template_key")
        assert valid is False

    def test_validate_url_valid(self):
        """Test valid URL passes."""
        valid, error = InputValidator.validate("https://example.com/path", "url")
        assert valid is True
        assert error is None

    def test_validate_url_invalid(self):
        """Test invalid URL fails."""
        valid, error = InputValidator.validate("not-a-url", "url")
        assert valid is False

    def test_validate_email_valid(self):
        """Test valid email passes."""
        valid, error = InputValidator.validate("user@example.com", "email")
        assert valid is True
        assert error is None

    def test_validate_email_invalid(self):
        """Test invalid email fails."""
        valid, error = InputValidator.validate("not-an-email", "email")
        assert valid is False

    def test_validate_username_valid(self):
        """Test valid username passes."""
        valid, error = InputValidator.validate("user_name-123", "username")
        assert valid is True
        assert error is None

    def test_validate_username_too_short(self):
        """Test username too short fails."""
        valid, error = InputValidator.validate("ab", "username")
        assert valid is False
        assert "short" in error.lower()

    def test_validate_username_too_long(self):
        """Test username too long fails."""
        valid, error = InputValidator.validate("a" * 50, "username")
        assert valid is False
        assert "long" in error.lower()

    def test_validate_password_valid(self):
        """Test valid password passes."""
        valid, error = InputValidator.validate("securePassword123!", "password")
        assert valid is True
        assert error is None

    def test_validate_password_too_short(self):
        """Test password too short fails."""
        valid, error = InputValidator.validate("short", "password")
        assert valid is False
        assert "short" in error.lower()

    def test_validate_task_id_valid(self):
        """Test valid task_id passes."""
        valid, error = InputValidator.validate("a1b2c3d4", "task_id")
        assert valid is True
        assert error is None

    def test_validate_task_id_invalid(self):
        """Test invalid task_id fails."""
        valid, error = InputValidator.validate("invalid", "task_id")
        assert valid is False

    def test_validate_unknown_rule_raises(self):
        """Test unknown validation rule raises ValueError."""
        with pytest.raises(ValueError, match="Unknown validation rule"):
            InputValidator.validate("value", "unknown_rule")

    def test_validate_dict_valid(self):
        """Test valid dict passes validation."""
        data = {
            "template_key": "market_analyst",
            "user_input": "Hello",
        }
        schema = {
            "template_key": "template_key",
            "user_input": "prompt",
        }
        valid, error, field = InputValidator.validate_dict(data, schema)
        assert valid is True
        assert error is None
        assert field is None

    def test_validate_dict_invalid_field(self):
        """Test invalid field in dict returns field name."""
        data = {
            "template_key": "InvalidKey",
        }
        schema = {
            "template_key": "template_key",
        }
        valid, error, field = InputValidator.validate_dict(data, schema)
        assert valid is False
        assert field == "template_key"

    def test_validate_none_required_field(self):
        """Test None value for required field fails."""
        valid, error = InputValidator.validate(None, "prompt")
        assert valid is False


class TestValidationRule:
    """Test ValidationRule dataclass."""

    def test_validation_rule_defaults(self):
        """Test ValidationRule default values."""
        rule = ValidationRule()
        assert rule.required is True
        assert rule.type_check is None
        assert rule.min_length is None
        assert rule.max_length is None

    def test_validation_rule_with_constraints(self):
        """Test ValidationRule with length constraints."""
        rule = ValidationRule(
            required=True,
            type_check=str,
            min_length=5,
            max_length=10,
        )
        assert rule.min_length == 5
        assert rule.max_length == 10

    def test_validation_rule_compiled_pattern(self):
        """Test ValidationRule pattern compilation."""
        rule = ValidationRule(pattern=r"^[a-z]+$")
        compiled = rule.get_compiled_pattern()
        assert compiled is not None
        assert compiled.match("hello") is not None
        assert compiled.match("HELLO") is None


class TestValidationError:
    """Test ValidationError exception."""

    def test_validation_error_creation(self):
        """Test ValidationError creation with all fields."""
        error = ValidationError(
            message="Test error",
            error_code=ValidationErrorCode.FORBIDDEN_KEYWORD,
            field_name="test_field",
            value="bad_value",
        )
        assert error.message == "Test error"
        assert error.error_code == ValidationErrorCode.FORBIDDEN_KEYWORD
        assert error.field_name == "test_field"
        assert error.value == "bad_value"

    def test_validation_error_to_dict(self):
        """Test ValidationError to_dict conversion."""
        error = ValidationError(
            message="Test error",
            error_code=ValidationErrorCode.TYPE_MISMATCH,
            field_name="field1",
        )
        result = error.to_dict()
        assert result["error"] == "TYPE_MISMATCH"
        assert result["message"] == "Test error"
        assert result["field"] == "field1"


class TestSecureInputBuilder:
    """Test SecureInputBuilder class."""

    def test_build_safe_prompt_custom_template(self):
        """Test building prompt with custom template."""
        result = SecureInputBuilder.build_safe_prompt(
            template_key="custom",
            user_input="Hello, world!",
        )
        assert result == "Hello, world!"

    def test_build_safe_prompt_sanitizes_input(self):
        """Test that input is sanitized."""
        result = SecureInputBuilder.build_safe_prompt(
            template_key="custom",
            user_input="  Hello    world!  \n\n",
        )
        assert "Hello" in result
        assert result == result.strip()

    def test_build_safe_prompt_invalid_template_key(self):
        """Test invalid template_key raises ValidationError."""
        with pytest.raises(ValidationError):
            SecureInputBuilder.build_safe_prompt(
                template_key="INVALID",
                user_input="Hello",
            )

    def test_build_safe_prompt_empty_input(self):
        """Test empty input raises ValidationError."""
        with pytest.raises(ValidationError):
            SecureInputBuilder.build_safe_prompt(
                template_key="custom",
                user_input="",
            )

    def test_build_safe_prompt_with_templates(self):
        """Test building prompt with template substitution."""
        templates = {"greeting": "Hello, {user_input}! Welcome."}
        result = SecureInputBuilder.build_safe_prompt(
            template_key="greeting",
            user_input="Alice",
            templates=templates,
        )
        assert result == "Hello, Alice! Welcome."

    def test_build_safe_prompt_injects_sanitized_input(self):
        """Test that user input is properly sanitized in template."""
        templates = {"greeting": "Hello, {user_input}!"}
        # Control characters and extra whitespace should be sanitized
        result = SecureInputBuilder.build_safe_prompt(
            template_key="greeting",
            user_input="<img src=x onerror=alert('xss')>\n\nHello    World",
            templates=templates,
        )
        # Newlines collapsed to single space, but HTML not escaped by this method
        assert "\n" not in result
        assert "  " not in result  # Multiple spaces collapsed


class TestInputValidatorSanitization:
    """Test InputValidator sanitization methods."""

    def test_sanitize_string_remove_control_chars(self):
        """Test control character removal."""
        result = InputValidator.sanitize_string("Hello\x00World")
        assert "\x00" not in result
        assert "Hello" in result
        assert "World" in result

    def test_sanitize_string_collapse_whitespace(self):
        """Test whitespace collapsing."""
        result = InputValidator.sanitize_string("Hello    World\n\nTest")
        assert "  " not in result
        assert "\n" not in result

    def test_sanitize_string_max_chars(self):
        """Test max character truncation."""
        result = InputValidator.sanitize_string("A" * 100, max_chars=10)
        assert len(result) == 10

    def test_sanitize_string_empty(self):
        """Test sanitizing empty string."""
        result = InputValidator.sanitize_string("")
        assert result == ""

    def test_sanitize_string_none(self):
        """Test sanitizing None."""
        result = InputValidator.sanitize_string(None)
        assert result is None

    def test_escape_html(self):
        """Test HTML escaping."""
        result = InputValidator.escape_html("<script>alert('xss')</script>")
        assert "<" not in result
        assert ">" not in result
        assert "&lt;" in result

    def test_escape_html_empty(self):
        """Test escaping empty string."""
        result = InputValidator.escape_html("")
        assert result == ""

    def test_escape_sql(self):
        """Test SQL escaping."""
        result = InputValidator.escape_sql("O'Reilly")
        assert "'" in result  # Should be escaped
        assert result == "O''Reilly"


class TestValidationContext:
    """Test ValidationContext dataclass."""

    def test_validation_context_add_error(self):
        """Test adding error to context."""
        ctx = ValidationContext()
        ctx.add_error("field1", "Error message")
        assert "field1" in ctx.field_errors
        assert ctx.field_errors["field1"] == "Error message"

    def test_validation_context_add_warning(self):
        """Test adding warning to context."""
        ctx = ValidationContext()
        ctx.add_warning("Warning message")
        assert "Warning message" in ctx.warnings

    def test_validation_context_is_valid(self):
        """Test is_valid when no errors."""
        ctx = ValidationContext()
        assert ctx.is_valid() is True

    def test_validation_context_is_invalid(self):
        """Test is_valid when has errors."""
        ctx = ValidationContext()
        ctx.add_error("field1", "Error")
        assert ctx.is_valid() is False

    def test_validation_context_to_dict(self):
        """Test to_dict conversion."""
        ctx = ValidationContext()
        ctx.add_error("field1", "Error")
        ctx.add_warning("Warning")
        result = ctx.to_dict()
        assert result["valid"] is False
        assert "field1" in result["errors"]
        assert "Warning" in result["warnings"]
