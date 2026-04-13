"""
Help Tab Logic and Event Handlers
"""

from __future__ import annotations

from datetime import datetime
from typing import Tuple

from src.ui.state import PROVIDERS, DOCS_DIR

def build_api_doc_text() -> str:
    lines = [
        "ShadowBoard | 个人虚拟董事会 & 零成本 MoE 决策引擎 v3.0 接口文档",
        "",
        "=== 核心产品特性 ===",
        "1. 🎭 角色化辩论 (Debate)：内置 CMO, CTO, CFO, Risk Manager 等专家角色 Prompt",
        "2. 🎼 跨模型接力 (Relay)：支持使用 {prev_result} 自动注入前序董事会环节输出",
        "3. ⚖️ 自动聚合 (Synthesis)：支持由本地模型或指定节点担任董事长进行最终归纳",
        "4. 🛡️ 故障自愈 (Recovery)：线性回退重试 + 本地 Ollama 降级保障议程不中断",
        "",
        "=== v3.0 重构特性 ===",
        "5. 任务追踪 (TaskTracker)：完整生命周期管理、事件监听、依赖解析",
        "6. 会议纪要 (MemoryStore)：多会话管理、上下文窗口、消息语义搜索",
        "7. 智能工作流 (Workflow)：内置 Startup_Review 等 4 套标准会议议程",
        "8. 决策报表 (Monitor)：决策效率指标收集、系统健康度、告警管理",
        "",
        "=== 董事会功能列表 ===",
        "",
        "-- 平台与配置 --",
        "1. 应用平台预设 - 切换目标 AI 董事会席位 (DeepSeek/Kimi/Qwen)",
        "2. 保存参数 - 持久化配置到 config.json",
        "3. 建立远程连接 - 启动持久化浏览器会话",
        "4. 登录状态验证 - 验证 Web AI 登录状态",
        "5. 执行冒烟测试 - 发送测试消息验证链路连通性",
        "6. 一键准备 - 自动化初始化董事会环境",
        "",
        "-- 召开会议 --",
        "7. 立即执行 - 执行单个董事环节并等待响应",
        "8. 复用议案 - 快速填充历史输入内容",
        "9. 导出纪要 - 保存 AI 响应为 Markdown 格式",
        "",
        "-- 链式会议 (队列) --",
        "10. 加入议程 - 添加任务到批量辩论队列",
        "11. 执行首个环节 - 处理队列首个董事会环节",
        "12. 清空议程 - 移除所有待处理环节",
        "",
        "-- 智能工作流 --",
        "13. 查看议程详情 - 显示步骤角色和逻辑依赖",
        "14. 一键召开董事会 - 运行完整预设工作流",
        "",
        "-- 会议纪要 --",
        "15. 开启新议程 - 新建对话会话",
        "16. 切换议程 - 切换到指定历史纪要",
        "17. 查看发言记录 - 显示会话详细历史内容",
        "",
        "-- 决策报表 --",
        "18. 刷新仪表盘 - 获取系统运行状态",
        "19. 执行统计 - 查看各角色执行频率与耗时",
        "20. 组件健康度 - 检测自动化引擎各组件状态",
        "",
        "-- 历史与诊断 --",
        "21. 同步物理历史 - 从本地磁盘刷新记录",
        "22. 清空物理记录 - 彻底清除本地任务日志",
        "23. 底层体检 - 完整系统链路状态诊断",
        "24. 错误追溯 - 显示最近 5 条异常现场日志",
        "",
        "=== platform 支持席位 ===",
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


def export_api_doc() -> Tuple[str, str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DOCS_DIR / f"api_doc_{ts}.md"
    path.write_text(build_api_doc_text(), encoding="utf-8")
    return str(path), f"接口文档已生成 {path.name}"
