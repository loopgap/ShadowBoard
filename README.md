# ShadowBoard | 个人虚拟董事会 & 零成本 MoE 决策引擎

[![Python Version](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/driven_by-Playwright-green.svg)](https://playwright.dev/)
[![Status](https://img.shields.io/badge/status-Boardroom_v3.0-gold.svg)]()

**ShadowBoard** 是一款为独立开发者、创业者和创作者打造的 **"个人虚拟董事会"**。

它利用独创的自动化协同机制，将 DeepSeek、Kimi、通义千问等主流网页 AI 平台无缝串联，构建起一个零 API 成本的多角色混合专家系统 (Mixture-of-Experts)。只需输入一个想法或议案，系统即可自动调度多位 "AI 董事" 进行深度辩论与交叉验证，最终为您输出高质量的综合决策报告。

---

## 🌟 核心理念：协作，不止于对话

在面对复杂决策时，单一 AI 的回答往往存在局限性。**ShadowBoard** 通过以下方式解决这一问题：

1. **🎭 角色化辩论 (Role-based Debate)**：内置 CMO (市场)、CTO (技术)、CFO (财务)、Risk Manager (风险) 等角色。每个角色由最擅长该领域的 Web AI 平台担任。
2. **🎼 任务接力 (Context Relay)**：通过 DAG 工作流，将一个 AI 的输出作为另一个 AI 的背景上下文，实现深度逻辑下钻。
3. **⚖️ 自动聚合 (The Chairman)**：所有 AI 董事发表意见后，由本地 Llama3 或指定的汇总模型进行归纳，指出共识、分歧与最终行动建议。
4. **💰 零成本运作**：完全基于 Web 自动化技术，无需昂贵的 API Key，榨干免费额度的最大生产力。

---

## 🚀 快速开始 (Quick Start)

### 1. 环境准备
确保您的系统已安装 Python 3.9+，然后执行：
```powershell
# 1. 安装项目及依赖
pip install -e .

# 2. 安装 Playwright 浏览器内核
playwright install chromium
```

### 2. 启动虚拟会议室
运行以下指令启动 Web 界面：
```powershell
python web_app.py
```

### 3. 召开您的首个董事会
- 在 **"配置董事会"** 标签页完成目标平台（如 DeepSeek, Kimi）的登录。
- 在 **"召开会议"** 标签页，输入您的决策议案并点击 **"启动流程"**。

---

## 🛠️ 技术架构 (Architecture)

ShadowBoard 采用工业级多层抽象设计：

- **⚓ 语义锚点定位**：结合 A11y 辅助功能树与视觉模糊特征，即使网页 UI 变动，引擎也能自愈定位。
- **🔍 视觉证据链**：全链路透明监控。系统自动记录网络请求、DOM 变更及关键节点的 "黑匣子截图"。
- **🛡️ 故障自愈与降级**：内置线性回退重试算法。当网页端失效时，自动降级至本地 Ollama 方案。
- **📈 任务追踪系统**：完整的任务生命周期管理，支持 SQLite 持久化与执行事件日志。
- **⚡ 引擎优化与安全**：全量类型安全增强与资源自动管理。引入了 UI 任务队列迭代快照机制防止异步崩溃，并实现了浏览器进程自动清理与增强型导航自愈策略，确保在任何故障路径下均不留存僵尸进程。

---

## 📁 项目结构 (Project Structure)

```
shadowboard/
├── src/                     # 源代码模块
│   ├── core/               # 自动化引擎
│   ├── services/           # 董事会服务 (工作流、任务追踪、记忆)
│   ├── models/             # 数据模型
│   └── utils/              # 工具函数
├── main.py                 # CLI 入口
├── web_app.py              # 虚拟会议室 Web UI
├── tests/                  # 测试文件
└── docs/                   # 项目维基 (Wiki)
```

---

## 📚 更多文档

详细的使用说明、开发指南与 API 文档，请参阅我们的 **[项目维基 (WIKI)](docs/Home.md)**。

---

## ✅ 交付标准

项目内置严苛的质量门禁：
- **自动化测试**：通过 `pytest` 覆盖核心操作链路。
- **性能门禁**：UI 构建 < 15s，历史记录反向读取 O(1)。
- **规范审计**：集成 `Ruff` 实时规范检查。

---

*ShadowBoard：让每一份灵感，都经得起多维度的拷问。*
