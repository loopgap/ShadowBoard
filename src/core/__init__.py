"""
Core Module

Provides essential components for the Chorus-WebAI engine:
- Configuration management
- Browser automation
- Exception definitions
"""

from .config import ConfigManager, get_config, set_config
from .exceptions import (
    ChorusError,
    ConfigError,
    BrowserError,
    TaskError,
    WorkflowError,
    MemoryError,
)
from .browser import BrowserManager, BrowserSession

__all__ = [
    "ConfigManager",
    "get_config",
    "set_config",
    "ChorusError",
    "ConfigError",
    "BrowserError",
    "TaskError",
    "WorkflowError",
    "MemoryError",
    "BrowserManager",
    "BrowserSession",
]
