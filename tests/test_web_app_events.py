from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import web_app


def test_provider_label_from_config_default():
    assert web_app._provider_label_from_config({}) == web_app.PROVIDERS["deepseek"]["label"]


def test_provider_guide_text_contains_url():
    label = web_app.PROVIDERS["kimi"]["label"]
    text = web_app._provider_guide_text(label)
    assert "https://kimi.moonshot.cn/" in text


def test_apply_provider_returns_expected_tuple():
    label = web_app.PROVIDERS["tongyi"]["label"]
    url, send_mode, guide, status = web_app._apply_provider(label)
    assert url == web_app.PROVIDERS["tongyi"]["url"]
    assert send_mode == web_app.PROVIDERS["tongyi"]["send_mode"]
    assert "平台" in guide
    assert "已切换平台" in status


def test_api_doc_build_and_export(tmp_path, monkeypatch):
    text = web_app._build_api_doc_text()
    assert "接口文档" in text

    monkeypatch.setattr(web_app, "DOCS_DIR", tmp_path)
    file_path, msg = web_app._export_api_doc()
    assert Path(file_path).exists()
    assert "已生成" in msg


def test_template_help_and_input_tip():
    assert "模板说明" in web_app._template_help("摘要总结")
    assert "输入提示" in web_app._input_tip("")
    assert "输入长度" in web_app._input_tip("a" * 30)


def test_history_table_filter(monkeypatch):
    sample = [
        {"time": "t1", "template": "summary", "duration_seconds": 1, "response_chars": 10, "ok": True},
        {"time": "t2", "template": "summary", "duration_seconds": 2, "response_chars": 0, "ok": False},
    ]
    monkeypatch.setattr(web_app.core, "read_history", lambda limit=120: sample)
    assert len(web_app._history_table("全部")) == 2
    assert len(web_app._history_table("仅成功")) == 1
    assert len(web_app._history_table("仅失败")) == 1


def test_clear_history(tmp_path, monkeypatch):
    hist = tmp_path / "history.jsonl"
    hist.write_text("x", encoding="utf-8")
    monkeypatch.setattr(web_app.core, "HISTORY_PATH", hist)
    monkeypatch.setattr(web_app, "_history_table", lambda filter_mode="全部": [["ok"]])
    msg, rows = web_app._clear_history()
    assert "清空" in msg
    assert rows == [["ok"]]
    assert hist.read_text(encoding="utf-8") == ""


def test_latest_errors(tmp_path, monkeypatch):
    err_dir = tmp_path / "errors"
    err_dir.mkdir()
    monkeypatch.setattr(web_app.core, "ERROR_DIR", err_dir)
    assert "暂无错误日志" in web_app._latest_errors()
    p = err_dir / "error_1.txt"
    p.write_text("boom", encoding="utf-8")
    out = web_app._latest_errors()
    assert "error_1.txt" in out
    assert "boom" in out


def test_health_check(monkeypatch):
    monkeypatch.setattr(web_app, "_profile_has_login_data", lambda: True)
    monkeypatch.setattr(web_app.core, "load_config", lambda: {"target_url": "u", "confirm_before_send": True, "max_retries": 3, "provider_key": "deepseek"})
    out = web_app._health_check()
    data = json.loads(out)
    assert data["目标网址"] == "u"


def test_load_and_save_config(monkeypatch):
    saved = {}

    def fake_load():
        return {
            "target_url": "https://chat.deepseek.com/",
            "provider_key": "deepseek",
            "send_mode": "enter",
            "confirm_before_send": True,
            "max_retries": 3,
            "response_timeout_seconds": 120,
        }

    def fake_save(cfg):
        saved.update(cfg)

    monkeypatch.setattr(web_app.core, "load_config", fake_load)
    monkeypatch.setattr(web_app.core, "save_config", fake_save)

    status, guide, provider_guide = web_app._save_config_from_form(
        web_app.PROVIDERS["kimi"]["label"],
        "https://kimi.moonshot.cn/",
        "enter",
        True,
        4,
        180,
    )
    assert "保存" in status
    assert "新手进度" in guide
    assert "平台" in provider_guide
    assert saved["provider_key"] == "kimi"


def test_open_login_browser_existing_session(monkeypatch):
    monkeypatch.setitem(web_app.LOGIN_STATE, "context", object())
    msg, _ = web_app._open_login_browser()
    assert "已打开" in msg
    web_app.LOGIN_STATE["context"] = None


def test_open_login_browser_fail(monkeypatch):
    monkeypatch.setattr(web_app.core, "load_config", lambda: {"target_url": "x", "navigation_timeout_seconds": 10})

    def bad_open(_cfg):
        raise RuntimeError("no browser")

    monkeypatch.setattr(web_app.core, "open_chat_page", bad_open)
    msg, _ = web_app._open_login_browser()
    assert "失败" in msg


def test_finish_login_no_session():
    web_app.LOGIN_STATE["page"] = None
    msg, _ = web_app._finish_login_check()
    assert "未检测到" in msg


def test_finish_login_success(monkeypatch):
    web_app.LOGIN_STATE["page"] = object()
    monkeypatch.setattr(web_app.core, "load_config", lambda: {"input_selectors": ["x"]})
    monkeypatch.setattr(web_app.core, "get_first_visible_locator", lambda p, s, timeout_ms=0: object())
    monkeypatch.setattr(web_app, "_close_login_session", lambda: None)
    msg, _ = web_app._finish_login_check()
    assert "通过" in msg


