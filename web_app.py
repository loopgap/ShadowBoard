"""
网页 AI 半自动助手 - Gradio 图形界面模块 (Web UI Layer)

本模块构建了一个基于 Gradio 的交互式 Web 界面，提供以下功能:
1. 平台预设管理与参数配置
2. 引导式登录与冒烟测试流程
3. 单次任务执行与结果实时预览
4. 批量任务队列 (Task Queue) 系统
5. 历史记录审计、健康检查与接口文档导出
6. 任务追踪与记忆存储
7. 工作流编排
"""

from __future__ import annotations

import asyncio
import copy
import json
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

if TYPE_CHECKING:
    import gradio as gr

import main as core

# Import new services
from src.services.task_tracker import TaskTracker
from src.services.memory_store import MemoryStore, SessionManager
from src.services.workflow import WorkflowEngine
from src.services.monitor import Monitor


# --- Task Queue System (批量任务队列系统) ---
from dataclasses import dataclass, field
import uuid

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
_QUEUE_LOCK = None

# --- New Service Instances ---
_task_tracker: TaskTracker = None
_memory_store: MemoryStore = None
_session_manager: SessionManager = None
_workflow_engine: WorkflowEngine = None
_monitor: Monitor = None

def _get_task_tracker() -> TaskTracker:
    """Get or create TaskTracker instance."""
    global _task_tracker
    if _task_tracker is None:
        _task_tracker = TaskTracker()
    return _task_tracker

def _get_memory_store() -> MemoryStore:
    """Get or create MemoryStore instance."""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store

def _get_session_manager() -> SessionManager:
    """Get or create SessionManager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(_get_memory_store())
    return _session_manager

def _get_workflow_engine() -> WorkflowEngine:
    """Get or create WorkflowEngine instance."""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
        # Register predefined workflows
        from src.services.workflow import create_summary_workflow, create_translation_workflow
        _workflow_engine.register_workflow(create_summary_workflow())
        _workflow_engine.register_workflow(create_translation_workflow())
    return _workflow_engine

def _get_monitor() -> Monitor:
    """Get or create Monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = Monitor()
    return _monitor

def get_queue_lock():
    """获取队列操作的异步锁，确保线程/并发安全"""
    global _QUEUE_LOCK
    if _QUEUE_LOCK is None:
        _QUEUE_LOCK = asyncio.Lock()
    return _QUEUE_LOCK
# ------------------------------------------

_LOGIN_LOCK = None
def get_login_lock():
    """获取浏览器登录会话的锁，防止同时打开多个登录窗口"""
    global _LOGIN_LOCK
    if _LOGIN_LOCK is None:
        _LOGIN_LOCK = asyncio.Lock()
    return _LOGIN_LOCK
LOGIN_STATE: Dict[str, Any] = {"p": None, "context": None, "page": None}
LAST_INPUT: Dict[str, str] = {"template": "摘要总结", "content": ""}

EXPORT_DIR = core.STATE_DIR / "exports"
DOCS_DIR = core.STATE_DIR / "docs"

PROVIDERS: Dict[str, Dict[str, str]] = {
    "deepseek": {"label": "DeepSeek", "url": "https://chat.deepseek.com/", "send_mode": "enter", "guide": "建议开启‘回车发送’。如果遇到验证码，请手动完成。"},
    "kimi": {"label": "Kimi (Moonshot)", "url": "https://kimi.moonshot.cn/", "send_mode": "enter", "guide": "Kimi 网页版响应较快，适合长文本分析。"},
    "tongyi": {"label": "通义千问 (Qwen)", "url": "https://tongyi.aliyun.com/", "send_mode": "button", "guide": "通义建议使用‘点击按钮’模式进行交互。"},
}
PROVIDER_LABEL_TO_KEY: Dict[str, str] = {v["label"]: k for k, v in PROVIDERS.items()}

_DEFAULT_TEMPLATES = {
    "摘要总结": {"key": "summary", "guide": "输入一段长文章，模型将提取核心要点并列举行动项。"},
    "润色改写": {"key": "rewrite", "guide": "将草稿改写为专业、流畅的文档。"},
    "信息抽取": {"key": "extract", "guide": "从文本中提取日期、人物、金额等关键结构化数据。"},
    "自定义原样发送": {"key": "custom", "guide": "跳过模板，直接将输入内容发送给 AI 模型。"},
}

TEMPLATE_LABEL_TO_KEY: Dict[str, str] = {k: v["key"] for k, v in _DEFAULT_TEMPLATES.items()}
KEY_TO_TEMPLATE_LABEL: Dict[str, str] = {v["key"]: k for k, v in _DEFAULT_TEMPLATES.items()}
KEY_TO_TEMPLATE_LABEL["smoke"] = "冒烟测试"
TEMPLATE_GUIDE: Dict[str, str] = {k: v["guide"] for k, v in _DEFAULT_TEMPLATES.items()}

CUSTOM_CSS: str = ""

def _load_metadata():
    """从外部 JSON 和 CSS 文件加载元数据，若不存在则保留默认硬编码值"""
    global PROVIDERS, PROVIDER_LABEL_TO_KEY, TEMPLATE_LABEL_TO_KEY, KEY_TO_TEMPLATE_LABEL, TEMPLATE_GUIDE, CUSTOM_CSS
    
    # 加载 Providers 和 Templates
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
            print(f"Error loading providers.json: {e}")

    # 加载 CSS
    css_path = core.STATE_DIR / "style.css"
    if css_path.exists():
        CUSTOM_CSS = css_path.read_text(encoding="utf-8")
    else:
        CUSTOM_CSS = ""

_load_metadata()

