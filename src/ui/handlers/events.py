"""Event handlers extracted from web_app.py for better code organization."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    pass

import main as core
from src.core.session import (
    get_last_input_lock,
)
from src.core.config import (
    provider_label_from_config,
    provider_guide_text,
)
from src.utils.cache import cache_result
from src.ui.state import (
    KEY_TO_TEMPLATE_LABEL,
    PROVIDER_LABEL_TO_KEY,
    PROVIDERS,
    TEMPLATE_GUIDE,
    TEMPLATE_LABEL_TO_KEY,
    LOGIN_STATE,
    LAST_INPUT,
    get_login_lock,
)
from src.utils.i18n import t

logger = logging.getLogger(__name__)


def _sanitize_error(error_msg: str) -> str:
    """Remove sensitive paths and information from error messages.

    Replaces absolute file paths with placeholder to prevent leaking
    system-specific path information.
    """
    import re

    # Replace URLs first to avoid being affected by path regexes
    error_msg = re.sub(r"https?://\S+", "<URL>", error_msg)
    # Replace Windows-style absolute paths (e.g., D:\folder\file)
    error_msg = re.sub(r"[A-Za-z]:\\[\w\\]+", "<PATH>", error_msg)
    # Replace Unix-style absolute paths (e.g., /home/user/folder)
    # Use negative lookbehind to avoid matching :// (URL protocol)
    error_msg = re.sub(r"(?<!:)/[\w/]+", "<PATH>", error_msg)
    return error_msg


@dataclass
class ValidationResult:
    """Result of input validation with border color feedback."""

    is_valid: bool
    border_color: str  # CSS color for border
    message: str


# Backward compatibility aliases for functions moved to config.py
_provider_label_from_config = provider_label_from_config
_provider_guide_text = provider_guide_text


@cache_result(ttl=600)
def _build_api_doc_text() -> str:
    lines = [
        "ShadowBoard 网页 AI 半自动助手 接口文档",
        "",
        "功能事件列表",
        "1 应用平台预设 事件 应用平台预设",
        "2 保存参数 事件 保存参数",
        "3 打开登录浏览器 事件 打开登录浏览器",
        "4 登录完成检查 事件 登录完成检查",
        "5 执行冒烟测试 事件 执行冒烟测试",
        "6 一键准备 事件 一键准备",
        "7 开始执行 事件 开始执行",
        "8 复用上次输入 事件 复用上次输入",
        "9 导出结果 事件 导出结果",
        "10 刷新历史 事件 刷新历史",
        "11 清空历史 事件 清空历史",
        "12 健康检查 事件 健康检查",
        "13 查看最近错误日志 事件 查看最近错误日志",
        "",
        "平台支持",
    ]
    for p in PROVIDERS.values():
        lines.append(f"- {p['label']} {p['url']} 发送方式 {p['send_mode']}")
    lines.extend(
        [
            "",
            "说明",
            "本工具通过浏览器自动化与网页 AI 交互",
            "登录 验证码 风控等步骤需用户人工配合",
        ]
    )
    return "\n".join(lines)


def _export_api_doc() -> Tuple[str, str]:
    from web_app import DOCS_DIR

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DOCS_DIR / f"api_doc_{ts}.md"
    path.write_text(_build_api_doc_text(), encoding="utf-8")
    return str(path), f"接口文档已生成 {path.name}"


def _profile_has_login_data() -> bool:
    try:
        return core.PROFILE_DIR.exists() and any(core.PROFILE_DIR.iterdir())
    except Exception as exc:
        logger.warning(f"Failed to check profile login data: {exc}", exc_info=True)
        return False


def _history_has_success(template: str | None = None) -> bool:
    rows = core.read_history(limit=120)
    for row in rows:
        if not bool(row.get("ok", False)):
            continue
        if template is None or row.get("template") == template:
            return True
    return False


@cache_result(ttl=300)
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


@cache_result(ttl=600)
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


def _validate_task_input(user_input: str) -> Tuple[str, str]:
    """Validate task input and return tip with border color class.

    Returns:
        Tuple of (tip_message, border_color_class)
    """
    text = (user_input or "").strip()
    length = len(text)

    if length == 0:
        return "输入提示 请粘贴正文或直接写需求", "border-empty"
    if length < 20:
        return f"输入长度 {length} 字 建议补充上下文 结果会更稳定", "border-warning"
    if length > 6000:
        return f"输入长度 {length} 字 内容较长 建议分段执行", "border-warning"
    return f"输入长度 {length} 字 内容质量正常 可直接执行", "border-valid"


def _validate_target_url(url: str) -> Tuple[str, str]:
    """Validate target URL and return status with border color class.

    Returns:
        Tuple of (status_message, border_color_class)
    """
    text = (url or "").strip()
    if not text:
        return "目标网址 不能为空", "border-error"

    # Basic URL format check
    if not text.startswith(("http://", "https://")):
        return "目标网址 必须以 http:// 或 https:// 开头", "border-error"

    if len(text) < 10:
        return "目标网址 长度不足", "border-error"

    return "目标网址 格式正确", "border-valid"


def _validate_max_retries(value: int) -> Tuple[str, str]:
    """Validate max retries value.

    Returns:
        Tuple of (status_message, border_color_class)
    """
    if value < 1:
        return "重试次数 不能小于1", "border-error"
    if value > 6:
        return "重试次数 最大为6", "border-error"
    return "重试次数 格式正确", "border-valid"


def _validate_response_timeout(value: int) -> Tuple[str, str]:
    """Validate response timeout value.

    Returns:
        Tuple of (status_message, border_color_class)
    """
    if value < 30:
        return "超时时间 不能小于30秒", "border-error"
    if value > 600:
        return "超时时间 最大为600秒", "border-error"
    return "超时时间 格式正确", "border-valid"


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


def _clear_history(clear_confirm: bool) -> Tuple[str, List[List[Any]]]:
    if not clear_confirm:
        return "请先勾选 确认清空历史 再点击清空按钮", _history_table("全部")
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
            raw_error = fp.read_text(encoding="utf-8")[:800]
            lines.append(_sanitize_error(raw_error))
        except Exception as exc:
            lines.append(f"读取失败 {_sanitize_error(str(exc))}")
        lines.append("")
    return "\n".join(lines)


async def _health_check() -> str:
    cfg = core.load_config()
    task_stats = await _get_task_tracker().get_statistics()
    memory_stats = await _get_memory_store().get_statistics()
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
        "任务统计": task_stats,
        "内存统计": memory_stats,
    }
    return json.dumps(status, ensure_ascii=False, indent=2)


def _get_task_tracker():
    from src.core.dependencies import get_task_tracker

    return get_task_tracker()


def _get_memory_store():
    from src.core.dependencies import get_memory_store

    return get_memory_store()


def _load_config_for_form() -> Tuple[str, str, str, bool, int, int, str, str, str, str]:
    cfg = core.load_config()
    provider_label = provider_label_from_config(cfg)
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
        provider_guide_text(provider_label),
        _build_api_doc_text(),
    )


def _apply_provider(provider_label: str) -> Tuple[str, str, str, str]:
    key = PROVIDER_LABEL_TO_KEY.get(provider_label, "deepseek")
    item = PROVIDERS[key]
    return (
        item["url"],
        item["send_mode"],
        provider_guide_text(provider_label),
        f"已切换平台 {item['label']}",
    )


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
    return "配置已保存", _build_guide_markdown(), provider_guide_text(provider_label)


async def _close_login_session() -> None:
    async with get_login_lock():
        ctx = LOGIN_STATE.get("context")
        p = LOGIN_STATE.get("p")
        if ctx is not None:
            try:
                await ctx.close()
            except Exception as exc:
                logger.warning(f"Failed to close browser context: {exc}", exc_info=True)
        if p is not None:
            try:
                await p.stop()
            except Exception as exc:
                logger.warning(f"Failed to stop browser process: {exc}", exc_info=True)
        LOGIN_STATE.update({"p": None, "context": None, "page": None})


async def _open_login_browser() -> Tuple[str, str]:
    cfg = core.load_config()
    try:
        async with get_login_lock():
            if LOGIN_STATE.get("context") is not None:
                return "登录浏览器已打开 请在该窗口完成登录", _build_guide_markdown()
            p, context, page = await core.open_chat_page(cfg)
            LOGIN_STATE.update({"p": p, "context": context, "page": page})
        return (
            "已打开登录浏览器 请登录后回到本页面点击 登录完成检查",
            _build_guide_markdown(),
        )
    except Exception as exc:
        await _close_login_session()
        return (
            t("errors.browser_open_failed", error=_sanitize_error(str(exc))),
            _build_guide_markdown(),
        )


async def _finish_login_check() -> Tuple[str, str]:
    async with get_login_lock():
        page = LOGIN_STATE.get("page")
        if page is None:
            return t("errors.login_not_detected"), _build_guide_markdown()

    cfg = core.load_config()
    ok = await core.get_first_visible_locator(page, cfg["input_selectors"], timeout_ms=3500) is not None
    await _close_login_session()
    if ok:
        return t("errors.login_check_passed"), _build_guide_markdown()
    return (
        t("errors.no_chat_input_detected"),
        _build_guide_markdown(),
    )


async def _run_smoke_test(smoke_confirm: bool, smoke_pause_seconds: int) -> Tuple[str, str]:
    if not smoke_confirm:
        return t("errors.smoke_test_confirm_required"), _build_guide_markdown()
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
        return (
            f"冒烟测试成功 用时 {elapsed} 秒 返回 {result[:120]}",
            _build_guide_markdown(),
        )
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
                "error": _sanitize_error(str(exc)),
            }
        )
        return t("errors.smoke_test_failed", elapsed=elapsed, error=_sanitize_error(str(exc))), _build_guide_markdown()


async def _one_click_prepare() -> Tuple[str, str]:
    msg, guide = await _open_login_browser()
    tip = "已执行自动准备 下一步请在新浏览器中登录 然后点击 登录完成检查 和 执行冒烟测试"
    return f"{tip}\n{msg}", guide


def _reuse_last_input() -> Tuple[str, str]:
    template = LAST_INPUT.get("template", "摘要总结")
    content = LAST_INPUT.get("content", "")
    return template, content


def _export_response(response: str) -> Tuple[str, str]:
    from web_app import EXPORT_DIR

    text = (response or "").strip()
    if not text:
        return "", "没有可导出的结果 请先执行任务"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt = EXPORT_DIR / f"result_{ts}.txt"
    md = EXPORT_DIR / f"result_{ts}.md"
    txt.write_text(text, encoding="utf-8")
    md.write_text(f"# 执行结果\n\n{text}\n", encoding="utf-8")
    return str(txt), f"导出完成 文件 {txt.name} 和 {md.name}"


async def _run_task(template_label: str, user_input: str, confirmed: bool):
    """Execute a single task with the given template and input."""
    import copy as copy_module

    raw_input = (user_input or "").strip()
    if not raw_input:
        yield t("errors.task_canceled_empty_input"), "", "", "输入提示 请先填写任务内容", _history_table("全部")
        return

    async with get_last_input_lock():
        LAST_INPUT["template"] = template_label
        LAST_INPUT["content"] = raw_input

    cfg = core.load_config()
    if cfg.get("confirm_before_send", True) and not confirmed:
        yield t("errors.confirm_before_send"), "", "", _input_tip(raw_input), _history_table("全部")
        return

    template_key = TEMPLATE_LABEL_TO_KEY.get(template_label, "custom")
    prompt = core.build_prompt(template_key, raw_input)
    run_cfg = copy_module.deepcopy(cfg)
    run_cfg["confirm_before_send"] = False

    started = time.time()
    response = ""
    timeout_seconds = int(run_cfg.get("response_timeout_seconds", 120))
    try:
        async for chunk in core.send_with_retry(run_cfg, prompt):
            response = chunk
            elapsed = round(time.time() - started, 2)
            progress = min(95, int((elapsed / timeout_seconds) * 100))
            yield (
                f"执行中... {progress}% 用时 {elapsed} 秒，收到 {len(response)} 字",
                prompt[:3000],
                response,
                _input_tip(raw_input),
                _history_table("全部"),
            )

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
                "error": _sanitize_error(str(exc)),
            }
        )
        yield (
            t("errors.execution_failed", elapsed=elapsed, error=_sanitize_error(str(exc))),
            prompt[:3000],
            response,
            _input_tip(raw_input),
            _history_table("全部"),
        )
