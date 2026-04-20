"""
UI Assembly Module
"""

from __future__ import annotations

from src.ui.state import PROVIDERS, TEMPLATE_LABEL_TO_KEY, HISTORY_FILTERS
from src.ui.tabs import (
    setup_tab,
    task_tab,
    queue_tab,
    workflow_tab,
    memory_tab,
    monitor_tab,
    diag_tab,
    help_tab,
)


def build_ui():
    import gradio as gr

    provider_labels = [v["label"] for v in PROVIDERS.values()]

    with gr.Blocks(title="ShadowBoard | 个人虚拟董事会 & 零成本 MoE 决策引擎") as demo:
        gr.HTML(
            """
<div class='hero'>
  <div class='hero-title'>ShadowBoard</div>
  <div class='hero-sub'>个人虚拟董事会 & 零成本 MoE 决策引擎：让每一份灵感都经得起多维度的拷问</div>
  <div class='hero-chips'>
    <span class='hero-chip'>🎭 多角色辩论 (Debate)</span>
    <span class='hero-chip'>🎼 跨模型接力 (Relay)</span>
    <span class='hero-chip'>⚓ 语义锚点 (Anchor)</span>
    <span class='hero-chip'>🛡️ 故障自愈 (Recovery)</span>
  </div>
</div>
""".strip()
        )

        with gr.Tabs():
            with gr.Tab("🚀 快速上手"):
                with gr.Row():
                    with gr.Column(scale=2):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>董事会操作向导</div>")
                            guide_markdown = gr.Markdown()
                            with gr.Row():
                                refresh_guide_btn = gr.Button("刷新进度", elem_classes=["action-secondary"])
                                one_click_btn = gr.Button(
                                    "一键初始化董事会环境",
                                    elem_classes=["action-primary"],
                                )
                                shutdown_btn = gr.Button("🛑 安全关闭系统 (Shutdown)", variant="stop")

                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>智能决策特性</div>")
                            gr.Markdown(
                                """
- **多角色辩论**: CMO/CTO/CFO 角色注入
- **任务接力**: `{prev_result}` 跨模型透传
- **自愈定位**: 零成本抗 UI 变动能力
- **本地归纳**: 支持 Ollama 董事长归纳
""".strip()
                            )

            with gr.Tab("⚙️ 平台与配置"):
                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>AI 平台预设</div>")
                            provider_label = gr.Dropdown(
                                provider_labels,
                                value=PROVIDERS["deepseek"]["label"],
                                label="当前激活平台",
                            )
                            apply_provider_btn = gr.Button("应用预设", elem_classes=["action-secondary"])
                            provider_guide = gr.Textbox(
                                label="平台指引",
                                lines=3,
                                elem_classes=["provider-card"],
                            )

                    with gr.Column(scale=2):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>全局参数</div>")
                            with gr.Row():
                                target_url = gr.Textbox(label="入口地址", scale=2)
                                send_mode = gr.Radio(
                                    choices=[("回车", "enter"), ("点击", "button")],
                                    label="交互方式",
                                    scale=1,
                                )
                            with gr.Row():
                                confirm_before_send = gr.Checkbox(label="启用确认发送", value=True)
                                max_retries = gr.Slider(1, 6, 3, label="重试次数")
                                response_timeout = gr.Slider(30, 600, 120, label="超时限制 (s)")
                            save_btn = gr.Button("保存配置", elem_classes=["action-primary"])

                with gr.Row():
                    with gr.Column():
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>浏览器会话控制 (持久化存储)</div>")
                            with gr.Row():
                                open_login_btn = gr.Button(
                                    "🔑 建立远程连接/登录",
                                    elem_classes=["action-secondary"],
                                )
                                finish_login_btn = gr.Button(
                                    "✅ 登录检查与持久化",
                                    elem_classes=["action-secondary"],
                                )
                                smoke_btn = gr.Button("🔥 链路冒烟测试", elem_classes=["action-primary"])
                            with gr.Row():
                                smoke_confirm = gr.Checkbox(label="我已准备好测试")
                                smoke_pause = gr.Slider(0, 15, 3, label="测试前暂停 (s)")
                                setup_status = gr.Textbox(label="系统日志", lines=1)

            with gr.Tab("📝 召开会议 (单次任务)"):
                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>会议议案编排</div>")
                            template_label = gr.Dropdown(
                                list(TEMPLATE_LABEL_TO_KEY.keys()),
                                value="市场分析 (CMO)",
                                label="议案模板 (角色)",
                            )
                            template_help = gr.Markdown()
                            task_input = gr.Textbox(
                                label="输入议案/想法正文",
                                lines=12,
                                placeholder="在此输入需要董事会评估的想法或原始需求...",
                            )
                            input_tip = gr.Markdown()
                            send_confirm = gr.Checkbox(label="确认发送 (建议开启)", value=True)
                            with gr.Row():
                                run_btn = gr.Button("立即执行", elem_classes=["action-primary"])
                                reuse_btn = gr.Button("填入上次内容", elem_classes=["action-secondary"])

                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>执行结果反馈</div>")
                            run_status = gr.Textbox(label="执行进度", lines=1)
                            prompt_preview = gr.Textbox(label="提示词预览", lines=2, visible=False)
                            response_box = gr.Textbox(label="AI 响应内容", lines=18)
                            with gr.Row():
                                export_btn = gr.Button(
                                    "导出 会议纪要 (MD)",
                                    elem_classes=["action-secondary"],
                                )
                                export_file = gr.File(label="点击下载", interactive=False)
                                export_status = gr.Textbox(label="导出状态", lines=1, visible=False)

            with gr.Tab("📊 链式会议 (队列)"):
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>添加链式辩论环节</div>")
                    with gr.Row():
                        q_template = gr.Dropdown(
                            list(TEMPLATE_LABEL_TO_KEY.keys()),
                            value="市场分析 (CMO)",
                            label="角色环节",
                        )
                        q_input = gr.Textbox(
                            label="针对性指令 (支持 {prev_result} 引用前序环节)",
                            scale=3,
                        )
                        q_add_btn = gr.Button("加入议程", elem_classes=["action-primary"], scale=1)
                        q_add_status = gr.Textbox(label="添加结果", lines=1, visible=False)

                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>议程队列监控</div>")
                    with gr.Row():
                        q_run_btn = gr.Button("▶ 执行首个环节", elem_classes=["action-primary"])
                        q_clear_btn = gr.Button("🗑️ 清空议程", elem_classes=["action-secondary"])
                        q_refresh_btn = gr.Button("🔄 刷新议程状态", elem_classes=["action-secondary"])
                    q_run_status = gr.Textbox(label="议程运行状态", lines=1)
                    q_grid = gr.Dataframe(
                        headers=["ID", "添加时间", "环节", "预览", "状态", "结果"],
                        interactive=False,
                    )

            with gr.Tab("🔄 智能工作流"):
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>内置董事会工作流模板</div>")
                    with gr.Row():
                        workflow_select = gr.Dropdown(
                            choices=workflow_tab.list_workflows(),
                            label="选择智能工作流",
                        )
                        workflow_info_btn = gr.Button("查看议程详情", elem_classes=["action-secondary"])
                    workflow_details = gr.Textbox(label="工作流详情", lines=6, interactive=False)

                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>自动执行完整会议议程</div>")
                    workflow_input = gr.Textbox(
                        label="输入核心议案",
                        lines=4,
                        placeholder="输入需要各部门协作的完整议案内容...",
                    )
                    with gr.Row():
                        workflow_run_btn = gr.Button("▶ 一键召开董事会", elem_classes=["action-primary"])
                        workflow_status = gr.Textbox(label="议程状态", lines=1)
                    workflow_result = gr.Textbox(label="最终决策报告/汇总", lines=10)

            with gr.Tab("💾 会议纪要 (记忆)") as memory_tab_item:
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>董事会历史会话</div>")
                    with gr.Row():
                        session_title = gr.Textbox(label="新会议标题", scale=2)
                        create_session_btn = gr.Button("开启新议程", elem_classes=["action-primary"])
                    session_list = gr.Dataframe(
                        headers=["ID", "标题", "发言次数", "状态", "更新时间"],
                        interactive=False,
                    )
                    with gr.Row():
                        refresh_sessions_btn = gr.Button("刷新纪要列表", elem_classes=["action-secondary"])
                        switch_session_input = gr.Textbox(label="切换到历史议程ID")
                        switch_session_btn = gr.Button("切换议程", elem_classes=["action-secondary"])

                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>完整发言记录</div>")
                    session_context_btn = gr.Button("查看发言记录", elem_classes=["action-secondary"])
                    session_context = gr.Textbox(label="董事会对话历史", lines=8, interactive=False)
                    memory_stats_box = gr.Textbox(label="存储统计", lines=3)

            with gr.Tab("📈 董事会报表") as monitor_tab_item:
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>决策效率监控</div>")
                    with gr.Row():
                        dashboard_refresh_btn = gr.Button("刷新数据报表", elem_classes=["action-primary"])
                        task_stats_btn = gr.Button("执行频率统计", elem_classes=["action-secondary"])
                    dashboard_data = gr.Textbox(label="决策仪表盘数据", lines=15)

                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>系统运行指标</div>")
                    with gr.Row():
                        metrics_health_btn = gr.Button("组件健康度", elem_classes=["action-secondary"])
                        metrics_tasks_btn = gr.Button("成功率统计", elem_classes=["action-secondary"])
                    metrics_display = gr.Textbox(label="指标数据", lines=10)

        with gr.Tab("🛠️ 诊断与日志") as diag_tab_item:
            with gr.Group(elem_classes=["section-card"]):
                with gr.Row():
                    history_filter = gr.Radio(choices=HISTORY_FILTERS, value="全部", label="结果过滤")
                    refresh_history_btn = gr.Button("同步物理历史", elem_classes=["action-secondary"])
                history_grid = gr.Dataframe(interactive=False)
                with gr.Row():
                    health_btn = gr.Button("系统底层体检", elem_classes=["action-secondary"])
                    error_btn = gr.Button("底层错误追溯", elem_classes=["action-secondary"])
                    clear_history_btn = gr.Button("清空物理记录", elem_classes=["action-secondary"])
                diag_box = gr.Textbox(label="底层控制台输出", lines=10, elem_classes=["provider-card"])

        with gr.Tab("帮助文档"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>接口文档与开发者指引</div>")
                api_doc_box = gr.Textbox(label="接口说明内容", lines=18)
                with gr.Row():
                    refresh_doc_btn = gr.Button("刷新接口文档", elem_classes=["action-secondary"])
                    export_doc_btn = gr.Button("导出接口文档", elem_classes=["action-primary"])
                api_doc_file = gr.File(label="接口文档下载", interactive=False)
                api_doc_status = gr.Textbox(label="文档生成状态", lines=2)

        # --- Setup Tab Events ---
        apply_provider_btn.click(
            fn=setup_tab.apply_provider,
            inputs=[provider_label],
            outputs=[target_url, send_mode, provider_guide, setup_status],
        )
        save_btn.click(
            fn=setup_tab.save_config_from_form,
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
        open_login_btn.click(fn=setup_tab.open_login_browser, outputs=[setup_status, guide_markdown])
        finish_login_btn.click(fn=setup_tab.finish_login_check, outputs=[setup_status, guide_markdown])
        smoke_btn.click(
            fn=setup_tab.run_smoke_test,
            inputs=[smoke_confirm, smoke_pause],
            outputs=[setup_status, guide_markdown],
        )
        one_click_btn.click(fn=setup_tab.one_click_prepare, outputs=[setup_status, guide_markdown])
        shutdown_btn.click(fn=setup_tab.shutdown_system, outputs=[setup_status])
        refresh_guide_btn.click(fn=setup_tab.build_guide_markdown, outputs=[guide_markdown])

        # --- Task Tab Events ---
        template_label.change(fn=task_tab.template_help, inputs=[template_label], outputs=[template_help])
        task_input.change(fn=task_tab.input_tip, inputs=[task_input], outputs=[input_tip])
        reuse_btn.click(fn=task_tab.reuse_last_input, outputs=[template_label, task_input])
        run_btn.click(
            fn=task_tab.run_task,
            inputs=[template_label, task_input, send_confirm],
            outputs=[run_status, prompt_preview, response_box, input_tip, history_grid],
        )
        export_btn.click(
            fn=task_tab.export_response,
            inputs=[response_box],
            outputs=[export_file, export_status],
        )

        # --- Queue Tab Events ---
        q_add_btn.click(
            fn=queue_tab.add_to_queue,
            inputs=[q_template, q_input],
            outputs=[q_add_status],
        )
        q_refresh_btn.click(fn=queue_tab.render_queue_table, outputs=[q_grid])
        q_clear_btn.click(fn=queue_tab.clear_queue, outputs=[q_run_status, q_grid])
        q_run_btn.click(fn=queue_tab.process_queue_once, outputs=[q_run_status, q_grid])

        # --- Workflow Tab Events ---
        workflow_info_btn.click(
            fn=workflow_tab.get_workflow_details,
            inputs=[workflow_select],
            outputs=[workflow_details],
        )
        workflow_run_btn.click(
            fn=workflow_tab.execute_workflow,
            inputs=[workflow_select, workflow_input],
            outputs=[workflow_status, workflow_result],
        )

        # --- Memory Tab Events ---
        create_session_btn.click(
            fn=memory_tab.create_session,
            inputs=[session_title],
            outputs=[session_context, session_list],
        )
        refresh_sessions_btn.click(fn=memory_tab.list_sessions, outputs=[session_list])
        switch_session_btn.click(
            fn=memory_tab.switch_session,
            inputs=[switch_session_input],
            outputs=[session_context, session_context],
        )
        session_context_btn.click(
            fn=memory_tab.get_session_context,
            inputs=[switch_session_input],
            outputs=[session_context],
        )

        # --- Monitor Tab Events ---
        dashboard_refresh_btn.click(fn=monitor_tab.get_dashboard_data, outputs=[dashboard_data])
        task_stats_btn.click(fn=monitor_tab.get_task_statistics, outputs=[dashboard_data])
        metrics_health_btn.click(fn=monitor_tab.get_dashboard_data, outputs=[metrics_display])
        metrics_tasks_btn.click(fn=monitor_tab.get_task_statistics, outputs=[metrics_display])

        # --- Diag Tab Events ---
        refresh_history_btn.click(fn=diag_tab.history_table, inputs=[history_filter], outputs=[history_grid])
        history_filter.change(fn=diag_tab.history_table, inputs=[history_filter], outputs=[history_grid])
        clear_history_btn.click(fn=diag_tab.clear_history, outputs=[diag_box, history_grid])
        health_btn.click(fn=diag_tab.health_check, outputs=[diag_box])
        error_btn.click(fn=diag_tab.latest_errors, outputs=[diag_box])

        # --- Help Tab Events ---
        refresh_doc_btn.click(fn=help_tab.build_api_doc_text, outputs=[api_doc_box])
        export_doc_btn.click(fn=help_tab.export_api_doc, outputs=[api_doc_file, api_doc_status])

        # --- Global Load Events (Lazy Loading) ---
        demo.load(
            fn=setup_tab.load_config_for_form,
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

        # Tab selection based lazy loading
        diag_tab_item.select(fn=diag_tab.history_table, inputs=[history_filter], outputs=[history_grid])
        memory_tab_item.select(fn=memory_tab.list_sessions, outputs=[session_list])
        memory_tab_item.select(fn=memory_tab.get_memory_statistics, outputs=[memory_stats_box])
        monitor_tab_item.select(fn=monitor_tab.get_dashboard_data, outputs=[dashboard_data])
        
        # Keep queue grid as it's small or needed for status
        demo.load(fn=queue_tab.render_queue_table, outputs=[q_grid])

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
