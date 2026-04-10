# Chorus-WebAI 深度操作指南 (V2.3)

本手册旨在帮助高级用户深入理解 **Chorus-WebAI** 的配置体系、新特性与进阶技巧。

---

## 版本更新摘要 (v2.3)

### 新增功能

| 功能模块 | 说明 |
|----------|------|
| **任务追踪系统** | 完整的任务生命周期管理，支持状态追踪、事件监听、依赖解析 |
| **记忆存储系统** | 多会话管理，支持对话历史持久化、上下文窗口控制 |
| **工作流引擎** | DAG 工作流编排，支持条件分支、并行执行、预定义模板 |
| **监控告警系统** | 性能指标收集、系统健康检查、告警管理 |
| **LRU 缓存** | 带TTL的缓存系统，优化频繁读取操作 |

### 架构优化

- 模块化重构：`src/` 目录分层设计
- 单例配置管理：线程安全的全局配置访问
- SQLite 持久化：任务和会话数据可靠存储

---

## ⚙️ 配置全集 (Configuration Schema)

配置文件位于 `.semi_agent/config.json`，支持实时修改：

| 配置项 | 类型 | 默认值 | 说明 | 进阶建议 |
| :--- | :--- | :--- | :--- | :--- |
| `target_url` | String | `https://chat.deepseek.com/` | 自动化进入的初始页面 | 可在"平台预设"中一键切换 |
| `browser_channel` | String | `msedge` | 浏览器内核 | 推荐使用 `msedge` 或 `chrome` |
| `send_mode` | Enum | `enter` | 发送触发方式 | `enter` (回车) / `button` (点击按钮) |
| `max_retries` | Integer | `3` | 任务失败后的重试次数 | 建议设为 3，配合线性回退算法 |
| `response_timeout_seconds` | Integer | `120` | 等待 AI 响应的最长时间 | 长文本生成建议设为 300 以上 |
| `stable_response_seconds` | Integer | `3` | 判断生成结束的静默时长 | 内容变动停止 N 秒后认为生成完成 |
| `confirm_before_send` | Boolean | `true` | 发送前是否弹出二次确认 | 批量队列执行时会自动强制关闭 |

### 环境变量支持

配置项可通过环境变量覆盖，格式为 `CHORUS_<UPPERCASE_KEY>`：

```powershell
# 示例
set CHORUS_MAX_RETRIES=5
set CHORUS_TARGET_URL=https://kimi.moonshot.cn/
```

---

## 🎭 任务模板与提示词技巧

### 1. 内置模板说明

| 模板 | Key | 用途 |
|------|-----|------|
| 摘要总结 | `summary` | 针对长文提取核心要点 |
| 润色改写 | `rewrite` | 提升文本的专业度与逻辑连贯性 |
| 信息抽取 | `extract` | 提取日期、人物、行动项等结构化信息 |
| 翻译 | `translation` | 多语言翻译 |
| 自定义原样发送 | `custom` | 跳过模板，直接发送原始内容 |

### 2. `{user_input}` 占位符

模板底层通过 Python `str.format()` 实现。在"自定义"模板中可直接控制提示词结构。

### 3. 预定义工作流模板

| 工作流 | 步骤 | 用途 |
|--------|------|------|
| Summary Workflow | 总结 → 抽取 | 先总结内容再提取关键点 |
| Translation Workflow | 翻译 → 审校 | 翻译后自动进行质量检查 |

---

## ⛓️ 链式接力 (Relay) 进阶用法

在 **"批量任务队列"** 中，`{prev_result}` 是实现工作流自动化的核心：

### 示例：自动化报告生成流程

```
任务 A: 请将以下用户需求拆解为 3 个功能模块：
{user_input}

任务 B: 针对以下功能模块，请各写一段 200 字的技术实现方案：
{prev_result}

任务 C: 请为以上技术方案编写测试用例：
{prev_result}
```

### 依赖管理

- 任务按添加顺序执行
- 每个任务可引用 `{prev_result}` 获取前一任务的输出
- 如果前置任务失败，后续任务将收到空字符串

---

## 📊 任务追踪系统 (TaskTracker)

### 功能概览

- **生命周期管理**：创建 → 启动 → 完成/失败 → 重试
- **事件监听**：订阅任务状态变更事件
- **持久化存储**：SQLite 数据库自动保存
- **统计聚合**：成功率、平均耗时等指标

### CLI 使用

```
# 查看任务统计
选择菜单项 6) Task statistics

# 查看系统健康状态
选择菜单项 7) System health
```

