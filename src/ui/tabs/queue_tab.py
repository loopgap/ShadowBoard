"""
Queue Tab Logic and Event Handlers
"""

from __future__ import annotations

import time
import copy
from datetime import datetime
from typing import Any, List

import main as core
from src.core.dependencies import get_task_tracker, get_monitor
from src.ui.state import (
    TASK_QUEUE, QueueItem, get_queue_lock, TEMPLATE_LABEL_TO_KEY
)

async def add_to_queue(template_label: str, user_input: str) -> str:
    raw_input = (user_input or "").strip()
    if not raw_input:
        return "提示: 任务内容为空，未加入队列"
    async with get_queue_lock():
        item = QueueItem(template_label=template_label, user_input=raw_input)
        TASK_QUEUE.append(item)
        
        # Create task in tracker
        tracker = get_task_tracker()
        template_key = TEMPLATE_LABEL_TO_KEY.get(template_label, "custom")
        task = await tracker.create_task(
            template_key=template_key,
            user_input=raw_input,
            prompt=core.build_prompt(template_key, raw_input),
        )
        item.task_id = task.id
        
    return f"已成功加入队列 (ID: {item.id}, TaskID: {task.id})，当前队列长度: {len(TASK_QUEUE)}"

def render_queue_table() -> List[List[Any]]:
    # 修复：使用 list(TASK_QUEUE) 创建快照后再进行迭代，以防止多线程/异步环境下崩溃
    return [[item.id, item.added_at, item.template_label, item.user_input[:20], item.status, item.result[:30]] for item in list(TASK_QUEUE)]

async def process_queue_once():
    tracker = get_task_tracker()
    monitor = get_monitor()
    
    async with get_queue_lock():
        pending = [item for item in TASK_QUEUE if item.status == "等待中"]
        if not pending:
            return "队列中没有等待执行的任务", render_queue_table()
        
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
    return f"任务 {target.id} 已处理完毕 ({target.status})", render_queue_table()

async def clear_queue():
    async with get_queue_lock():
        TASK_QUEUE.clear()
    return "队列已清空", render_queue_table()
