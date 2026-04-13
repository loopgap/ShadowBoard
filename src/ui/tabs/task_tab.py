"""
Task Tab Logic and Event Handlers
"""

from __future__ import annotations

import time
import copy
from datetime import datetime
from typing import Tuple

import main as core
from src.ui.state import (
    TEMPLATE_LABEL_TO_KEY, TEMPLATE_GUIDE, LAST_INPUT, EXPORT_DIR
)

def template_help(template_label: str) -> str:
    guide = TEMPLATE_GUIDE.get(template_label, "")
    return f"模板说明 {guide}" if guide else "模板说明 请选择模板后开始输入"


def input_tip(user_input: str) -> str:
    text = (user_input or "").strip()
    length = len(text)
    if length == 0:
        return "输入提示 请粘贴正文或直接写需求"
    if length < 20:
        return f"输入长度 {length} 字 建议补充上下文 结果会更稳定"
    if length > 6000:
        return f"输入长度 {length} 字 内容较长 建议分段执行"
    return f"输入长度 {length} 字 内容质量正常 可直接执行"


async def run_task(template_label: str, user_input: str, confirmed: bool):
    from src.ui.tabs.diag_tab import history_table
    raw_input = (user_input or "").strip()
    if not raw_input:
        yield "任务已取消 输入为空", "", "", "输入提示 请先填写任务内容", history_table("全部")
        return

    LAST_INPUT["template"] = template_label
    LAST_INPUT["content"] = raw_input

    cfg = core.load_config()
    if cfg.get("confirm_before_send", True) and not confirmed:
        yield "请先勾选 我确认发送 后再执行", "", "", input_tip(raw_input), history_table("全部")
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
            yield f"执行中... 用时 {elapsed} 秒，收到 {len(response)} 字", prompt[:3000], response, input_tip(raw_input), history_table("全部")
            
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
        yield status, prompt[:3000], response, input_tip(raw_input), history_table("全部")
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
        yield f"执行失败 用时 {elapsed} 秒 错误 {exc}", prompt[:3000], response, input_tip(raw_input), history_table("全部")


def reuse_last_input() -> Tuple[str, str]:
    template = LAST_INPUT.get("template", "摘要总结")
    content = LAST_INPUT.get("content", "")
    return template, content


def export_response(response: str) -> Tuple[str, str]:
    text = (response or "").strip()
    if not text:
        return "", "没有可导出的结果 请先执行任务"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt = EXPORT_DIR / f"result_{ts}.txt"
    md = EXPORT_DIR / f"result_{ts}.md"
    txt.write_text(text, encoding="utf-8")
    md.write_text(f"# 执行结果\n\n{text}\n", encoding="utf-8")
    return str(txt), f"导出完成 文件 {txt.name} 和 {md.name}"