### 编程接口

```python
from src.services.task_tracker import TaskTracker, TaskTrackerEvent

tracker = TaskTracker()

# 创建任务
task = await tracker.create_task(
    template_key="summary",
    user_input="Your content here"
)

# 添加事件监听器
def on_complete(task):
    print(f"Task {task.id} completed!")

tracker.add_listener(TaskTrackerEvent.TASK_COMPLETED, on_complete)

# 执行任务
await tracker.start_task(task.id)
await tracker.complete_task(task.id, "Response content")

# 获取统计
stats = tracker.get_statistics()
print(f"Success rate: {stats['success_rate']:.2%}")
```

---

## 💾 记忆存储系统 (MemoryStore)

### 功能概览

- **多会话管理**：创建、切换、归档会话
- **消息历史**：完整对话记录持久化
- **上下文窗口**：控制传递给 AI 的历史长度
- **语义搜索**：按关键词检索历史消息

### Web UI 使用

1. 切换到 **"💾 记忆存储"** 标签页
2. 输入会话标题，点击 **"创建会话"**
3. 在会话列表中选择要切换的会话 ID
4. 点击 **"查看当前上下文"** 显示对话历史

### 编程接口

```python
from src.services.memory_store import SessionManager

manager = SessionManager()

# 记忆对话
manager.remember("user", "Hello, AI!")
manager.remember("assistant", "Hello! How can I help you?")

# 回忆上下文
context = manager.recall(max_messages=10)
for msg in context:
    print(f"[{msg['role']}]: {msg['content']}")

# 搜索历史
results = manager.search("Python")
print(f"Found {len(results)} matching messages")

# 会话管理
sessions = manager.list_sessions()
manager.switch_session("session_id_here")
```

---

## 🔄 工作流引擎 (WorkflowEngine)

### 概念说明

工作流是由多个步骤(Step)组成的有向无环图(DAG)，支持：

- **顺序执行**：步骤按依赖顺序执行
- **条件分支**：根据条件选择执行路径
- **并行执行**：多个步骤同时执行
- **延迟等待**：在步骤间插入延迟

### 步骤类型

| 类型 | 说明 |
|------|------|
| `TASK` | 执行 AI 任务 |
| `CONDITION` | 条件判断，选择分支 |
| `PARALLEL` | 并行执行多个子步骤 |
| `DELAY` | 延迟等待 |

### Web UI 使用

1. 切换到 **"🔄 工作流引擎"** 标签页
2. 从下拉菜单选择工作流模板
3. 点击 **"查看详情"** 了解工作流结构
4. 输入内容，点击 **"执行工作流"**

### 编程接口

```python
from src.services.workflow import (
    WorkflowEngine, WorkflowDefinition, WorkflowStep, StepType
)

engine = WorkflowEngine()

# 定义工作流
workflow = WorkflowDefinition(
    id="my_workflow",
    name="My Custom Workflow",
    steps=[
        WorkflowStep(
            id="step1",
            name="Analyze",
            step_type=StepType.TASK,
            template_key="summary",
            user_input="Analyze: {user_input}",
        ),
        WorkflowStep(
            id="step2",
            name="Extract",
            step_type=StepType.TASK,
            template_key="extract",
            user_input="Extract from: {prev_result}",
            depends_on=["step1"],
        ),
    ],
)

# 注册并执行
engine.register_workflow(workflow)
execution = await engine.execute("my_workflow", {"user_input": "test data"})

# 检查结果
if execution.state.value == "completed":
    print("Workflow completed!")
    print(execution.step_results)
```

---

## 📈 监控面板 (Monitor)

### 功能概览

- **指标收集**：计数器、仪表盘、直方图
- **健康检查**：系统组件状态检测
- **告警管理**：阈值告警、事件通知

### Web UI 使用

1. 切换到 **"📈 监控面板"** 标签页
2. 点击 **"刷新仪表盘"** 获取系统状态
3. 点击 **"任务统计"** 查看执行指标
4. 点击 **"健康检查"** 检测系统组件

### 编程接口

```python
from src.services.monitor import Monitor, AlertLevel

monitor = Monitor()

# 记录任务执行
monitor.record_task_execution(
    success=True,
    duration_seconds=2.5,
    template="summary"
)

# 注册健康检查
from src.services.monitor import HealthStatus

def check_database():
    # 自定义检查逻辑
    return HealthStatus(
        component="database",
        healthy=True,
        message="Connection OK"
    )

monitor.register_health_check("database", check_database)

# 获取仪表盘数据
dashboard = monitor.get_dashboard_data()
print(f"System healthy: {dashboard['health']['healthy']}")

# 触发告警
monitor.alerts.fire(
    name="high_latency",
    level=AlertLevel.WARNING,
    message="Task duration exceeds 60 seconds"
)
```