EXAMPLE_INPUTS: List[List[str]] = [
    ["摘要总结", "请总结下面会议纪要并输出三条结论和三条行动项\n本周完成接口联调\n下周开始灰度发布\n风险是测试资源不足"],
    ["润色改写", "请把这段话改得专业但简洁 这个功能目前不够稳定 我们后续会持续优化"],
    ["信息抽取", "从以下文本提取日期 负责人 截止时间 王明二月二十八日前完成验收文档 李华三月一日提交测试报告"],
    ["自定义原样发送", "你是一名项目助理 请把我的需求拆成可执行清单"],
]

HISTORY_FILTERS = ["全部", "仅成功", "仅失败"]


def _ensure_dirs() -> None:
    core.ensure_state()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)


def _provider_label_from_config(cfg: Dict[str, Any]) -> str:
    key = str(cfg.get("provider_key", "deepseek")).strip()
    if key in PROVIDERS:
        return PROVIDERS[key]["label"]
    return PROVIDERS["deepseek"]["label"]


def _provider_guide_text(provider_label: str) -> str:
    key = PROVIDER_LABEL_TO_KEY.get(provider_label, "deepseek")
    item = PROVIDERS[key]
    return "\n".join(
        [
            f"平台 {item['label']}",
            f"推荐网址 {item['url']}",
            f"推荐发送方式 {'回车发送' if item['send_mode'] == 'enter' else '点击按钮发送'}",
            f"操作建议 {item['guide']}",
        ]
    )


def _build_api_doc_text() -> str:
    lines = [
        "Chorus-WebAI | 网页 AI 协同引擎 v2.3 接口文档",
        "",
        "=== 核心架构特性 ===",
        "1. 多模型接力 (Relay)：支持使用 {prev_result} 引用前序任务输出",
        "2. 语义锚点 (Anchor)：内置 A11y 降级定位策略，增强对 UI 改版的抗性",
        "3. 视觉证据链 (Evidence)：自动记录错误现场快照与黑匣子日志",
        "4. 故障自愈 (Recovery)：线性回退重试 + 本地 Ollama 降级",
        "",
        "=== v2.3 新特性 ===",
        "5. 任务追踪 (TaskTracker)：完整生命周期管理、事件监听、依赖解析",
        "6. 记忆存储 (MemoryStore)：多会话管理、上下文窗口、消息搜索",
        "7. 工作流引擎 (Workflow)：DAG编排、条件分支、并行执行",
        "8. 监控告警 (Monitor)：指标收集、健康检查、告警管理",
        "",
        "=== 功能事件列表 ===",
        "",
        "-- 平台与配置 --",
        "1. 应用平台预设 - 切换目标 AI 平台",
        "2. 保存参数 - 持久化配置到 config.json",
        "3. 打开登录浏览器 - 启动持久化浏览器会话",
        "4. 登录完成检查 - 验证登录状态并保存会话",
        "5. 执行冒烟测试 - 发送测试消息验证链路",
        "6. 一键准备 - 自动执行初始化流程",
        "",
        "-- 任务执行 --",
        "7. 开始执行 - 发送任务并等待响应",
        "8. 复用上次输入 - 快速填充历史输入",
        "9. 导出结果 - 保存响应为 MD/TXT 文件",
        "",
        "-- 批量队列 --",
        "10. 加入队列 - 添加任务到批量队列",
        "11. 执行首项 - 处理队列首个任务",
        "12. 清空队列 - 移除所有待处理任务",
        "",
        "-- 工作流引擎 --",
        "13. 查看工作流详情 - 显示步骤和依赖",
        "14. 执行工作流 - 运行完整工作流",
        "",
        "-- 记忆存储 --",
        "15. 创建会话 - 新建对话会话",
        "16. 切换会话 - 切换到指定会话",
        "17. 查看上下文 - 显示会话历史",
        "",
        "-- 监控面板 --",
        "18. 刷新仪表盘 - 获取系统状态",
        "19. 任务统计 - 查看执行统计",
        "20. 健康检查 - 系统组件状态",
        "",
        "-- 历史与诊断 --",
        "21. 刷新历史 - 同步任务记录",
        "22. 清空历史 - 清除所有记录",
        "23. 健康检查 - 完整系统诊断",
        "24. 查看错误日志 - 显示最近异常",
        "",
        "=== 平台支持 ===",
    ]
    for p in PROVIDERS.values():
        lines.append(f"- {p['label']} {p['url']} 发送方式 {p['send_mode']}")
    lines.extend(
        [
            "",
            "=== 模块结构 (src/) ===",
            "core/        - 核心引擎 (config, browser, exceptions)",
            "models/      - 数据模型 (task, session, history)",
            "services/    - 业务服务 (task_tracker, memory_store, workflow, monitor)",
            "utils/       - 工具函数 (cache, helpers)",
            "",
            "=== 说明 ===",
            "本工具通过浏览器自动化与网页 AI 交互",
            "登录、验证码、风控等步骤需用户人工配合",
            "",
            "详细使用指南请参阅: docs/USER_GUIDE.md",
        ]
    )
    return "\n".join(lines)


