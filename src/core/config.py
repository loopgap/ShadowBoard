"""
Configuration Management Module

Provides centralized configuration management with:
- Type-safe configuration access
- Environment variable support
- Configuration validation
- Hot-reload capability
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from .exceptions import ConfigError

logger = logging.getLogger(__name__)


# Default configuration values
DEFAULT_CONFIG: Dict[str, Any] = {
    "target_url": "https://chat.deepseek.com/",
    "browser_channel": "msedge",
    "send_mode": "enter",
    "confirm_before_send": True,
    "max_retries": 3,
    "backoff_seconds": 1.5,
    "input_selectors": [
        "textarea",
        "[contenteditable='true']",
        "textarea[placeholder*='message' i]",
        "textarea[placeholder*='chat' i]",
    ],
    "assistant_selectors": [
        "[data-role='assistant']",
        ".assistant",
        ".markdown",
        "article",
    ],
    "send_button_selectors": [
        "button[type='submit']",
        "button[aria-label*='send' i]",
    ],
    "navigation_timeout_seconds": 30,
    "response_timeout_seconds": 120,
    "stable_response_seconds": 3,
    "smoke_pause_seconds": 3,
}


@dataclass
class ProviderConfig:
    """Configuration for an AI provider."""
    key: str
    label: str
    url: str
    send_mode: str = "enter"
    guide: str = ""


# Predefined providers
DEFAULT_PROVIDERS: Dict[str, ProviderConfig] = {
    "deepseek": ProviderConfig(
        key="deepseek",
        label="DeepSeek",
        url="https://chat.deepseek.com/",
        send_mode="enter",
        guide="建议开启'回车发送'。如果遇到验证码，请手动完成。",
    ),
    "kimi": ProviderConfig(
        key="kimi",
        label="Kimi (Moonshot)",
        url="https://kimi.moonshot.cn/",
        send_mode="enter",
        guide="Kimi 网页版响应较快，适合长文本分析。",
    ),
    "tongyi": ProviderConfig(
        key="tongyi",
        label="通义千问 (Qwen)",
        url="https://tongyi.aliyun.com/",
        send_mode="button",
        guide="通义建议使用'点击按钮'模式进行交互。",
    ),
}


class ConfigManager:
    """
    Centralized configuration manager.

    Features:
    - Lazy loading and caching
    - Environment variable overrides
    - Configuration validation
    - Change notifications
    """

    _instance: Optional["ConfigManager"] = None
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> "ConfigManager":
        """Singleton pattern for global config access."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        config_path: Optional[Path] = None,
        state_dir: Optional[Path] = None,
    ) -> None:
        if self._initialized:
            return

        self._state_dir = state_dir or Path(__file__).resolve().parent.parent.parent / ".semi_agent"
        self._config_path = config_path or self._state_dir / "config.json"
        self._providers: Dict[str, ProviderConfig] = DEFAULT_PROVIDERS.copy()
        self._config: Dict[str, Any] = {}
        self._listeners: List[Callable[[str, Any], None]] = []

        self._ensure_state_dir()
        self._config = self._load_config()
        self._initialized = True

    def _ensure_state_dir(self) -> None:
        """Ensure state directory exists."""
        self._state_dir.mkdir(parents=True, exist_ok=True)
        (self._state_dir / "errors").mkdir(parents=True, exist_ok=True)
        (self._state_dir / "browser_profile").mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file with fallback to defaults."""
        if not self._config_path.exists():
            self._save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()

        try:
            content = self._config_path.read_text(encoding="utf-8")
            if not content.strip():
                return DEFAULT_CONFIG.copy()

            data = json.loads(content)
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)

            # Validate URL
            url = str(merged.get("target_url", "")).strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                merged["target_url"] = DEFAULT_CONFIG["target_url"]

            return merged
        except json.JSONDecodeError as e:
            logger.error(f"Configuration file is corrupted: {e} at {self._config_path}")
            raise ConfigError(
                f"Configuration file is corrupted: {e}",
                context={"file": str(self._config_path)},
            )
        except Exception as e:
            logger.error(f"Failed to load configuration from {self._config_path}: {e}")
            raise ConfigError(
                f"Failed to load configuration: {e}",
                cause=e,
            )

    def _save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file."""
        self._config_path.write_text(
            json.dumps(config, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    @property
    def state_dir(self) -> Path:
        """Get state directory path."""
        return self._state_dir

    @property
    def profile_dir(self) -> Path:
        """Get browser profile directory path."""
        return self._state_dir / "browser_profile"

    @property
    def error_dir(self) -> Path:
        """Get error log directory path."""
        return self._state_dir / "errors"

    @property
    def history_path(self) -> Path:
        """Get history file path."""
        return self._state_dir / "history.jsonl"

    @property
    def config_path(self) -> Path:
        """Get configuration file path."""
        return self._config_path

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with environment variable override.

        Environment variables take precedence over file configuration.
        Format: SHADOW_<UPPERCASE_KEY>
        """
        # Check environment variable first
        env_key = f"SHADOW_{key.upper()}"
        env_value = os.environ.get(env_key)
        if env_value is not None:
            # Type conversion based on default type
            default_value = DEFAULT_CONFIG.get(key)
            if isinstance(default_value, bool):
                return env_value.lower() in ("true", "1", "yes")
            elif isinstance(default_value, int):
                return int(env_value)
            elif isinstance(default_value, float):
                return float(env_value)
            return env_value

        return self._config.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        """Set configuration value and optionally persist."""
        self._config[key] = value

        if save:
            self._save_config(self._config)

        # Notify listeners
        for listener in self._listeners:
            listener(key, value)

    def update(self, updates: Dict[str, Any], save: bool = True) -> None:
        """Update multiple configuration values."""
        for key, value in updates.items():
            self.set(key, value, save=False)

        if save:
            self._save_config(self._config)

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values."""
        return self._config.copy()

    def get_provider(self, key: str) -> Optional[ProviderConfig]:
        """Get provider configuration by key."""
        return self._providers.get(key)

    def get_all_providers(self) -> Dict[str, ProviderConfig]:
        """Get all provider configurations."""
        return self._providers.copy()

    def add_provider(self, provider: ProviderConfig) -> None:
        """Add or update a provider configuration."""
        self._providers[provider.key] = provider

    def add_change_listener(
        self,
        listener: Callable[[str, Any], None],
    ) -> None:
        """Add a listener for configuration changes."""
        self._listeners.append(listener)

    def reload(self) -> None:
        """Reload configuration from file."""
        self._config = self._load_config()


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager(
    config_path: Optional[Path] = None,
    state_dir: Optional[Path] = None,
) -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path, state_dir)
    return _config_manager


def get_config(key: str, default: Any = None) -> Any:
    """Convenience function to get configuration value."""
    return get_config_manager().get(key, default)


def set_config(key: str, value: Any, save: bool = True) -> None:
    """Convenience function to set configuration value."""
    get_config_manager().set(key, value, save)