---

## 📁 项目结构

```
test_mcp/
├── src/                          # 源代码模块
│   ├── core/                     # 核心引擎
│   │   ├── __init__.py
│   │   ├── config.py             # 配置管理（单例模式）
│   │   ├── browser.py            # 浏览器自动化
│   │   └── exceptions.py         # 异常层次结构
│   ├── models/                   # 数据模型
│   │   ├── __init__.py
│   │   ├── task.py               # 任务模型（状态机）
│   │   ├── session.py            # 会话模型
│   │   └── history.py            # 历史记录模型
│   ├── services/                 # 业务服务
│   │   ├── __init__.py
│   │   ├── task_tracker.py       # 任务追踪服务
│   │   ├── memory_store.py       # 记忆存储服务
│   │   ├── workflow.py           # 工作流引擎
│   │   └── monitor.py            # 监控服务
│   ├── utils/                    # 工具函数
│   │   ├── __init__.py
│   │   ├── cache.py              # LRU 缓存
│   │   └── helpers.py            # 辅助函数
│   └── __init__.py
├── main.py                       # CLI 入口
├── web_app.py                    # Web UI (Gradio)
├── tests/                        # 测试文件
│   ├── test_core_logic.py
│   ├── test_web_app_events.py
│   ├── test_task_tracker.py
│   ├── test_memory_store.py
│   ├── test_workflow.py
│   ├── test_monitor.py
│   └── test_utils.py
├── docs/
│   └── USER_GUIDE.md            # 本文档
├── requirements.txt
└── README.md
```

---

## ❓ 故障排除 (FAQ)

### Q: 浏览器窗口打开了，但一直提示"找不到输入框"？

**A**: 这通常由以下原因引起：
1. **未登录**：请确保您已在弹出的浏览器窗口中完成登录并看到了聊天界面。
2. **选择器过期**：目标平台更新了 UI。请在 **"系统体检"** 中检查选择器匹配情况，或联系开发者更新配置。

### Q: 为什么性能自测 (perf_check) 在我的机器上失败了？

**A**: `perf_check` 默认阈值针对标准开发机器（模块导入 < 8s）。如果您的磁盘性能较弱（如 HDD），可能会触发超时。您可以临时在 `perf_check.py` 中调大 `limits` 字典。

### Q: 历史记录太多了，加载会变慢吗？

**A**: 不会。系统采用了 **反向文件流读取技术 (O(1) 内存)**，无论历史记录有 1MB 还是 1GB，其读取首条和末条的速度是恒定的。

### Q: 任务追踪数据存储在哪里？

**A**: 任务数据存储在 `.semi_agent/tasks.db` SQLite 数据库中。会话数据存储在 `.semi_agent/memory.db`。

### Q: 如何清理所有状态数据？

**A**: 
```powershell
# 清理浏览器 Profile (需关闭所有程序)
rm -rf .semi_agent/browser_profile/

# 清理任务和会话数据库
rm .semi_agent/tasks.db
rm .semi_agent/memory.db

# 清理所有状态（完全重置）
rm -rf .semi_agent/
```

---

## 🛠️ 开发者维护命令

```powershell
# 运行全量单元测试
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/test_task_tracker.py -v

# 运行性能门禁自测
python perf_check.py

# 启动 Web UI
python web_app.py

# 启动 CLI 模式
python main.py
```

---

## 🔧 扩展开发

### 添加新的任务模板

编辑 `src/utils/helpers.py` 中的 `TEMPLATES` 字典：

```python
TEMPLATES["my_template"] = "Your custom prompt: {user_input}"
```

### 添加新的 AI 平台

编辑 `src/core/config.py` 中的 `DEFAULT_PROVIDERS`：

```python
DEFAULT_PROVIDERS["new_platform"] = ProviderConfig(
    key="new_platform",
    label="New Platform",
    url="https://new-platform.com/chat",
    send_mode="enter",
    guide="平台使用提示",
)
```

### 创建自定义工作流

参考 `src/services/workflow.py` 中的 `create_summary_workflow()` 函数创建新的工作流模板。

---

*Chorus-WebAI v2.3：让网页 AI 成为您的生产力突触。*