def _export_api_doc() -> Tuple[str, str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DOCS_DIR / f"api_doc_{ts}.md"
    path.write_text(_build_api_doc_text(), encoding="utf-8")
    return str(path), f"接口文档已生成 {path.name}"


def _profile_has_login_data() -> bool:
    try:
        return core.PROFILE_DIR.exists() and any(core.PROFILE_DIR.iterdir())
    except Exception:
        return False


def _history_has_success(template: str | None = None) -> bool:
    rows = core.read_history(limit=120)
    for row in rows:
        if not bool(row.get("ok", False)):
            continue
        if template is None or row.get("template") == template:
            return True
    return False


def _build_guide_markdown() -> str:
    cfg = core.load_config()
    has_login = _profile_has_login_data()
    has_smoke = _history_has_success("smoke")
    has_task_success = _history_has_success()

    step1 = "已完成 已保存配置" if cfg.get("target_url") else "待完成 请先保存配置"
    step2 = "已完成 检测到登录会话" if has_login else "待完成 请点击 打开登录浏览器"
    step3 = "已完成 冒烟测试通过" if has_smoke else "待完成 建议先执行冒烟测试"
    step4 = "已完成 已有成功任务" if has_task_success else "待完成 前往 执行任务 完成首个任务"

    return "\n".join(
        [
            "### 新手进度",
            f"1 {step1}",
            f"2 {step2}",
            f"3 {step3}",
            f"4 {step4}",
            "",
            "建议 首次使用按顺序完成一到四",
        ]
    )


def _template_help(template_label: str) -> str:
    guide = TEMPLATE_GUIDE.get(template_label, "")
    return f"模板说明 {guide}" if guide else "模板说明 请选择模板后开始输入"


def _input_tip(user_input: str) -> str:
    text = (user_input or "").strip()
    length = len(text)
    if length == 0:
        return "输入提示 请粘贴正文或直接写需求"
    if length < 20:
        return f"输入长度 {length} 字 建议补充上下文 结果会更稳定"
    if length > 6000:
        return f"输入长度 {length} 字 内容较长 建议分段执行"
    return f"输入长度 {length} 字 内容质量正常 可直接执行"


def _history_table(filter_mode: str = "全部") -> List[List[Any]]:
    rows = core.read_history(limit=120)
    out: List[List[Any]] = []
    for row in rows:
        ok = bool(row.get("ok", False))
        if filter_mode == "仅成功" and not ok:
            continue
        if filter_mode == "仅失败" and ok:
            continue
        out.append(
            [
                row.get("time", "-"),
                KEY_TO_TEMPLATE_LABEL.get(str(row.get("template", "-")), str(row.get("template", "-"))),
                row.get("duration_seconds", "-"),
                row.get("response_chars", "-"),
                "成功" if ok else "失败",
                str(row.get("error", ""))[:200],
            ]
        )
    return out


def _clear_history() -> Tuple[str, List[List[Any]]]:
    core.HISTORY_PATH.write_text("", encoding="utf-8")
    return "历史记录已清空", _history_table("全部")


def _latest_errors() -> str:
    files = sorted(core.ERROR_DIR.glob("error_*.txt"), reverse=True)
    if not files:
        return f"暂无错误日志 目录 {core.ERROR_DIR}"
    lines: List[str] = []
    for fp in files[:5]:
        lines.append(f"[{fp.name}]")
        try:
            lines.append(fp.read_text(encoding="utf-8")[:800])
        except Exception as exc:
            lines.append(f"读取失败 {exc}")
        lines.append("")
    return "\n".join(lines)


def _health_check() -> str:
    cfg = core.load_config()
    
    # Get task statistics from tracker
    tracker = _get_task_tracker()
    task_stats = tracker.get_statistics()
    
    # Get memory statistics
    memory = _get_memory_store()
    memory_stats = memory.get_statistics()
    
    status = {
        "状态目录": str(core.STATE_DIR),
        "登录目录存在": core.PROFILE_DIR.exists(),
        "登录目录有内容": _profile_has_login_data(),
        "历史文件存在": core.HISTORY_PATH.exists(),
        "错误目录存在": core.ERROR_DIR.exists(),
        "目标网址": cfg.get("target_url"),
        "发送前确认": cfg.get("confirm_before_send"),
        "重试次数": cfg.get("max_retries"),
        "当前平台": cfg.get("provider_key", "deepseek"),
        # New metrics
        "任务统计": task_stats,
        "内存统计": memory_stats,
    }
    return json.dumps(status, ensure_ascii=False, indent=2)


def _pick_available_port(start: int = 7860, end: int = 7875) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"{start} 到 {end} 端口均被占用 请先关闭占用进程")


def _load_config_for_form() -> Tuple[str, str, str, bool, int, int, str, str, str, str]:
    cfg = core.load_config()
    provider_label = _provider_label_from_config(cfg)
    status = f"已加载配置 URL {cfg['target_url']} 重试 {cfg['max_retries']} 超时 {cfg['response_timeout_seconds']} 秒"
    return (
        provider_label,
        str(cfg["target_url"]),
        str(cfg["send_mode"]),
        bool(cfg["confirm_before_send"]),
        int(cfg["max_retries"]),
        int(cfg["response_timeout_seconds"]),
        status,
        _build_guide_markdown(),
        _provider_guide_text(provider_label),
        _build_api_doc_text(),
    )


def _apply_provider(provider_label: str) -> Tuple[str, str, str, str]:
    key = PROVIDER_LABEL_TO_KEY.get(provider_label, "deepseek")
    item = PROVIDERS[key]
    return item["url"], item["send_mode"], _provider_guide_text(provider_label), f"已切换平台 {item['label']}"


def _save_config_from_form(
    provider_label: str,
    target_url: str,
    send_mode: str,
    confirm_before_send: bool,
    max_retries: int,
    response_timeout_seconds: int,
) -> Tuple[str, str, str]:
    cfg = core.load_config()
    cfg["provider_key"] = PROVIDER_LABEL_TO_KEY.get(provider_label, "deepseek")
    cfg["target_url"] = target_url.strip() or cfg["target_url"]
    cfg["send_mode"] = send_mode
    cfg["confirm_before_send"] = bool(confirm_before_send)
    cfg["max_retries"] = int(max_retries)
    cfg["response_timeout_seconds"] = int(response_timeout_seconds)
    core.save_config(cfg)
    return "配置已保存", _build_guide_markdown(), _provider_guide_text(provider_label)


