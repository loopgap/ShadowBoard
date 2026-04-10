"""
Custom Exception Hierarchy

Defines a structured exception hierarchy for consistent error handling
across the Chorus-WebAI application.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class ChorusError(Exception):
    """
    Base exception for all Chorus-WebAI errors.

    Provides structured error information with error codes,
    context data, and optional cause chaining.
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "CHORUS_000"
        self.context = context or {}
        self.cause = cause

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "context": self.context,
            "cause": str(self.cause) if self.cause else None,
        }

    def __str__(self) -> str:
        parts = [f"[{self.error_code}] {self.message}"]
        if self.context:
            parts.append(f"Context: {self.context}")
        if self.cause:
            parts.append(f"Caused by: {self.cause}")
        return " | ".join(parts)


class ConfigError(ChorusError):
    """Configuration-related errors."""

    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if config_key:
            context["config_key"] = config_key
        super().__init__(
            message,
            error_code="CONFIG_ERROR",
            context=context,
            **kwargs,
        )


class BrowserError(ChorusError):
    """Browser automation errors."""

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        selector: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if url:
            context["url"] = url
        if selector:
            context["selector"] = selector
        super().__init__(
            message,
            error_code="BROWSER_ERROR",
            context=context,
            **kwargs,
        )


class TaskError(ChorusError):
    """Task execution errors."""

    def __init__(
        self,
        message: str,
        task_id: Optional[str] = None,
        task_status: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if task_id:
            context["task_id"] = task_id
        if task_status:
            context["task_status"] = task_status
        super().__init__(
            message,
            error_code="TASK_ERROR",
            context=context,
            **kwargs,
        )


class WorkflowError(ChorusError):
    """Workflow orchestration errors."""

    def __init__(
        self,
        message: str,
        workflow_id: Optional[str] = None,
        step: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if workflow_id:
            context["workflow_id"] = workflow_id
        if step:
            context["step"] = step
        super().__init__(
            message,
            error_code="WORKFLOW_ERROR",
            context=context,
            **kwargs,
        )


class MemoryError(ChorusError):
    """Memory storage errors."""

    def __init__(
        self,
        message: str,
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", {})
        if session_id:
            context["session_id"] = session_id
        super().__init__(
            message,
            error_code="MEMORY_ERROR",
            context=context,
            **kwargs,
        )
