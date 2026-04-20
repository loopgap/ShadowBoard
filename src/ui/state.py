"""
ShadowBoard UI Global State and Locks
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import main as core

logger = logging.getLogger(__name__)


@dataclass
class QueueItem:
    """表示队列中的单个任务项"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    template_label: str = ""
    user_input: str = ""
    status: str = "等待中"  # 等待中 / 执行中 / 执行成功 / 执行失败
    result: str = ""
    added_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    task_id: str = ""  # Reference to TaskTracker task ID


TASK_QUEUE: List[QueueItem] = []
_QUEUE_LOCK: Optional[asyncio.Lock] = None
_LOGIN_LOCK: Optional[asyncio.Lock] = None


def get_queue_lock() -> asyncio.Lock:
    """Get the queue lock. Ensure it's initialized in an async loop."""
    global _QUEUE_LOCK
    if _QUEUE_LOCK is None:
        try:
            _QUEUE_LOCK = asyncio.Lock()
        except RuntimeError:
            return asyncio.Lock()
    return _QUEUE_LOCK


def get_login_lock() -> asyncio.Lock:
    """Get the login lock. Ensure it's initialized in an async loop."""
    global _LOGIN_LOCK
    if _LOGIN_LOCK is None:
        try:
            _LOGIN_LOCK = asyncio.Lock()
        except RuntimeError:
            return asyncio.Lock()
    return _LOGIN_LOCK


LOGIN_STATE: Dict[str, Any] = {"p": None, "context": None, "page": None}
LAST_INPUT: Dict[str, str] = {"template": "市场分析 (CMO)", "content": ""}

EXPORT_DIR = core.STATE_DIR / "exports"
DOCS_DIR = core.STATE_DIR / "docs"

PROVIDERS: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "label": "DeepSeek 网页",
        "url": "https://chat.deepseek.com/",
        "send_mode": "enter",
        "guide": "推荐新手首选 页面稳定 先登录后做冒烟测试",
    },
    "kimi": {
        "label": "Kimi 网页",
        "url": "https://kimi.moonshot.cn/",
        "send_mode": "enter",
        "guide": "适合长文处理 登录后先执行一次冒烟验证",
    },
    "tongyi": {
        "label": "通义千问 网页",
        "url": "https://tongyi.aliyun.com/qianwen/",
        "send_mode": "button",
        "guide": "建议使用点击按钮发送 遇到弹窗先手动关闭",
    },
}
PROVIDER_LABEL_TO_KEY: Dict[str, str] = {v["label"]: k for k, v in PROVIDERS.items()}

_DEFAULT_TEMPLATES = {
    "市场分析 (CMO)": {
        "key": "market_analyst",
        "guide": "从市场规模、竞争对手、用户痛点角度分析议案",
    },
    "技术评估 (CTO)": {
        "key": "tech_lead",
        "guide": "评估技术可行性、架构复杂度与核心栈",
    },
    "财务审计 (CFO)": {
        "key": "finance_expert",
        "guide": "进行成本收益分析，识别财务风险",
    },
    "风险管理 (Red Team)": {
        "key": "risk_manager",
        "guide": "从法律合规和逻辑漏洞角度做风险评估",
    },
    "董事长总结 (Chairman)": {
        "key": "chairman_summary",
        "guide": "汇总分歧与共识并给出最终建议",
    },
    "摘要总结": {
        "key": "summary",
        "guide": "适合长文快速提炼要点 默认输出结构化结论",
    },
    "自定义原样发送": {
        "key": "custom",
        "guide": "不会套模板 直接把输入内容发送给网页 AI",
    },
}

TEMPLATE_LABEL_TO_KEY: Dict[str, str] = {k: v["key"] for k, v in _DEFAULT_TEMPLATES.items()}
KEY_TO_TEMPLATE_LABEL: Dict[str, str] = {v["key"]: k for k, v in _DEFAULT_TEMPLATES.items()}
KEY_TO_TEMPLATE_LABEL["smoke"] = "冒烟测试"
TEMPLATE_GUIDE: Dict[str, str] = {k: v["guide"] for k, v in _DEFAULT_TEMPLATES.items()}

CUSTOM_CSS: str = ""


def load_metadata():
    """从外部 JSON 和 CSS 文件加载元数据，若不存在则保留默认硬编码值"""
    global PROVIDERS, PROVIDER_LABEL_TO_KEY, TEMPLATE_LABEL_TO_KEY, KEY_TO_TEMPLATE_LABEL, TEMPLATE_GUIDE, CUSTOM_CSS

    meta_path = core.STATE_DIR / "providers.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            ext_providers = meta.get("providers", {})
            if ext_providers:
                PROVIDERS.update(ext_providers)
                PROVIDER_LABEL_TO_KEY.update({v["label"]: k for k, v in ext_providers.items()})

            ext_templates = meta.get("templates", {})
            if ext_templates:
                TEMPLATE_LABEL_TO_KEY.update({k: v["key"] for k, v in ext_templates.items()})
                KEY_TO_TEMPLATE_LABEL.update({v["key"]: k for k, v in ext_templates.items()})
                TEMPLATE_GUIDE.update({k: v["guide"] for k, v in ext_templates.items()})
        except Exception as e:
            logger.warning(f"Error loading providers.json: {e}")

    css_path = core.STATE_DIR / "style.css"
    if css_path.exists():
        CUSTOM_CSS = css_path.read_text(encoding="utf-8")
    else:
        CUSTOM_CSS = ""


def ensure_dirs() -> None:
    core.ensure_state()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)


EXAMPLE_INPUTS: List[List[str]] = [
    [
        "摘要总结",
        "请总结下面会议纪要并输出三条结论和三条行动项\n本周完成接口联调\n下周开始灰度发布\n风险是测试资源不足",
    ],
    ["润色改写", "请把这段话改得专业但简洁 这个功能目前不够稳定 我们后续会持续优化"],
    [
        "信息抽取",
        "从以下文本提取日期 负责人 截止时间 王明二月二十八日前完成验收文档 李华三月一日提交测试报告",
    ],
    ["自定义原样发送", "你是一名项目助理 请把我的需求拆成可执行清单"],
]

HISTORY_FILTERS = ["全部", "仅成功", "仅失败"]