async def _close_login_session() -> None:
    async with get_login_lock():
        ctx = LOGIN_STATE.get("context")
        p = LOGIN_STATE.get("p")
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:
                pass
        if p is not None:
            try:
                await p.stop()
            except Exception:
                pass
        LOGIN_STATE.update({"p": None, "context": None, "page": None})


async def _open_login_browser() -> Tuple[str, str]:
    cfg = core.load_config()
    try:
        async with get_login_lock():
            if LOGIN_STATE.get("context") is not None:
                return "登录浏览器已打开 请在该窗口完成登录", _build_guide_markdown()
            p, context, page = await core.open_chat_page(cfg)
            LOGIN_STATE.update({"p": p, "context": context, "page": page})
        return "已打开登录浏览器 请登录后回到本页面点击 登录完成检查", _build_guide_markdown()
    except Exception as exc:
        await _close_login_session()
        return (
            "打开浏览器失败 请先执行 .venv\\Scripts\\python.exe -m playwright install chromium 然后重试 错误 "
            f"{exc}",
            _build_guide_markdown(),
        )


async def _finish_login_check() -> Tuple[str, str]:
    async with get_login_lock():
        page = LOGIN_STATE.get("page")
        if page is None:
            return "未检测到登录会话 请先点击 打开登录浏览器", _build_guide_markdown()

    cfg = core.load_config()
    ok = await core.get_first_visible_locator(page, cfg["input_selectors"], timeout_ms=3500) is not None
    await _close_login_session()
    if ok:
        return "登录检查通过 会话已持久化保存", _build_guide_markdown()
    return "未检测到聊天输入框 请重新打开登录浏览器确认页面状态", _build_guide_markdown()


async def _run_smoke_test(smoke_confirm: bool, smoke_pause_seconds: int) -> Tuple[str, str]:
    if not smoke_confirm:
        return "请先勾选冒烟测试确认后再执行", _build_guide_markdown()
    cfg = core.load_config()
    cfg["smoke_pause_seconds"] = int(smoke_pause_seconds)
    run_cfg = copy.deepcopy(cfg)
    run_cfg["confirm_before_send"] = False

    started = time.time()
    try:
        pause_seconds = max(0, int(run_cfg.get("smoke_pause_seconds", 3)))
        if pause_seconds > 0:
            await asyncio.sleep(pause_seconds)

        result = ""
        async for chunk in core.send_with_retry(run_cfg, "Reply with exactly: READY"):
            result = chunk
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": "smoke",
                "input_chars": 24,
                "response_chars": len(result),
                "duration_seconds": elapsed,
                "ok": True,
            }
        )
        return f"冒烟测试成功 用时 {elapsed} 秒 返回 {result[:120]}", _build_guide_markdown()
    except Exception as exc:
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": "smoke",
                "input_chars": 24,
                "response_chars": 0,
                "duration_seconds": elapsed,
                "ok": False,
                "error": str(exc),
            }
        )
        return f"冒烟测试失败 用时 {elapsed} 秒 错误 {exc}", _build_guide_markdown()


async def _one_click_prepare() -> Tuple[str, str]:
    msg, guide = await _open_login_browser()
    tip = "已执行自动准备 下一步请在新浏览器中登录 然后点击 登录完成检查 和 执行冒烟测试"
    return f"{tip}\n{msg}", guide


async def _run_task(template_label: str, user_input: str, confirmed: bool):
    raw_input = (user_input or "").strip()
    if not raw_input:
        yield "任务已取消 输入为空", "", "", "输入提示 请先填写任务内容", _history_table("全部")
        return

    LAST_INPUT["template"] = template_label
    LAST_INPUT["content"] = raw_input

    cfg = core.load_config()
    if cfg.get("confirm_before_send", True) and not confirmed:
        yield "请先勾选 我确认发送 后再执行", "", "", _input_tip(raw_input), _history_table("全部")
        return

    template_key = TEMPLATE_LABEL_TO_KEY.get(template_label, "custom")
    prompt = core.build_prompt(template_key, raw_input)
    run_cfg = copy.deepcopy(cfg)
    run_cfg["confirm_before_send"] = False

    started = time.time()
    response = ""
    try:
        async for chunk in core.send_with_retry(run_cfg, prompt):
            response = chunk
            elapsed = round(time.time() - started, 2)
            yield f"执行中... 用时 {elapsed} 秒，收到 {len(response)} 字", prompt[:3000], response, _input_tip(raw_input), _history_table("全部")
            
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": template_key,
                "input_chars": len(raw_input),
                "response_chars": len(response),
                "duration_seconds": elapsed,
                "ok": True,
            }
        )
        status = f"执行成功 用时 {elapsed} 秒 返回 {len(response)} 字"
        yield status, prompt[:3000], response, _input_tip(raw_input), _history_table("全部")
    except Exception as exc:
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": template_key,
                "input_chars": len(raw_input),
                "response_chars": len(response),
                "duration_seconds": elapsed,
                "ok": False,
                "error": str(exc),
            }
        )
        yield f"执行失败 用时 {elapsed} 秒 错误 {exc}", prompt[:3000], response, _input_tip(raw_input), _history_table("全部")


def _reuse_last_input() -> Tuple[str, str]:
    template = LAST_INPUT.get("template", "摘要总结")
    content = LAST_INPUT.get("content", "")
    return template, content


def _export_response(response: str) -> Tuple[str, str]:
    text = (response or "").strip()
    if not text:
        return "", "没有可导出的结果 请先执行任务"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt = EXPORT_DIR / f"result_{ts}.txt"
    md = EXPORT_DIR / f"result_{ts}.md"
    txt.write_text(text, encoding="utf-8")
    md.write_text(f"# 执行结果\n\n{text}\n", encoding="utf-8")
    return str(txt), f"导出完成 文件 {txt.name} 和 {md.name}"



