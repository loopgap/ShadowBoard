"""
Diagnostics Tab Logic and Event Handlers
"""

from __future__ import annotations

import json
from typing import Any, List, Tuple

import main as core
from src.core.dependencies import get_task_tracker, get_memory_store
from src.ui.state import KEY_TO_TEMPLATE_LABEL


def history_table(filter_mode: str = "全部") -> List[List[Any]]:
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


def clear_history() -> Tuple[str, List[List[Any]]]:
    core.HISTORY_PATH.write_text("", encoding="utf-8")
    return "历史记录已清空", history_table("全部")


def latest_errors() -> str:
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


async def health_check() -> str:
    cfg = core.load_config()

    # Get task statistics from tracker
    tracker = get_task_tracker()
    task_stats = await tracker.get_statistics()

    # Get memory statistics
    memory = get_memory_store()
    memory_stats = await memory.get_statistics()

    status = {
        "状态目录": str(core.STATE_DIR),
        "登录目录存在": core.PROFILE_DIR.exists(),
        "登录目录有内容": (core.PROFILE_DIR.exists() and any(core.PROFILE_DIR.iterdir())),
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
