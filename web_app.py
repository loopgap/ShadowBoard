from __future__ import annotations

import asyncio
import socket
import sys

import gradio as gr
import main as core
from src.core.templates import (
    EXAMPLE_INPUTS,
    PROVIDERS,
)
from src.ui.components.selectors import (
    CUSTOM_CSS,
    HISTORY_FILTERS,
    PROVIDER_LABELS,
    TEMPLATE_LABELS,
    get_faq_markdown,
    get_hero_html,
    get_quick_actions_html,
)
from src.ui.handlers.events import (
    _apply_provider,
    _build_api_doc_text,
    _build_guide_markdown,
    _clear_history,
    _export_api_doc,
    _export_response,
    _finish_login_check,
    _health_check,
    _history_table,
    _input_tip,
    _latest_errors,
    _load_config_for_form,
    _one_click_prepare,
    _open_login_browser,
    _reuse_last_input,
    _run_task,
    _run_smoke_test,
    _save_config_from_form,
    _template_help,
)
from src.services.queue import (
    add_to_queue,
    clear_queue,
    process_queue_once,
    render_queue_table,
)
from src.core.dependencies import initialize_services

EXPORT_DIR = core.STATE_DIR / "exports"
DOCS_DIR = core.STATE_DIR / "docs"


def _ensure_dirs() -> None:
    core.ensure_state()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)


def _pick_available_port(start: int = 7860, end: int = 7875) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"{start} 到 {end} 端口均被占用 请先关闭占用进程")


