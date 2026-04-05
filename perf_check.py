"""
性能指标自测工具 (Performance Metrics Checker)

该脚本用于量化关键操作的耗时，包括:
1. 模块导入时间
2. UI 渲染时间
3. 历史数据处理时间
若超过预设阈值，脚本将返回非零退出码，用于 CI/CD 质量门禁。
"""

from __future__ import annotations

import json
import time


def timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    dt = time.perf_counter() - t0
    return out, dt


def main() -> int:
    metrics = {}

    t0 = time.perf_counter()
    import web_app  # noqa: F401

    metrics["import_web_app_seconds"] = time.perf_counter() - t0

    import web_app as app

    _, metrics["build_ui_seconds"] = timed(app.build_ui)
    _, metrics["build_guide_seconds"] = timed(app._build_guide_markdown)
    _, metrics["build_api_doc_seconds"] = timed(app._build_api_doc_text)
    _, metrics["history_table_seconds"] = timed(app._history_table, "全部")

    limits = {
        "import_web_app_seconds": 2.0,
        "build_ui_seconds": 12.0,
        "build_guide_seconds": 0.4,
        "build_api_doc_seconds": 0.4,
        "history_table_seconds": 0.6,
    }

    failed = []
    for k, limit in limits.items():
        if metrics[k] > limit:
            failed.append({"metric": k, "value": metrics[k], "limit": limit})

    print(json.dumps({"metrics": metrics, "limits": limits, "failed": failed}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
