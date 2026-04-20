# 系统架构总览

本文档基于当前源码结构整理，目的是快速说明各层职责与调用关系。

---

## 1. 分层结构

```text
入口层
  main.py         # CLI/自动化执行入口
  web_app.py      # Web 界面入口

应用层
  src/ui/         # Gradio 视图与交互逻辑
  src/services/   # 任务、工作流、记忆、监控

领域层
  src/models/     # Task / Session / History 数据模型

基础设施层
  src/core/       # 配置、异常、浏览器、依赖注入
  src/utils/      # 模板与通用工具
```

## 2. 核心模块说明

### 2.1 `src/core`

- `config.py`: 全局配置管理（ConfigManager 单例，支持环境变量覆盖、Provider 配置、动态监听）。
- `session.py`: 登录会话状态与最后输入状态管理（SessionManager 单例）。
- `exceptions.py`: 统一异常体系（ConfigError、BrowserError、TaskError）。
- `browser.py`: Playwright 浏览器会话管理。
- `dependencies.py`: 服务单例注册与获取入口。

### 2.2 `src/services`

- `task_tracker.py`: 基于 `aiosqlite` 的异步任务生命周期管理与事件持久化。
- `workflow.py`: DAG 工作流编排与执行。
- `memory_store.py`: 基于 `aiosqlite` 的异步会话记忆管理与消息持久化。
- `monitor.py`: 基于 `aiosqlite` 的异步指标收集、健康检查与告警。

### 2.3 `src/ui`

- `app.py`: Gradio 页面装配（多个功能 Tab）。
- `tabs/`: 每个标签页对应一个模块，解耦交互逻辑。
- `state.py`: UI 共享状态与配置映射。

### 2.4 `src/models`

- `task.py`: 任务状态机与事件。
- `session.py`: 会话与消息模型。
- `history.py`: 历史记录模型。

## 3. 关键调用链

### 3.1 Web 模式

1. `web_app.py` 启动 Gradio。
2. `src/ui/app.py` 组装页面与事件绑定。
3. UI 事件通过 `src/core/dependencies.py` 获取服务。
4. 服务层写入 SQLite 并返回结果到 UI。

### 3.2 工作流执行

1. UI 或 CLI 提交议案。
2. `WorkflowEngine` 根据 DAG 执行步骤。
3. 每个步骤转为 Task 由 `TaskTracker` 跟踪。
4. 执行结果进入 `MemoryStore`，并由 `Monitor` 记录指标。

## 4. 持久化与状态

- `.semi_agent/config.json`: 运行配置。
- `.semi_agent/*.db`: 任务、记忆、监控相关 SQLite 数据。
- `.semi_agent/history.jsonl`: 历史记录。

## 5. Gradio UI 懒加载与性能优化

Web UI (`web_app.py`) 采用多级懒加载优化：
- **模块级懒加载**: `gradio` 模块在 `build_ui()` 函数内部导入，减少初始 import 耗时。
- **组件级懒加载**: 采用 `Tab.select()` 事件触发模式。只有当用户点击特定标签页（如“会议纪要”、“董事会报表”、“诊断与日志”）时，系统才会从 SQLite 加载对应数据。
- **资源级管控**: 强化版 `BrowserPool` 使用单一全局 Playwright 实例，并在进程退出时通过 `atexit` 强制回收，杜绝僵尸进程。

## 6. 性能基准测试

`perf_check.py` 提供启动性能基准测试：
- 测量 `import web_app`、`build_ui`、`build_guide`、`build_api_doc`、`history_table` 等关键步骤耗时
- CI 环境有 5x 时间限制倍数
- 用于防止启动性能退化

## 7. 当前架构特征

- 优点: 模块边界清晰，服务职责明确，便于扩展。
- 注意点: 仍以单进程单例服务为主，不是远程微服务部署架构。

---

[返回文档中心](Home.md)