async def _add_to_queue(template_label: str, user_input: str) -> str:
    raw_input = (user_input or "").strip()
    if not raw_input:
        return "提示: 任务内容为空，未加入队列"
    async with get_queue_lock():
        item = QueueItem(template_label=template_label, user_input=raw_input)
        TASK_QUEUE.append(item)
        
        # Create task in tracker
        tracker = _get_task_tracker()
        template_key = TEMPLATE_LABEL_TO_KEY.get(template_label, "custom")
        task = await tracker.create_task(
            template_key=template_key,
            user_input=raw_input,
            prompt=core.build_prompt(template_key, raw_input),
        )
        item.task_id = task.id
        
    return f"已成功加入队列 (ID: {item.id}, TaskID: {task.id})，当前队列长度: {len(TASK_QUEUE)}"

def _render_queue_table() -> List[List[Any]]:
    return [[item.id, item.added_at, item.template_label, item.user_input[:20], item.status, item.result[:30]] for item in TASK_QUEUE]

async def _process_queue_once():
    tracker = _get_task_tracker()
    monitor = _get_monitor()
    
    async with get_queue_lock():
        pending = [item for item in TASK_QUEUE if item.status == "等待中"]
        if not pending:
            return "队列中没有等待执行的任务", _render_queue_table()
        
        # 获取当前任务及其索引
        current_idx = TASK_QUEUE.index(pending[0])
        target = TASK_QUEUE[current_idx]
        
        # 提取前序任务结果 (如果有的话)
        prev_result = ""
        if current_idx > 0:
            prev_result = str(TASK_QUEUE[current_idx - 1].result)
        
        target.status = "执行中"
        
        # Update task tracker
        if target.task_id:
            await tracker.start_task(target.task_id)
    
    cfg = core.load_config()
    run_cfg = copy.deepcopy(cfg)
    run_cfg["confirm_before_send"] = False
    template_key = TEMPLATE_LABEL_TO_KEY.get(target.template_label, "custom")
    
    # 动态注入前序结果
    processed_input = target.user_input.replace("{prev_result}", prev_result)
    prompt = core.build_prompt(template_key, processed_input)

    started = time.time()
    response = ""
    ok = False
    try:
        async for chunk in core.send_with_retry(run_cfg, prompt):
            response = chunk
            target.result = f"收到 {len(response)} 字..."
        
        if not response:
            raise RuntimeError("Task executed but returned empty response.")
            
        target.status = "执行成功"
        target.result = response
        ok = True
        
        # Complete task in tracker
        if target.task_id:
            await tracker.complete_task(target.task_id, response)
            monitor.record_task_execution(True, time.time() - started, template_key)
            
    except Exception as exc:
        target.status = "执行失败"
        target.result = f"Error: {exc}"
        ok = False
        
        # Fail task in tracker
        if target.task_id:
            await tracker.fail_task(target.task_id, str(exc))
            monitor.record_task_execution(False, time.time() - started, template_key)
            
    finally:
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": template_key,
                "input_chars": len(target.user_input),
                "response_chars": len(response),
                "duration_seconds": elapsed,
                "ok": ok,
                "error": str(target.result) if not ok else "",
                "task_id": target.task_id,
            }
        )
    return f"任务 {target.id} 已处理完毕 ({target.status})", _render_queue_table()

async def _clear_queue():
    async with get_queue_lock():
        TASK_QUEUE.clear()
    return "队列已清空", _render_queue_table()

# --- New Features: Task Statistics & Workflow Management ---

def _get_task_statistics() -> str:
    """Get task statistics from TaskTracker."""
    tracker = _get_task_tracker()
    stats = tracker.get_statistics()
    return json.dumps(stats, ensure_ascii=False, indent=2)

def _get_memory_statistics() -> str:
    """Get memory/session statistics."""
    store = _get_memory_store()
    stats = store.get_statistics()
    return json.dumps(stats, ensure_ascii=False, indent=2)

def _get_dashboard_data() -> str:
    """Get comprehensive dashboard data."""
    monitor = _get_monitor()
    data = monitor.get_dashboard_data()
    return json.dumps(data, ensure_ascii=False, indent=2)

def _list_workflows() -> List[str]:
    """List available workflow templates."""
    engine = _get_workflow_engine()
    workflows = engine.list_workflows()
    return [f"{w.name} ({w.id})" for w in workflows]

def _get_workflow_details(workflow_name: str) -> str:
    """Get details of a specific workflow."""
    engine = _get_workflow_engine()
    workflows = engine.list_workflows()
    
    for w in workflows:
        if w.name in workflow_name or w.id in workflow_name:
            steps_info = []
            for step in w.steps:
                steps_info.append(f"  - {step.name} ({step.step_type.value})")
            
            return f"""Workflow: {w.name}
ID: {w.id}
Version: {w.version}
Description: {w.description}

Steps:
""" + "\n".join(steps_info)
    
    return "Workflow not found"

async def _execute_workflow(workflow_name: str, user_input: str) -> Tuple[str, str]:
    """Execute a workflow with user input."""
    engine = _get_workflow_engine()
    workflows = engine.list_workflows()
    
    workflow = None
    for w in workflows:
        if w.name in workflow_name or w.id in workflow_name:
            workflow = w
            break
    
    if not workflow:
        return "Workflow not found", ""
    
    # Execute with context
    context = {"user_input": user_input}
    
    try:
        execution = await engine.execute(workflow.id, context)
        
        if execution.state.value == "completed":
            # Get last step result
            last_result = list(execution.step_results.values())[-1] if execution.step_results else ""
            return f"Workflow completed successfully. Execution ID: {execution.id}", str(last_result)[:2000]
        else:
            return f"Workflow {execution.state.value}: {execution.error}", ""
    except Exception as e:
        return f"Workflow execution failed: {e}", ""

