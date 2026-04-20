# ShadowBoard 文档中心

这是项目唯一建议入口。你可以从这里快速定位功能文档、架构文档和历史方案文档。

---

## 1. 使用与配置

- [项目总览与快速开始](../README.md)
- [配置手册](Configuration.md)
- [常见问题](FAQ.md)

## 2. 架构与实现

- [系统架构总览](Architecture.md)
- [进阶架构方案 (Advanced)](Architecture-Advanced.md)
- [核心服务说明](Services.md)
- [工作流引擎说明](Workflows.md)
- [API 参考](API-Reference.md)
- [开发与维护指南](Development.md)
- [实施与部署指南](Implementation.md)

## 3. 归档与备份

以下文档为历史阶段的规划与交付记录，已统一归档至 `docs/archive/`：

- [交付总结与升级摘要](archive/DELIVERY_SUMMARY.md)
- [企业级升级摘要](archive/ENTERPRISE_UPGRADE_SUMMARY.md)

---

## 4. 当前代码结构（与源码一致）

```text
src/
	core/         # 配置、异常、浏览器管理、依赖注入
	models/       # Task / Session / History 等数据模型
	services/     # Workflow / TaskTracker / MemoryStore / Monitor
	ui/           # Gradio UI 组件与各 Tab 逻辑
	utils/        # 模板与通用工具函数
```

如果发现文档与代码不一致，请以源码为准，并在此页补充索引。
