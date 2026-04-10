# Chorus-WebAI | 网页 AI 协同引擎

[![Python Version](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/driven_by-Playwright-green.svg)](https://playwright.dev/)
[![Status](https://img.shields.io/badge/status-Orchestrator_v2.3-purple.svg)]()
[![Build Status](https://github.com/loopgap/Chorus-WebAI/actions/workflows/ci.yml/badge.svg)](https://github.com/loopgap/Chorus-WebAI/actions/workflows/ci.yml)

**Chorus-WebAI** 是一款工业级的 **"元编排器 (Meta-Orchestrator)"**。它通过独创的自动化协同机制，将 DeepSeek、Kimi、通义千问等主流网页 AI 平台无缝集成，构建起一个高效、低成本的分布式 AI 任务执行网络。

---

## 🚀 快速开始 (Quick Start)

只需三步，即可开启您的 AI 协同之旅：

### 1. 环境准备
确保您的系统已安装 Python 3.13+，然后执行：
```powershell
# 克隆仓库并安装依赖
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. 启动 Web 界面
运行主程序，系统将自动分配一个可用的本地端口并打开浏览器：
```powershell
python web_app.py
```

### 3. 执行首个任务
- 在 **"平台与配置"** 标签页点击 **"🔑 打开登录窗口"** 完成目标平台（如 DeepSeek）的登录。
- 回到 **"执行任务"** 标签页，输入内容并点击 **"立即执行"**。

---

## 🎖️ 核心技术架构 (Architecture)

Chorus-WebAI 采用多层抽象设计，确保在动态网页环境下的高可用性：

### 1. 🎼 多模型接力 (Relay)
通过 `{prev_result}` 占位符实现任务间的上下文流转。您可以编排复杂的业务流：
- **逻辑生成** -> **内容扩写** -> **合规审计**。
- 支持跨平台接力（例如：DeepSeek 总结 -> Kimi 润色）。

### 2. ⚓ 语义锚点定位 (Semantic Anchor)
结合 **A11y 辅助功能树** 与 **视觉模糊特征** 的自愈式定位技术。即使网页 UI 发生结构性变动，引擎也能凭借"操作意图"精准锁定输入框与发送按钮。

### 3. 🔍 视觉证据链 (Visual Evidence Chain)
全链路透明监控。系统自动记录全链路网络请求、DOM 变更以及关键节点的 **"黑匣子截图"**。在任务异常时，为您提供可交互的现场复现报告。

### 4. 🛡️ 故障自愈与本地降级
内置 **线性回退 (Linear Backoff)** 重试算法。当网页端彻底失效时，支持自动降级至 **Ollama (本地 Llama3)** 方案，确保任务队列不中断。

---

## 🆕 新特性 (v2.3)

### 📊 任务追踪系统 (Task Tracker)
- 完整的任务生命周期追踪（创建、执行、完成、失败）
- 任务依赖关系管理
- SQLite 持久化存储
- 详细执行事件日志

### 💾 记忆存储系统 (Memory Store)
- 会话级对话历史存储
- 多会话管理
- 上下文窗口控制
- 语义搜索支持

### 🔄 工作流引擎 (Workflow Engine)
- DAG 工作流定义
- 条件分支与并行执行
- 步骤依赖管理
- 预定义工作流模板

### 📈 监控告警 (Monitoring)
- 性能指标收集
- 系统健康检查
- 告警管理与通知
- 仪表盘数据聚合

---

## 📁 项目结构 (Project Structure)

```
test_mcp/
├── src/                     # 源代码模块
│   ├── core/               # 核心引擎
│   │   ├── config.py       # 配置管理
│   │   ├── browser.py      # 浏览器自动化
│   │   └── exceptions.py   # 异常定义
│   ├── services/           # 业务服务
│   │   ├── task_tracker.py # 任务追踪
│   │   ├── memory_store.py # 记忆存储
│   │   ├── workflow.py     # 工作流引擎
│   │   └── monitor.py      # 监控服务
│   ├── models/             # 数据模型
│   │   ├── task.py         # 任务模型
│   │   ├── session.py      # 会话模型
│   │   └── history.py      # 历史记录
│   └── utils/              # 工具函数
│       ├── cache.py        # 缓存工具
│       └── helpers.py      # 辅助函数
├── main.py                 # CLI 入口
├── web_app.py              # Web UI
├── tests/                  # 测试文件
└── docs/                   # 文档
```

---

## ✅ 交付标准与开发者指南

项目内置了严苛的工业级质量门禁，确保每一行代码的可靠性：

- **自动化测试**：运行 `pytest` 执行覆盖核心操作链路的单元测试。
- **性能门禁 (Performance Gate)**：
  - 模块导入 < 8s（包含 Gradio/Playwright 冷启动）。
  - UI 构建 < 15s。
  - 历史记录反向读取具备 O(1) 内存复杂度。
- **静态检查**：集成 `Ruff` 实时规范审计。

> **详细说明请参阅：[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**

---

## 🧪 运行测试

```powershell
# 运行所有测试
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/test_task_tracker.py -v

# 运行性能检查
python perf_check.py
```

---

*Chorus-WebAI：协作，不止于对话。*
