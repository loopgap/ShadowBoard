"""
Setup Tab Logic and Event Handlers
"""

from __future__ import annotations

import asyncio
import copy
import os
import signal
import time
from datetime import datetime
from typing import Any, Dict, Tuple

import main as core
from src.ui.state import (
    PROVIDERS, PROVIDER_LABEL_TO_KEY, LOGIN_STATE,
    get_login_lock,
)

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


def build_guide_markdown() -> str:
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

def load_config_for_form() -> Tuple[str, str, str, bool, int, int, str, str, str, str]:
    from src.ui.tabs.help_tab import build_api_doc_text
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
        build_guide_markdown(),
        _provider_guide_text(provider_label),
        build_api_doc_text(),
    )


def apply_provider(provider_label: str) -> Tuple[str, str, str, str]:
    key = PROVIDER_LABEL_TO_KEY.get(provider_label, "deepseek")
    item = PROVIDERS[key]
    return item["url"], item["send_mode"], _provider_guide_text(provider_label), f"已切换平台 {item['label']}"


def save_config_from_form(
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
    return "配置已保存", build_guide_markdown(), _provider_guide_text(provider_label)


async def _delayed_exit(delay: float = 2.0):
    """Wait and then terminate the process."""
    await asyncio.sleep(delay)
    # Use SIGTERM for graceful exit if possible, or kill
    os.kill(os.getpid(), signal.SIGTERM)


async def shutdown_system() -> str:
    """Clean up resources and shut down the server."""
    # 1. Close any open browser sessions
    await close_login_session()
    # 2. Schedule process termination
    asyncio.create_task(_delayed_exit(2.0))
    return "系统正在安全关闭中... 请在 2 秒后直接关闭此浏览器标签页。终端进程即将退出。"


async def close_login_session() -> None:
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


async def open_login_browser() -> Tuple[str, str]:
    cfg = core.load_config()
    try:
        async with get_login_lock():
            if LOGIN_STATE.get("context") is not None:
                return "登录浏览器已打开 请在该窗口完成登录", build_guide_markdown()
            p, context, page = await core.open_chat_page(cfg)
            LOGIN_STATE.update({"p": p, "context": context, "page": page})
        return "已打开登录浏览器 请登录后回到本页面点击 登录完成检查", build_guide_markdown()
    except Exception as exc:
        await close_login_session()
        return (
            "打开浏览器失败 请先执行 .venv\\Scripts\\python.exe -m playwright install chromium 然后重试 错误 "
            f"{exc}",
            build_guide_markdown(),
        )


async def finish_login_check() -> Tuple[str, str]:
    async with get_login_lock():
        page = LOGIN_STATE.get("page")
        if page is None:
            return "未检测到登录会话 请先点击 打开登录浏览器", build_guide_markdown()

    cfg = core.load_config()
    ok = await core.get_first_visible_locator(page, cfg["input_selectors"], timeout_ms=3500) is not None
    await close_login_session()
    if ok:
        return "登录检查通过 会话已持久化保存", build_guide_markdown()
    return "未检测到聊天输入框 请重新打开登录浏览器确认页面状态", build_guide_markdown()


async def run_smoke_test(smoke_confirm: bool, smoke_pause_seconds: int) -> Tuple[str, str]:
    if not smoke_confirm:
        return "请先勾选冒烟测试确认后再执行", build_guide_markdown()
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
        return f"冒烟测试成功 用时 {elapsed} 秒 返回 {result[:120]}", build_guide_markdown()
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
        return f"冒烟测试失败 用时 {elapsed} 秒 错误 {exc}", build_guide_markdown()


async def one_click_prepare() -> Tuple[str, str]:
    msg, guide = await open_login_browser()
    tip = "已执行自动准备 下一步请在新浏览器中登录 然后点击 登录完成检查 和 执行冒烟测试"
    return f"{tip}\n{msg}", guide
