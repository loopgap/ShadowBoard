# 开发与维护

本文档描述当前仓库可直接使用的开发流程，内容已与现有文件对齐。

---

## 1. 本地开发启动

```powershell
# 安装依赖（可编辑模式）
pip install -e .

# 安装浏览器内核
playwright install chromium

# 启动 Web UI
python web_app.py
```

## 2. 运行测试

```powershell
# 全量测试
pytest

# 指定测试文件
pytest tests/test_workflow.py

# 性能检查
python perf_check.py
```

## 3. 关键目录

- `src/core/`: 配置、异常、浏览器管理、服务依赖。
- `src/services/`: 工作流、任务追踪、记忆存储、监控。
- `src/models/`: Task、Session、History 等模型。
- `src/ui/`: Gradio 页面组装与 Tab 业务逻辑。
- `tests/`: 单元测试与集成测试。

## 4. 开发约定

- 新增服务优先放在 `src/services/`，模型放在 `src/models/`。
- 业务入口统一通过 `src/core/dependencies.py` 获取服务实例。
- 文档变更后同步更新 [Home.md](Home.md) 的索引。

---

[返回文档中心](Home.md)
