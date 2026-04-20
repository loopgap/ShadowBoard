from __future__ import annotations

import json
import os
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
        "import_web_app_seconds": 20.0,  # After lazy loading, import is fast
        "build_ui_seconds": 15.0,  # gradio import now counts here (was in import)
        "build_guide_seconds": 0.4,
        "build_api_doc_seconds": 0.4,
        "history_table_seconds": 0.6,
    }

    is_ci = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"
    multiplier = 5.0 if is_ci else 1.0

    failed = []
    for k, limit in limits.items():
        effective_limit = limit * multiplier
        if metrics[k] > effective_limit:
            failed.append({"metric": k, "value": metrics[k], "limit": effective_limit})

    print(
        json.dumps(
            {
                "metrics": metrics,
                "limits": {k: v * multiplier for k, v in limits.items()},
                "failed": failed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