def build_ui() -> "gr.Blocks":
    """Build the Gradio UI layout."""
    with gr.Blocks(title="网页 AI 半自动助手") as demo:
        gr.HTML(get_hero_html())

        with gr.Tab("新手向导"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>快速开始</div>")
                guide_markdown = gr.Markdown()
                with gr.Row():
                    refresh_guide_btn = gr.Button("刷新进度建议", elem_classes=["action-secondary"])
                    one_click_btn = gr.Button("一键准备", elem_classes=["action-primary"])

            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown(get_faq_markdown())

        with gr.Tab("平台与参数"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>平台选择</div>")
                with gr.Row():
                    provider_label = gr.Dropdown(
                        PROVIDER_LABELS,
                        value=PROVIDERS["deepseek"]["label"],
                        label="目标平台",
                    )
                    apply_provider_btn = gr.Button("应用平台预设", elem_classes=["action-primary"])
                provider_guide = gr.Textbox(label="平台引导", lines=4, elem_classes=["provider-card"])

            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>连接与执行参数</div>")
                with gr.Row():
                    target_url = gr.Textbox(label="目标网址", value="https://chat.deepseek.com/", scale=2)
                    send_mode = gr.Radio(
                        choices=[("回车发送", "enter"), ("点击按钮发送", "button")],
                        value="enter",
                        label="发送方式",
                        scale=1,
                    )
                with gr.Row():
                    confirm_before_send = gr.Checkbox(value=True, label="执行前需要确认发送")
                    max_retries = gr.Slider(minimum=1, maximum=6, step=1, value=3, label="失败自动重试次数")
                    response_timeout = gr.Slider(
                        minimum=30,
                        maximum=600,
                        step=10,
                        value=120,
                        label="响应超时秒数",
                    )

                save_btn = gr.Button("保存参数", elem_classes=["action-primary"])
                setup_status = gr.Textbox(label="状态反馈", lines=4)

                with gr.Row():
                    open_login_btn = gr.Button("打开登录浏览器", elem_classes=["action-secondary"])
                    finish_login_btn = gr.Button("登录完成检查", elem_classes=["action-secondary"])
                    smoke_btn = gr.Button("执行冒烟测试", elem_classes=["action-primary"])

                with gr.Row():
                    smoke_confirm = gr.Checkbox(value=False, label="我确认开始冒烟测试")
                    smoke_pause = gr.Slider(minimum=0, maximum=15, step=1, value=3, label="冒烟测试暂停秒数")

        with gr.Tab("执行任务"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>任务输入</div>")
                template_label = gr.Dropdown(TEMPLATE_LABELS, value="摘要总结", label="任务模板")
                template_help = gr.Markdown(_template_help("摘要总结"))
                task_input = gr.Textbox(
                    label="任务输入",
                    lines=10,
                    placeholder="示例 请总结这段内容 并给出三条下一步建议",
                )
                input_tip = gr.Markdown("输入提示 请粘贴正文或直接写需求")
                send_confirm = gr.Checkbox(value=True, label="我确认发送本次任务")
                with gr.Row():
                    run_btn = gr.Button("开始执行", elem_classes=["action-primary"])
                    reuse_btn = gr.Button("复用上次输入", elem_classes=["action-secondary"])
                gr.Examples(
                    examples=EXAMPLE_INPUTS,
                    inputs=[template_label, task_input],
                    label="示例输入 点击自动填充",
                )

            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>执行结果</div>")
                run_status = gr.Textbox(label="执行状态", lines=2)
                prompt_preview = gr.Textbox(label="生成提示词预览", lines=8)
                response_box = gr.Textbox(label="AI 返回结果", lines=16)
                with gr.Row():
                    export_btn = gr.Button("导出结果", elem_classes=["action-secondary"])
                    export_file = gr.File(label="下载文件", interactive=False)
                    export_status = gr.Textbox(label="导出状态", lines=2)

        with gr.Tab("历史与诊断"):
            with gr.Group(elem_classes=["section-card"]):
                with gr.Row():
                    history_filter = gr.Radio(
                        choices=HISTORY_FILTERS,
                        value="全部",
                        label="历史筛选",
                        elem_id="history-filter",
                    )
                    refresh_history_btn = gr.Button("刷新历史", elem_classes=["action-secondary"])

                history_grid = gr.Dataframe(
                    headers=["时间", "模板", "耗时秒", "返回字数", "结果", "错误摘要"],
                    datatype=["str", "str", "number", "number", "str", "str"],
                    row_count=15,
                    column_count=(6, "fixed"),
                    wrap=True,
                    interactive=False,
                    elem_id="history-table",
                )

                with gr.Row():
                    clear_confirm = gr.Checkbox(value=False, label="确认清空历史")
                    clear_history_btn = gr.Button("清空历史", elem_classes=["action-secondary"])
                    health_btn = gr.Button("健康检查", elem_classes=["action-secondary"])
                    error_btn = gr.Button("查看最近错误日志", elem_classes=["action-secondary"])

                diag_box = gr.Textbox(label="诊断输出", lines=14)

        with gr.Tab("批量队列"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>添加任务到队列</div>")
                q_template = gr.Dropdown(TEMPLATE_LABELS, value="摘要总结", label="任务模板")
                q_input = gr.Textbox(label="任务输入", lines=3)
                q_add_btn = gr.Button("加入队列", elem_classes=["action-secondary"])
                q_add_status = gr.Textbox(label="添加状态", lines=1)

            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>队列展示与执行</div>")
                with gr.Row():
                    q_refresh_btn = gr.Button("刷新队列", elem_classes=["action-secondary"])
                    q_clear_btn = gr.Button("清空队列", elem_classes=["action-secondary"])
                    q_run_btn = gr.Button("执行队列首个任务", elem_classes=["action-primary"])

                q_run_status = gr.Textbox(label="执行状态", lines=1)
                q_grid = gr.Dataframe(
                    headers=["ID", "添加时间", "模板", "内容预览", "状态", "结果摘要"],
                    datatype=["str", "str", "str", "str", "str", "str"],
                    row_count=10,
                    interactive=False,
                )

        with gr.Tab("帮助文档"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>接口文档与使用指引</div>")
                api_doc_box = gr.Textbox(label="接口文档内容", lines=18)
                with gr.Row():
                    refresh_doc_btn = gr.Button("刷新接口文档", elem_classes=["action-secondary"])
                    export_doc_btn = gr.Button("导出接口文档", elem_classes=["action-primary"])
                api_doc_file = gr.File(label="接口文档下载", interactive=False)
                api_doc_status = gr.Textbox(label="文档状态", lines=2)

        # Bind event handlers
        apply_provider_btn.click(
            fn=_apply_provider,
            inputs=[provider_label],
            outputs=[target_url, send_mode, provider_guide, setup_status],
        )

        save_btn.click(
            fn=_save_config_from_form,
            inputs=[
                provider_label,
                target_url,
                send_mode,
                confirm_before_send,
                max_retries,
                response_timeout,
            ],
            outputs=[setup_status, guide_markdown, provider_guide],
        )

        open_login_btn.click(fn=_open_login_browser, outputs=[setup_status, guide_markdown])
        finish_login_btn.click(fn=_finish_login_check, outputs=[setup_status, guide_markdown])
        smoke_btn.click(
            fn=_run_smoke_test,
            inputs=[smoke_confirm, smoke_pause],
            outputs=[setup_status, guide_markdown],
        )
        one_click_btn.click(fn=_one_click_prepare, outputs=[setup_status, guide_markdown])

        template_label.change(fn=_template_help, inputs=[template_label], outputs=[template_help])
        task_input.change(fn=_input_tip, inputs=[task_input], outputs=[input_tip])
        reuse_btn.click(fn=_reuse_last_input, outputs=[template_label, task_input])

        run_btn.click(
            fn=_run_task,
            inputs=[template_label, task_input, send_confirm],
            outputs=[run_status, prompt_preview, response_box, input_tip, history_grid],
        )
        export_btn.click(
            fn=_export_response,
            inputs=[response_box],
            outputs=[export_file, export_status],
        )

        refresh_guide_btn.click(fn=_build_guide_markdown, outputs=[guide_markdown])
        refresh_history_btn.click(fn=_history_table, inputs=[history_filter], outputs=[history_grid])
        history_filter.change(fn=_history_table, inputs=[history_filter], outputs=[history_grid])
        clear_history_btn.click(fn=_clear_history, inputs=[clear_confirm], outputs=[diag_box, history_grid])
        health_btn.click(fn=_health_check, outputs=[diag_box])
        error_btn.click(fn=_latest_errors, outputs=[diag_box])

        q_add_btn.click(fn=add_to_queue, inputs=[q_template, q_input], outputs=[q_add_status])
        q_refresh_btn.click(fn=render_queue_table, outputs=[q_grid])
        q_clear_btn.click(fn=clear_queue, outputs=[q_run_status, q_grid])
        q_run_btn.click(fn=process_queue_once, outputs=[q_run_status, q_grid])
        demo.load(fn=render_queue_table, outputs=[q_grid])

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

        gr.HTML(get_quick_actions_html())

    return demo


def main() -> None:
    try:
        _ensure_dirs()
        # Initialize async services (DB, etc.)
        asyncio.run(initialize_services())
        
        app = build_ui()
        app.queue(default_concurrency_limit=1)
        port = _pick_available_port(7860, 7875)
        print(f"Starting ShadowBoard UI on http://127.0.0.1:{port}")
        app.launch(
            server_name="127.0.0.1",
            server_port=port,
            inbrowser=True,
            theme=gr.themes.Soft(),
            css=CUSTOM_CSS,
        )
    except KeyboardInterrupt:
        print("Shutdown requested by user")
    except Exception as e:
        print(f"ERROR: Failed to start application: {e}", file=sys.stderr)
        print("Please check if port 7860 is available or another instance is running.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
