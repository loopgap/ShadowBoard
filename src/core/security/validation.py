"""
Input Validation Framework - 企业级输入验证

提供全面的输入验证与sanitization:
- 模式验证
- 长度检查
- 字符集限制
- 注入防护
- 自定义验证规则
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Pattern, Tuple


class ValidationErrorCode(Enum):
    """验证错误码"""
    MISSING_REQUIRED = "MISSING_REQUIRED"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    TOO_SHORT = "TOO_SHORT"
    TOO_LONG = "TOO_LONG"
    PATTERN_MISMATCH = "PATTERN_MISMATCH"
    INVALID_CHARACTERS = "INVALID_CHARACTERS"
    FORBIDDEN_KEYWORD = "FORBIDDEN_KEYWORD"
    CUSTOM_VALIDATION_FAILED = "CUSTOM_VALIDATION_FAILED"


class ValidationError(Exception):
    """验证异常"""
    
    def __init__(
        self,
        message: str,
        error_code: ValidationErrorCode = None,
        field_name: str = None,
        value: Any = None,
    ):
        self.message = message
        self.error_code = error_code or ValidationErrorCode.CUSTOM_VALIDATION_FAILED
        self.field_name = field_name
        self.value = value
        super().__init__(message)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'error': self.error_code.value,
            'message': self.message,
            'field': self.field_name,
        }


@dataclass
class ValidationRule:
    """验证规则"""
    
    # 基本约束
    required: bool = True
    type_check: type = None
    
    # 长度约束
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    
    # 内容约束
    pattern: Optional[str] = None  # 正则表达式
    allowed_chars: Optional[str] = None  # 允许的字符集
    forbidden_keywords: list = field(default_factory=list)
    
    # 自定义验证
    custom_validator: Optional[Callable[[Any], Tuple[bool, str]]] = None
    
    # 编译的正则（缓存优化）
    _compiled_pattern: Optional[Pattern] = None
    
    def get_compiled_pattern(self) -> Optional[Pattern]:
        """获取编译的正则表达式"""
        if self.pattern and not self._compiled_pattern:
            self._compiled_pattern = re.compile(self.pattern)
        return self._compiled_pattern


class InputValidator:
    """企业级输入验证器"""
    
    # 预定义规则库
    RULES = {
        'prompt': ValidationRule(
            required=True,
            type_check=str,
            min_length=1,
            max_length=100000,  # 100KB
            forbidden_keywords=['DROP', 'DELETE', 'EXEC', 'SCRIPT', '<!--', '-->'],
        ),
        'template_key': ValidationRule(
            required=True,
            type_check=str,
            pattern=r'^[a-z_]+$',
            min_length=1,
            max_length=50,
        ),
        'url': ValidationRule(
            required=True,
            type_check=str,
            pattern=r'^https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=]+$',
            min_length=10,
            max_length=2048,
        ),
        'email': ValidationRule(
            required=True,
            type_check=str,
            pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
            min_length=5,
            max_length=255,
        ),
        'username': ValidationRule(
            required=True,
            type_check=str,
            pattern=r'^[a-zA-Z0-9_-]{3,32}$',
            min_length=3,
            max_length=32,
        ),
        'password': ValidationRule(
            required=True,
            type_check=str,
            min_length=8,
            max_length=128,
        ),
        'task_id': ValidationRule(
            required=True,
            type_check=str,
            pattern=r'^[a-f0-9]{8}$',
        ),
        'workflow_json': ValidationRule(
            required=True,
            type_check=dict,
            custom_validator=None,  # 由业务逻辑处理
        ),
    }
    
    @classmethod
    def validate(
        cls,
        value: Any,
        rule_name: str,
        field_name: str = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        验证单个值
        
        Returns:
            (是否有效, 错误消息)
        """
        rule = cls.RULES.get(rule_name)
        if not rule:
            raise ValueError(f"Unknown validation rule: {rule_name}")
        
        return cls._validate_with_rule(value, rule, field_name or rule_name)
    
    @classmethod
    def validate_dict(
        cls,
        data: dict,
        schema: dict,  # {'field_name': 'rule_name', ...}
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        验证字典
        
        Returns:
            (是否有效, 错误消息, 失败的字段)
        """
        for field_name, rule_name in schema.items():
            value = data.get(field_name)
            valid, error_msg = cls.validate(value, rule_name, field_name)
            
            if not valid:
                return False, error_msg, field_name
        
        return True, None, None
    
    @classmethod
    def _validate_with_rule(
        cls,
        value: Any,
        rule: ValidationRule,
        field_name: str = None,
    ) -> Tuple[bool, Optional[str]]:
        """使用规则验证值"""
        
        # 1. 必填检查
        if value is None or value == "":
            if rule.required:
                return False, f"Field '{field_name}' is required"
            else:
                return True, None
        
        # 2. 类型检查
        if rule.type_check and not isinstance(value, rule.type_check):
            return False, (
                f"Field '{field_name}': expected {rule.type_check.__name__}, "
                f"got {type(value).__name__}"
            )
        
        # 仅对字符串继续检查
        if not isinstance(value, str):
            return True, None
        
        # 3. 长度检查
        if rule.min_length is not None and len(value) < rule.min_length:
            return False, (
                f"Field '{field_name}': too short "
                f"(min {rule.min_length}, got {len(value)})"
            )
        
        if rule.max_length is not None and len(value) > rule.max_length:
            return False, (
                f"Field '{field_name}': too long "
                f"(max {rule.max_length}, got {len(value)})"
            )
        
        # 4. 模式检查
        if rule.pattern:
            compiled = rule.get_compiled_pattern()
            if not compiled.match(value):
                return False, (
                    f"Field '{field_name}': invalid format "
                    f"(pattern: {rule.pattern})"
                )
        
        # 5. 字符集检查
        if rule.allowed_chars:
            invalid = set(value) - set(rule.allowed_chars)
            if invalid:
                return False, (
                    f"Field '{field_name}': invalid characters "
                    f"({', '.join(invalid)})"
                )
        
        # 6. 禁用关键词检查
        if rule.forbidden_keywords:
            upper_value = value.upper()
            for keyword in rule.forbidden_keywords:
                if keyword.upper() in upper_value:
                    return False, (
                        f"Field '{field_name}': contains forbidden keyword "
                        f"'{keyword}'"
                    )
        
        # 7. 自定义验证
        if rule.custom_validator:
            try:
                valid, error = rule.custom_validator(value)
                if not valid:
                    return False, f"Field '{field_name}': {error}"
            except Exception as e:
                return False, f"Field '{field_name}': validation error: {e}"
        
        return True, None
    
    @staticmethod
    def sanitize_string(
        value: str,
        remove_control_chars: bool = True,
        collapse_whitespace: bool = True,
        max_chars: Optional[int] = None,
    ) -> str:
        """清理字符串"""
        
        if not value:
            return value
        
        # 移除控制字符
        if remove_control_chars:
            value = ''.join(
                c for c in value 
                if ord(c) >= 32 or c in '\n\t\r'
            )
        
        # 折叠空白
        if collapse_whitespace:
            value = re.sub(r'\s+', ' ', value)
        
        # 截断
        if max_chars and len(value) > max_chars:
            value = value[:max_chars]
        
        return value.strip()
    
    @staticmethod
    def escape_html(value: str) -> str:
        """HTML 转义"""
        if not value:
            return value
        
        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }
        
        for char, escaped in replacements.items():
            value = value.replace(char, escaped)
        
        return value
    
    @staticmethod
    def escape_sql(value: str) -> str:
        """SQL 转义（备用，应使用参数化查询）"""
        if not value:
            return value
        
        # 双引号单引号
        return value.replace("'", "''").replace('"', '""')


class SecureInputBuilder:
    """安全输入构建器"""
    
    @staticmethod
    def build_safe_prompt(
        template_key: str,
        user_input: str,
        templates: dict = None,
    ) -> str:
        """构建安全的 prompt"""
        
        # 1. 验证输入
        valid, error = InputValidator.validate(template_key, 'template_key')
        if not valid:
            raise ValidationError(error, field_name='template_key')
        
        valid, error = InputValidator.validate(user_input, 'prompt')
        if not valid:
            raise ValidationError(error, field_name='user_input')
        
        # 2. 清理用户输入
        cleaned_input = InputValidator.sanitize_string(user_input)
        
        # 3. 防止模板注入
        if template_key == "custom":
            # 自定义模板直接使用清理过的输入
            return cleaned_input
        
        # 4. 从模板库获取
        templates = templates or {}
        template = templates.get(template_key, "{user_input}")
        
        # 5. 安全格式化（防止格式字符串攻击）
        try:
            prompt = template.format(user_input=cleaned_input)
        except (KeyError, IndexError, ValueError) as e:
            raise ValidationError(
                f"Template formatting error: {e}",
                field_name='template'
            )
        
        return prompt


@dataclass
class ValidationContext:
    """验证上下文（用于请求级验证）"""
    field_errors: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    
    def add_error(self, field: str, message: str):
        """添加字段错误"""
        self.field_errors[field] = message
    
    def add_warning(self, message: str):
        """添加警告"""
        self.warnings.append(message)
    
    def is_valid(self) -> bool:
        """检查是否有效"""
        return len(self.field_errors) == 0
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'valid': self.is_valid(),
            'errors': self.field_errors,
            'warnings': self.warnings,
        }
