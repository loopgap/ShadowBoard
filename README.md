# Chorus-WebAI | 网页 AI 协同引擎

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/driven_by-Playwright-green.svg)](https://playwright.dev/)
[![Status](https://img.shields.io/badge/status-Orchestrator_v2-purple.svg)]()

**Chorus-WebAI** 是一款定位为 **“元编排器 (Meta-Orchestrator)”** 的网页 AI 自动化引擎。它不仅打破了网页 AI 的孤岛状态，更通过工程化的协同机制，让 DeepSeek、Kimi、通义千问等平台变身为您的分布式计算节点。

## 🎖️ 核心差异化：超越脚本的工程设计

Chorus-WebAI 致力于解决 Web 自动化中“脆弱”与“黑盒”的痛点：

### 1. 🎼 多模型接力 (Multi-Model Relay)
不同于竞品的单次对话，Chorus 支持任务间的上下文流转。您可以在队列中编排如下流程：
- **节点 1 (DeepSeek)**: 生成代码逻辑大纲
- **节点 2 (Kimi)**: 对大纲进行文档化扩写（通过 `{prev_result}` 自动引用节点 1 的输出）
- **节点 3 (通义千问)**: 进行最终的合规性检查

### 2. ⚓ 语义锚点定位 (Semantic Anchor)
摒弃了易失效的硬编码选择器。我们的 **“自愈定位引擎”** 结合了 A11y 语义树和模糊视觉特征，即使网页 UI 改版（如类名混淆），指挥官也能精准找到输入窗口。

### 3. 🔍 交互式证据链 (Visual Evidence Chain)
执行即审计。系统自动记录全链路网络请求与 DOM 变更，失败时自动生成带截图的 **“黑匣子日志”**，让自动化执行过程不再是黑盒。

### 4. 💰 零 API 经济性
在 API 调用成本日益增长的今天，Chorus-WebAI 提供了极致的成本效益。无需 API Key，通过人类直觉级的自动化，榨干网页版 AI 的每一分性能。

## ✅ 交付标准与质量保障 (Delivery Checklist)

为了确保 Chorus-WebAI 的工业级可靠性，我们遵循严苛的交付核对流程：

### 1. 功能验证
- [x] **多平台适配**：DeepSeek, Kimi, 通义, 豆包, 智谱, 文心全量通过。
- [x] **持久化 Session**：浏览器 Profile 自动漫游与登录态持久化。
- [x] **冒烟测试协议**：内置 READY 指令校验，确保执行链路通畅。
- [x] **批量任务引擎**：支持跨任务结果传递与队列自动顺序执行。

### 2. 交互与体验
- [x] **响应式 UI**：基于 Gradio 的看板，适配多终端与深浅色模式。
- [x] **引导式进度**：实时刷新新手向导，大幅降低上手门槛。
- [x] **导出生态**：一键生成 .txt / .md 结果报告及交互式接口文档。

### 3. 工程质量
- [x] **代码质量**：Ruff 静态检查全量通过，代码风格严谨、可读性强。
- [x] **测试覆盖**：28+ 项自动化单元测试，覆盖核心操作链路。
- [x] **性能极限**：模块导入 < 2s，UI 构建限时 12s 以内，历史查询 O(1) 内存占用。

### 4. 交付完整性
- [x] **环境锁定**：提供完整的 `requirements.txt` 与环境配置指引。
- [x] **自愈结构**：状态目录 `.semi_agent/` 具备自动初始化与损坏恢复能力。

---

*Chorus-WebAI：让每一个网页 AI 平台都成为您的生产力突触。*

