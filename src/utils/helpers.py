"""
Helper Utilities

Common utility functions used across the application.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

# Template definitions
TEMPLATES: Dict[str, str] = {
    "summary": "Summarize the following content in 5 bullets:\n\n{user_input}",
    "translation": "Translate the following text to Chinese and keep meaning precise:\n\n{user_input}",
    "rewrite": "Rewrite the following text to be clear and professional:\n\n{user_input}",
    "extract": "Extract key entities, dates, and action items from the following:\n\n{user_input}",
    "qa": "Answer the request below with concise steps:\n\n{user_input}",
}


def build_prompt(template_key: str, user_input: str) -> str:
    """
    Build a prompt from a template.

    Args:
        template_key: Template identifier or "custom"
        user_input: User's input text

    Returns:
        Formatted prompt string
    """
    if template_key == "custom":
        return user_input

    template = TEMPLATES.get(template_key, "{user_input}")
    return template.format(user_input=user_input)


def shorten_text(
    text: str,
    max_length: int = 100,
    placeholder: str = "...",
) -> str:
    """
    Shorten text to maximum length.

    Args:
        text: Input text
        max_length: Maximum length including placeholder
        placeholder: Suffix for truncated text

    Returns:
        Shortened text
    """
    if len(text) <= max_length:
        return text

    # Account for placeholder length
    truncate_at = max_length - len(placeholder)
    if truncate_at <= 0:
        return placeholder[:max_length]

    return text[:truncate_at] + placeholder


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable form.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string (e.g., "2m 30s")
    """
    if seconds < 60:
        return f"{seconds:.1f}s"

    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60

    if minutes < 60:
        return f"{minutes}m {remaining_seconds:.0f}s"

    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m"


def get_timestamp(format: str = "iso") -> str:
    """
    Get current timestamp in specified format.

    Args:
        format: Output format ("iso", "file", "display")

    Returns:
        Formatted timestamp string
    """
    now = datetime.now()

    if format == "iso":
        return now.isoformat(timespec="seconds")
    elif format == "file":
        return now.strftime("%Y%m%d_%H%M%S")
    elif format == "display":
        return now.strftime("%Y-%m-%d %H:%M:%S")
    else:
        return now.isoformat()


def parse_bool(value: Any, default: bool = False) -> bool:
    """
    Parse a value as boolean.

    Args:
        value: Input value (string, bool, int, etc.)
        default: Default if cannot parse

    Returns:
        Boolean value
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower_value = value.lower()
        if lower_value in ("true", "yes", "1", "on"):
            return True
        if lower_value in ("false", "no", "0", "off"):
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def safe_get(
    data: Dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    """
    Safely get nested dictionary value.

    Args:
        data: Dictionary to search
        *keys: Nested keys
        default: Default value if not found

    Returns:
        Value or default
    """
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current