# --- Session Memory Functions ---

def _create_session(title: str) -> Tuple[str, List[List[Any]]]:
    """Create a new session."""
    manager = _get_session_manager()
    session = manager._store.create_session(title=title)
    manager._store.set_current_session(session.id)
    # Return success message and updated session list
    sessions = manager.list_sessions()
    session_list = [[s.id, s.title, s.message_count, s.state.value, s.updated_at.strftime("%Y-%m-%d %H:%M")] for s in sessions]
    return f"Session created: {session.id}", session_list

def _list_sessions() -> List[List[Any]]:
    """List all sessions."""
    manager = _get_session_manager()
    sessions = manager.list_sessions()
    return [[s.id, s.title, s.message_count, s.state.value, s.updated_at.strftime("%Y-%m-%d %H:%M")] for s in sessions]

def _get_session_context(session_id: str) -> str:
    """Get context from a session."""
    if not session_id or not session_id.strip():
        return "Please enter a session ID"
    store = _get_memory_store()
    context = store.get_context(session_id.strip())
    if not context:
        return "No messages in session or session not found"
    return "\n".join([f"[{m['role']}]: {m['content'][:200]}{'...' if len(m['content']) > 200 else ''}" for m in context])

def _switch_session(session_id: str) -> Tuple[str, str]:
    """Switch to a different session."""
    if not session_id or not session_id.strip():
        return "Please enter a session ID", ""
    manager = _get_session_manager()
    if manager.switch_session(session_id.strip()):
        context = _get_session_context(session_id.strip())
        return f"Switched to session: {session_id}", context
    return f"Failed to switch to session: {session_id}", ""

def _get_memory_statistics() -> str:
    """Get memory/session statistics."""
    store = _get_memory_store()
    stats = store.get_statistics()
    return json.dumps(stats, ensure_ascii=False, indent=2)