def test_finish_login_fail(monkeypatch):
    web_app.LOGIN_STATE["page"] = object()
    monkeypatch.setattr(web_app.core, "load_config", lambda: {"input_selectors": ["x"]})
    monkeypatch.setattr(web_app.core, "get_first_visible_locator", lambda p, s, timeout_ms=0: None)
    monkeypatch.setattr(web_app, "_close_login_session", lambda: None)
    msg, _ = web_app._finish_login_check()
    assert "未检测到" in msg


def test_run_smoke_requires_confirm():
    msg, _ = web_app._run_smoke_test(False, 0)
    assert "勾选" in msg


def test_run_smoke_success(monkeypatch):
    monkeypatch.setattr(web_app.core, "load_config", lambda: {"confirm_before_send": True, "smoke_pause_seconds": 0})
    monkeypatch.setattr(web_app.core, "send_with_retry", lambda cfg, prompt: "READY")
    records = []
    monkeypatch.setattr(web_app.core, "append_history", lambda row: records.append(row))
    msg, _ = web_app._run_smoke_test(True, 0)
    assert "成功" in msg
    assert records and records[0]["ok"] is True


def test_run_smoke_fail(monkeypatch):
    monkeypatch.setattr(web_app.core, "load_config", lambda: {"confirm_before_send": True, "smoke_pause_seconds": 0})

    def boom(cfg, prompt):
        raise RuntimeError("x")

    monkeypatch.setattr(web_app.core, "send_with_retry", boom)
    records = []
    monkeypatch.setattr(web_app.core, "append_history", lambda row: records.append(row))
    msg, _ = web_app._run_smoke_test(True, 0)
    assert "失败" in msg
    assert records and records[0]["ok"] is False


def test_one_click_prepare(monkeypatch):
    monkeypatch.setattr(web_app, "_open_login_browser", lambda: ("已打开", "g"))
    msg, guide = web_app._one_click_prepare()
    assert "自动准备" in msg
    assert guide == "g"


def test_run_task_empty(monkeypatch):
    monkeypatch.setattr(web_app, "_history_table", lambda mode="全部": [])
    status, *_ = web_app._run_task("摘要总结", "", True)
    assert "取消" in status


def test_run_task_require_confirm(monkeypatch):
    monkeypatch.setattr(web_app.core, "load_config", lambda: {"confirm_before_send": True})
    monkeypatch.setattr(web_app, "_history_table", lambda mode="全部": [])
    status, *_ = web_app._run_task("摘要总结", "abc", False)
    assert "勾选" in status


def test_run_task_success(monkeypatch):
    monkeypatch.setattr(web_app.core, "load_config", lambda: {"confirm_before_send": True})
    monkeypatch.setattr(web_app.core, "build_prompt", lambda key, text: f"{key}:{text}")
    monkeypatch.setattr(web_app.core, "send_with_retry", lambda cfg, prompt: "ok")
    rows = []
    monkeypatch.setattr(web_app.core, "append_history", lambda row: rows.append(row))
    monkeypatch.setattr(web_app, "_history_table", lambda mode="全部": [["x"]])
    status, prompt, response, _, hist = web_app._run_task("摘要总结", "abc", True)
    assert "成功" in status
    assert prompt.startswith("summary")
    assert response == "ok"
    assert hist == [["x"]]
    assert rows and rows[0]["ok"] is True


def test_run_task_fail(monkeypatch):
    monkeypatch.setattr(web_app.core, "load_config", lambda: {"confirm_before_send": True})
    monkeypatch.setattr(web_app.core, "build_prompt", lambda key, text: f"{key}:{text}")

    def boom(cfg, prompt):
        raise RuntimeError("fail")

    monkeypatch.setattr(web_app.core, "send_with_retry", boom)
    rows = []
    monkeypatch.setattr(web_app.core, "append_history", lambda row: rows.append(row))
    monkeypatch.setattr(web_app, "_history_table", lambda mode="全部": [["x"]])
    status, *_ = web_app._run_task("摘要总结", "abc", True)
    assert "失败" in status
    assert rows and rows[0]["ok"] is False


def test_reuse_last_input():
    web_app.LAST_INPUT["template"] = "摘要总结"
    web_app.LAST_INPUT["content"] = "abc"
    t, c = web_app._reuse_last_input()
    assert t == "摘要总结"
    assert c == "abc"


def test_export_response(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "EXPORT_DIR", tmp_path)
    file_path, msg = web_app._export_response("hello")
    assert file_path
    assert Path(file_path).exists()
    assert "导出完成" in msg


def test_export_response_empty():
    file_path, msg = web_app._export_response("")
    assert file_path == ""
    assert "没有可导出" in msg


def test_pick_available_port_and_busy_port():
    port = web_app._pick_available_port(7900, 7920)
    assert 7900 <= port <= 7920

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    try:
        with pytest.raises(RuntimeError):
            web_app._pick_available_port(port, port)
    finally:
        sock.close()


def test_build_ui_object():
    app = web_app.build_ui()
    assert app is not None