def build_ui() -> gr.Blocks:
    import gradio as gr
    provider_labels = [v["label"] for v in PROVIDERS.values()]

    with gr.Blocks(title="Chorus-WebAI | 网页 AI 协同引擎") as demo:
        gr.HTML(
            """
<div class='hero'>
  <div class='hero-title'>Chorus-WebAI</div>
  <div class='hero-sub'>跨平台 AI 协同引擎：让网页 AI 成为您的生产力突触</div>
  <div class='hero-chips'>
    <span class='hero-chip'>🎭 多模型接力 (Relay)</span>
    <span class='hero-chip'>📸 视觉证据链</span>
    <span class='hero-chip'>⚓ 语义锚点</span>
    <span class='hero-chip'>🛡️ 故障自愈</span>
  </div>
</div>
""".strip()
        )

        with gr.Tabs():
            with gr.Tab("🚀 快速上手"):
                with gr.Row():
                    with gr.Column(scale=2):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>操作向导</div>")
                            guide_markdown = gr.Markdown()
                            with gr.Row():
                                refresh_guide_btn = gr.Button("刷新进度", elem_classes=["action-secondary"])
                                one_click_btn = gr.Button("一键初始化环境", elem_classes=["action-primary"])
                    
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>智能特性</div>")
                            gr.Markdown(
                                """
- **链式接力**: `{prev_result}` 自动注入
- **自愈定位**: A11y 语义树 fallback
- **执行存证**: 自动生成错误快照
- **本地回退**: 支持 Ollama 离线方案
""".strip()
                            )

            with gr.Tab("⚙️ 平台与配置"):
                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>平台预设</div>")
                            provider_label = gr.Dropdown(provider_labels, value=PROVIDERS["deepseek"]["label"], label="目标平台")
                            apply_provider_btn = gr.Button("应用预设", elem_classes=["action-secondary"])
                            provider_guide = gr.Textbox(label="平台指引", lines=3, elem_classes=["provider-card"])

                    with gr.Column(scale=2):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>执行参数</div>")
                            with gr.Row():
                                target_url = gr.Textbox(label="入口地址", scale=2)
                                send_mode = gr.Radio(choices=[("回车", "enter"), ("点击", "button")], label="交互方式", scale=1)
                            with gr.Row():
                                confirm_before_send = gr.Checkbox(label="启用确认发送", value=True)
                                max_retries = gr.Slider(1, 6, 3, label="重试次数")
                                response_timeout = gr.Slider(30, 600, 120, label="超时限制 (s)")
                            save_btn = gr.Button("保存配置", elem_classes=["action-primary"])

                with gr.Row():
                    with gr.Column():
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>浏览器会话控制</div>")
                            with gr.Row():
                                open_login_btn = gr.Button("🔑 打开登录窗口", elem_classes=["action-secondary"])
                                finish_login_btn = gr.Button("✅ 登录状态验证", elem_classes=["action-secondary"])
                                smoke_btn = gr.Button("🔥 链路冒烟测试", elem_classes=["action-primary"])
                            with gr.Row():
                                smoke_confirm = gr.Checkbox(label="我已准备好测试")
                                smoke_pause = gr.Slider(0, 15, 3, label="测试前暂停 (s)")
                                setup_status = gr.Textbox(label="系统日志", lines=1)

            with gr.Tab("📝 执行任务"):
                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>任务编排</div>")
                            template_label = gr.Dropdown(list(TEMPLATE_LABEL_TO_KEY.keys()), value="摘要总结", label="任务模板")
                            template_help = gr.Markdown()
                            task_input = gr.Textbox(label="输入原始内容", lines=12, placeholder="在此粘贴文本或输入指令...")
                            input_tip = gr.Markdown()
                            send_confirm = gr.Checkbox(label="确认发送 (建议开启)", value=True)
                            with gr.Row():
                                run_btn = gr.Button("立即执行", elem_classes=["action-primary"])
                                reuse_btn = gr.Button("填入上次内容", elem_classes=["action-secondary"])

                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>执行反馈</div>")
                            run_status = gr.Textbox(label="执行进度", lines=1)
                            prompt_preview = gr.Textbox(label="提示词预览", lines=2, visible=False)
                            response_box = gr.Textbox(label="AI 响应内容", lines=18)
                            with gr.Row():
                                export_btn = gr.Button("导出 MD 报告", elem_classes=["action-secondary"])
                                export_file = gr.File(label="点击下载", interactive=False)
                                export_status = gr.Textbox(label="导出状态", lines=1, visible=False)

            with gr.Tab("📊 批量任务队列"):
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>添加链式任务</div>")
                    with gr.Row():
                        q_template = gr.Dropdown(list(TEMPLATE_LABEL_TO_KEY.keys()), value="摘要总结", label="模板")
                        q_input = gr.Textbox(label="内容 (支持 {prev_result})", scale=3)
                        q_add_btn = gr.Button("加入队列", elem_classes=["action-primary"], scale=1)
                        q_add_status = gr.Textbox(label="添加结果", lines=1, visible=False)
                
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>队列监控</div>")
                    with gr.Row():
                        q_run_btn = gr.Button("▶ 执行首项", elem_classes=["action-primary"])
                        q_clear_btn = gr.Button("🗑️ 清空全部", elem_classes=["action-secondary"])
                        q_refresh_btn = gr.Button("🔄 刷新状态", elem_classes=["action-secondary"])
                    q_run_status = gr.Textbox(label="运行状态", lines=1)
                    q_grid = gr.Dataframe(headers=["ID", "添加时间", "模板", "预览", "状态", "结果"], interactive=False)

            with gr.Tab("🛠️ 诊断与历史"):
                with gr.Group(elem_classes=["section-card"]):
                    with gr.Row():
                        history_filter = gr.Radio(choices=HISTORY_FILTERS, value="全部", label="结果过滤")
                        refresh_history_btn = gr.Button("同步历史", elem_classes=["action-secondary"])
                    history_grid = gr.Dataframe(interactive=False)
                    with gr.Row():
                        health_btn = gr.Button("系统体检", elem_classes=["action-secondary"])
                        error_btn = gr.Button("日志回溯", elem_classes=["action-secondary"])
                        clear_history_btn = gr.Button("清空记录", elem_classes=["action-secondary"])
                    diag_box = gr.Textbox(label="控制台输出", lines=10, elem_classes=["provider-card"])

            # New Tab: Workflow Engine
            with gr.Tab("🔄 工作流引擎"):
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>工作流模板</div>")
                    with gr.Row():
                        workflow_select = gr.Dropdown(choices=_list_workflows(), label="选择工作流")
                        workflow_info_btn = gr.Button("查看详情", elem_classes=["action-secondary"])
                    workflow_details = gr.Textbox(label="工作流详情", lines=6, interactive=False)
                
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>执行工作流</div>")
                    workflow_input = gr.Textbox(label="输入内容", lines=4, placeholder="输入工作流所需的内容...")
                    with gr.Row():
                        workflow_run_btn = gr.Button("▶ 执行工作流", elem_classes=["action-primary"])
                        workflow_status = gr.Textbox(label="执行状态", lines=1)
                    workflow_result = gr.Textbox(label="执行结果", lines=10)

            # New Tab: Memory & Sessions
            with gr.Tab("💾 记忆存储"):
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>会话管理</div>")
                    with gr.Row():
                        session_title = gr.Textbox(label="新会话标题", scale=2)
                        create_session_btn = gr.Button("创建会话", elem_classes=["action-primary"])
                    session_list = gr.Dataframe(headers=["ID", "标题", "消息数", "状态", "更新时间"], interactive=False)
                    with gr.Row():
                        refresh_sessions_btn = gr.Button("刷新列表", elem_classes=["action-secondary"])
                        switch_session_input = gr.Textbox(label="切换到会话ID")
                        switch_session_btn = gr.Button("切换会话", elem_classes=["action-secondary"])
                
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>会话上下文</div>")
                    session_context_btn = gr.Button("查看当前上下文", elem_classes=["action-secondary"])
                    session_context = gr.Textbox(label="对话历史", lines=8, interactive=False)
                    memory_stats = gr.Textbox(label="内存统计", lines=3)

            # New Tab: Monitoring Dashboard
            with gr.Tab("📈 监控面板"):
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>系统监控</div>")
                    with gr.Row():
                        dashboard_refresh_btn = gr.Button("刷新仪表盘", elem_classes=["action-primary"])
                        task_stats_btn = gr.Button("任务统计", elem_classes=["action-secondary"])
                    dashboard_data = gr.Textbox(label="仪表盘数据", lines=15)
                
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>性能指标</div>")
                    with gr.Row():
                        metrics_health_btn = gr.Button("健康检查", elem_classes=["action-secondary"])
                        metrics_tasks_btn = gr.Button("任务指标", elem_classes=["action-secondary"])
                    metrics_display = gr.Textbox(label="性能数据", lines=10)

        with gr.Tab("帮助文档"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>接口文档与使用指引</div>")
                api_doc_box = gr.Textbox(label="接口文档内容", lines=18)
                with gr.Row():
                    refresh_doc_btn = gr.Button("刷新接口文档", elem_classes=["action-secondary"])
                    export_doc_btn = gr.Button("导出接口文档", elem_classes=["action-primary"])
                api_doc_file = gr.File(label="接口文档下载", interactive=False)
                api_doc_status = gr.Textbox(label="文档状态", lines=2)

        apply_provider_btn.click(
            fn=_apply_provider,
            inputs=[provider_label],
            outputs=[target_url, send_mode, provider_guide, setup_status],
        )

        save_btn.click(
            fn=_save_config_from_form,
            inputs=[provider_label, target_url, send_mode, confirm_before_send, max_retries, response_timeout],
            outputs=[setup_status, guide_markdown, provider_guide],
        )

        open_login_btn.click(fn=_open_login_browser, outputs=[setup_status, guide_markdown])
        finish_login_btn.click(fn=_finish_login_check, outputs=[setup_status, guide_markdown])
        smoke_btn.click(fn=_run_smoke_test, inputs=[smoke_confirm, smoke_pause], outputs=[setup_status, guide_markdown])
        one_click_btn.click(fn=_one_click_prepare, outputs=[setup_status, guide_markdown])

        template_label.change(fn=_template_help, inputs=[template_label], outputs=[template_help])
        task_input.change(fn=_input_tip, inputs=[task_input], outputs=[input_tip])
        reuse_btn.click(fn=_reuse_last_input, outputs=[template_label, task_input])

        run_btn.click(
            fn=_run_task,
            inputs=[template_label, task_input, send_confirm],
            outputs=[run_status, prompt_preview, response_box, input_tip, history_grid],
        )
        export_btn.click(fn=_export_response, inputs=[response_box], outputs=[export_file, export_status])

        refresh_guide_btn.click(fn=_build_guide_markdown, outputs=[guide_markdown])
        refresh_history_btn.click(fn=_history_table, inputs=[history_filter], outputs=[history_grid])
        history_filter.change(fn=_history_table, inputs=[history_filter], outputs=[history_grid])
        clear_history_btn.click(fn=_clear_history, outputs=[diag_box, history_grid])
        health_btn.click(fn=_health_check, outputs=[diag_box])
        error_btn.click(fn=_latest_errors, outputs=[diag_box])

        # Workflow Engine event handlers
        workflow_info_btn.click(fn=_get_workflow_details, inputs=[workflow_select], outputs=[workflow_details])
        workflow_run_btn.click(fn=_execute_workflow, inputs=[workflow_select, workflow_input], outputs=[workflow_status, workflow_result])

        # Memory & Sessions event handlers
        create_session_btn.click(fn=_create_session, inputs=[session_title], outputs=[session_context, session_list])
        refresh_sessions_btn.click(fn=_list_sessions, outputs=[session_list])
        switch_session_btn.click(fn=_switch_session, inputs=[switch_session_input], outputs=[session_context, session_context])
        session_context_btn.click(fn=_get_session_context, inputs=[switch_session_input], outputs=[session_context])
        
        # Monitoring Dashboard event handlers
        dashboard_refresh_btn.click(fn=_get_dashboard_data, outputs=[dashboard_data])
        task_stats_btn.click(fn=_get_task_statistics, outputs=[dashboard_data])
        metrics_health_btn.click(fn=_get_dashboard_data, outputs=[metrics_display])
        metrics_tasks_btn.click(fn=_get_task_statistics, outputs=[metrics_display])

        q_add_btn.click(fn=_add_to_queue, inputs=[q_template, q_input], outputs=[q_add_status])
        q_refresh_btn.click(fn=_render_queue_table, outputs=[q_grid])
        q_clear_btn.click(fn=_clear_queue, outputs=[q_run_status, q_grid])
        q_run_btn.click(fn=_process_queue_once, outputs=[q_run_status, q_grid])
        demo.load(fn=_render_queue_table, outputs=[q_grid])

        refresh_doc_btn.click(fn=_build_api_doc_text, outputs=[api_doc_box])
        export_doc_btn.click(fn=_export_api_doc, outputs=[api_doc_file, api_doc_status])

        demo.load(
            fn=_load_config_for_form,
            outputs=[
                provider_label,
                target_url,
                send_mode,
                confirm_before_send,
                max_retries,
                response_timeout,
                setup_status,
                guide_markdown,
                provider_guide,
                api_doc_box,
            ],
        )
        demo.load(fn=_history_table, inputs=[history_filter], outputs=[history_grid])
        demo.load(fn=_list_sessions, outputs=[session_list])
        demo.load(fn=_get_dashboard_data, outputs=[dashboard_data])
        demo.load(fn=_get_memory_statistics, outputs=[memory_stats])

        gr.HTML(
            """
<div class='cn-quick-actions'>
  <div class='cn-quick-title'>常用功能</div>
  <div class='cn-quick-grid'>
    <a class='cn-quick-btn' href='javascript:window.scrollTo({top:0,behavior:"smooth"})'>返回顶部</a>
    <a class='cn-quick-btn' href='https://www.gradio.app/docs' target='_blank'>框架说明</a>
    <a class='cn-quick-btn' href='https://platform.openai.com/docs' target='_blank'>开发参考</a>
  </div>
  <div class='cn-quick-tip'>接口文档功能已内置在帮助文档页 可直接刷新和导出</div>
</div>
""".strip()
        )

    return demo


def main() -> None:
    _ensure_dirs()
    # 确保元数据已加载，以便 build_ui 能正确渲染
    _load_metadata()
    import gradio as gr
    app = build_ui()
    app.queue(default_concurrency_limit=1)
    port = _pick_available_port(7860, 7875)
    
    app.launch(
        server_name="127.0.0.1", 
        server_port=port, 
        inbrowser=True, 
        theme=gr.themes.Soft(), 
        css=CUSTOM_CSS
    )


if __name__ == "__main__":
    main()
