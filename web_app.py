from __future__ import annotations

import copy
import json
import socket
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

import gradio as gr

import main as core

LOGIN_LOCK = threading.Lock()
LOGIN_STATE: Dict[str, Any] = {"p": None, "context": None, "page": None}
LAST_INPUT: Dict[str, str] = {"template": "摘要总结", "content": ""}

EXPORT_DIR = core.STATE_DIR / "exports"
DOCS_DIR = core.STATE_DIR / "docs"

PROVIDERS: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "label": "DeepSeek 网页",
        "url": "https://chat.deepseek.com/",
        "send_mode": "enter",
        "guide": "推荐新手首选 页面稳定 先登录后做冒烟测试",
    },
    "kimi": {
        "label": "Kimi 网页",
        "url": "https://kimi.moonshot.cn/",
        "send_mode": "enter",
        "guide": "适合长文处理 登录后先执行一次冒烟验证",
    },
    "tongyi": {
        "label": "通义千问 网页",
        "url": "https://tongyi.aliyun.com/qianwen/",
        "send_mode": "button",
        "guide": "建议使用点击按钮发送 遇到弹窗先手动关闭",
    },
    "doubao": {
        "label": "豆包 网页",
        "url": "https://www.doubao.com/chat/",
        "send_mode": "enter",
        "guide": "登录后建议先做冒烟测试 再开始批量任务",
    },
    "zhipu": {
        "label": "智谱清言 网页",
        "url": "https://chatglm.cn/main/alltoolsdetail",
        "send_mode": "button",
        "guide": "建议点击按钮发送 页面改版时优先检查输入框定位",
    },
    "wenxin": {
        "label": "文心一言 网页",
        "url": "https://yiyan.baidu.com/",
        "send_mode": "button",
        "guide": "登录验证较严格 建议先人工完成验证后再自动执行",
    },
}

PROVIDER_LABEL_TO_KEY = {v["label"]: k for k, v in PROVIDERS.items()}

TEMPLATE_LABEL_TO_KEY: Dict[str, str] = {
    "摘要总结": "summary",
    "中英翻译": "translation",
    "润色改写": "rewrite",
    "信息抽取": "extract",
    "问答助手": "qa",
    "自定义原样发送": "custom",
}

KEY_TO_TEMPLATE_LABEL: Dict[str, str] = {
    "summary": "摘要总结",
    "translation": "中英翻译",
    "rewrite": "润色改写",
    "extract": "信息抽取",
    "qa": "问答助手",
    "custom": "自定义原样发送",
    "smoke": "冒烟测试",
}

TEMPLATE_GUIDE: Dict[str, str] = {
    "摘要总结": "适合长文快速提炼要点 默认输出结构化结论",
    "中英翻译": "输入任意语言文本 自动翻译并尽量保留语气",
    "润色改写": "适合邮件 汇报 简历语句优化",
    "信息抽取": "自动提取人名 日期 行动项 截止时间",
    "问答助手": "输入问题后给出简洁可执行步骤",
    "自定义原样发送": "不会套模板 直接把输入内容发送给网页 AI",
}

EXAMPLE_INPUTS: List[List[str]] = [
    ["摘要总结", "请总结下面会议纪要并输出三条结论和三条行动项\n本周完成接口联调\n下周开始灰度发布\n风险是测试资源不足"],
    ["润色改写", "请把这段话改得专业但简洁 这个功能目前不够稳定 我们后续会持续优化"],
    ["信息抽取", "从以下文本提取日期 负责人 截止时间 王明二月二十八日前完成验收文档 李华三月一日提交测试报告"],
    ["自定义原样发送", "你是一名项目助理 请把我的需求拆成可执行清单"],
]

HISTORY_FILTERS = ["全部", "仅成功", "仅失败"]

CUSTOM_CSS = """
:root { color-scheme: light dark; }
footer, #footer, .gradio-container .footer, [data-testid='footer'] { display: none !important; }

.gradio-container {
  --body-background-fill: #f5f7fb;
  --block-background-fill: #ffffff;
  --block-border-color: #dbe2ee;
  --block-label-text-color: #111827;
  --body-text-color: #111827;
  --body-text-color-subdued: #4b5563;
  --input-background-fill: #ffffff;
  --input-border-color: #cbd5e1;
  --input-placeholder-color: #6b7280;
  --color-accent: #1a73e8;
  --color-accent-soft: #e8f0fe;
  font-family: "Google Sans", "HarmonyOS Sans SC", "MiSans", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  background:
    radial-gradient(1000px 300px at 8% -8%, #e8f0fe 0%, rgba(232,240,254,0) 65%),
    radial-gradient(800px 260px at 92% -18%, #f3f8ff 0%, rgba(243,248,255,0) 65%),
    #f7f9fc;
  color: #111827;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  font-size: 15px;
  line-height: 1.65;
}

.hero {
  border: 1px solid #d2e3fc;
  border-radius: 22px;
  background: #ffffff;
  padding: 22px;
  margin-bottom: 14px;
  box-shadow: 0 10px 28px rgba(26,115,232,0.08);
}
.hero-title { font-size: 34px; font-weight: 800; color: #202124; margin-bottom: 8px; }
.hero-sub { font-size: 16px; color: #4b5563; margin-bottom: 12px; }
.hero-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.hero-chip {
  display: inline-block;
  border: 1px solid #d2e3fc;
  border-radius: 999px;
  padding: 6px 12px;
  background: #eef4ff;
  color: #174ea6;
  font-size: 13px;
  font-weight: 600;
}

.section-card {
  border: 1px solid #e6ebf2;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 4px 14px rgba(60,64,67,0.07);
  padding: 14px;
  margin-top: 8px;
}

.section-card,
.section-card * {
  color: #111827 !important;
}

.section-card .prose,
.section-card .prose * {
  background: transparent !important;
}

.section-title {
  font-size: 18px;
  font-weight: 700;
  color: #202124;
  margin-bottom: 10px;
}

.gradio-container .tabs {
  background: transparent !important;
}

.gradio-container .tabs button {
  color: #374151 !important;
  font-weight: 600 !important;
  border-bottom: 2px solid transparent !important;
  background: #f5f7fb !important;
  border-radius: 10px 10px 0 0 !important;
}

.gradio-container .tabs button:hover {
  color: #174ea6 !important;
  background: #eef4ff !important;
}

.gradio-container .tabs button[aria-selected='true'] {
  color: #174ea6 !important;
  font-weight: 700 !important;
  border-bottom: 2px solid #1a73e8 !important;
  background: #ffffff !important;
  box-shadow: inset 0 -1px 0 #1a73e8 !important;
}

.gradio-container textarea,
.gradio-container input,
.gradio-container .wrap,
.gradio-container .block {
  color: #202124 !important;
}

.gradio-container textarea,
.gradio-container input {
  background: #ffffff !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 10px !important;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04) !important;
}

.gradio-container .prose,
.gradio-container .prose * {
  color: #202124 !important;
}

.gradio-container .prose h1,
.gradio-container .prose h2,
.gradio-container .prose h3,
.gradio-container .prose h4 {
  color: #1f1f1f !important;
}

.gradio-container .prose p,
.gradio-container .prose li,
.gradio-container .prose strong {
  color: #111827 !important;
  line-height: 1.75 !important;
  font-size: 15px !important;
}

.gradio-container .prose code,
.gradio-container .prose pre {
  background: #f6f8fc !important;
  color: #1f1f1f !important;
  border: 1px solid #e3e8f0 !important;
}

.gradio-container [class*='markdown'],
.gradio-container [class*='markdown'] > div {
  background: #ffffff !important;
  border-radius: 10px !important;
}

.action-primary button {
  background: #1a73e8 !important;
  border-color: #1a73e8 !important;
  color: #ffffff !important;
  font-weight: 700 !important;
}
.action-primary button:hover { background: #1967d2 !important; }

.action-secondary button {
  background: #ffffff !important;
  border-color: #d2e3fc !important;
  color: #174ea6 !important;
  font-weight: 700 !important;
}

.provider-card textarea,
.provider-card input {
  background: #f7faff !important;
}

.cn-quick-actions {
  margin-top: 16px;
  margin-bottom: 8px;
  border: 1px solid #d2e3fc;
  border-radius: 16px;
  padding: 14px;
  background: #eef4ff;
}
.cn-quick-title { font-size: 18px; font-weight: 700; color: #174ea6; margin-bottom: 10px; }
.cn-quick-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.cn-quick-btn {
  display: block;
  text-align: center;
  text-decoration: none !important;
  font-size: 15px;
  font-weight: 700;
  color: #ffffff !important;
  padding: 12px 10px;
  border-radius: 10px;
  border: 1px solid #1a73e8;
  background: #1a73e8;
}
.cn-quick-btn:hover { background: #1967d2; }
.cn-quick-tip { margin-top: 10px; color: #3c4043; font-size: 13px; }

.gradio-container label,
.gradio-container .label-wrap,
.gradio-container .svelte-1ipelgc {
  color: #111827 !important;
}

/* History table readability in light mode */
#history-table table,
#history-table thead,
#history-table tbody,
#history-table tr,
#history-table th,
#history-table td {
  background: #ffffff !important;
  color: #111827 !important;
  border-color: #dbe2ee !important;
}

#history-table th {
  font-weight: 700 !important;
}

#history-table .table-wrap,
#history-table .table-wrap * {
  color: #111827 !important;
  border-color: #dbe2ee !important;
}

#history-table [role='grid'],
#history-table [role='row'],
#history-table [role='gridcell'],
#history-table [role='columnheader'] {
  background: #ffffff !important;
  color: #111827 !important;
}

#history-filter,
#history-filter * {
  color: #111827 !important;
}

@media (max-width: 900px) {
  .hero-title { font-size: 26px; }
  .cn-quick-grid { grid-template-columns: 1fr; }
}

@media (prefers-color-scheme: dark) {
  .gradio-container {
    --body-background-fill: #0f172a;
    --block-background-fill: #111827;
    --body-text-color: #e5e7eb;
    --body-text-color-subdued: #9ca3af;
    --input-background-fill: #0b1220;
    --input-border-color: #334155;
    --block-border-color: #334155;
    background:
      radial-gradient(1000px 300px at 8% -8%, #1e3a8a 0%, rgba(30,58,138,0) 65%),
      radial-gradient(800px 260px at 92% -18%, #1f2937 0%, rgba(31,41,55,0) 65%),
      #0b1220 !important;
    color: #e5e7eb !important;
  }

  .hero,
  .section-card,
  .cn-quick-actions {
    background: #111827 !important;
    border-color: #334155 !important;
    color: #e5e7eb !important;
  }

  .hero-title,
  .section-title,
  .gradio-container .prose,
  .gradio-container .prose *,
  .section-card,
  .section-card * {
    color: #e5e7eb !important;
  }

  .hero-sub,
  .cn-quick-tip {
    color: #cbd5e1 !important;
  }

  .gradio-container [class*='markdown'],
  .gradio-container [class*='markdown'] > div {
    background: #111827 !important;
    color: #e5e7eb !important;
  }

  .action-secondary button {
    background: #0b1220 !important;
    color: #93c5fd !important;
    border-color: #334155 !important;
  }

  .gradio-container textarea,
  .gradio-container input {
    background: #0b1220 !important;
    color: #e5e7eb !important;
    border-color: #334155 !important;
  }

  .gradio-container .tabs button {
    background: #0b1220 !important;
    color: #cbd5e1 !important;
  }

  .gradio-container .tabs button[aria-selected='true'] {
    background: #111827 !important;
    color: #93c5fd !important;
    border-bottom-color: #60a5fa !important;
  }

  /* History table readability in dark mode */
  #history-table table,
  #history-table thead,
  #history-table tbody,
  #history-table tr,
  #history-table th,
  #history-table td {
    background: #0b1220 !important;
    color: #e5e7eb !important;
    border-color: #334155 !important;
  }

  #history-table .table-wrap,
  #history-table .table-wrap *,
  #history-table [role='grid'],
  #history-table [role='row'],
  #history-table [role='gridcell'],
  #history-table [role='columnheader'] {
    background: #0b1220 !important;
    color: #e5e7eb !important;
    border-color: #334155 !important;
  }

  #history-filter,
  #history-filter * {
    color: #e5e7eb !important;
  }
}
"""


def _ensure_dirs() -> None:
    core.ensure_state()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)


def _provider_label_from_config(cfg: Dict[str, Any]) -> str:
    key = str(cfg.get("provider_key", "deepseek")).strip()
    if key in PROVIDERS:
        return PROVIDERS[key]["label"]
    return PROVIDERS["deepseek"]["label"]


def _provider_guide_text(provider_label: str) -> str:
    key = PROVIDER_LABEL_TO_KEY.get(provider_label, "deepseek")
    item = PROVIDERS[key]
    return "\n".join(
        [
            f"平台 {item['label']}",
            f"推荐网址 {item['url']}",
            f"推荐发送方式 {'回车发送' if item['send_mode'] == 'enter' else '点击按钮发送'}",
            f"操作建议 {item['guide']}",
        ]
    )


def _build_api_doc_text() -> str:
    lines = [
        "网页 AI 半自动助手 接口文档",
        "",
        "功能事件列表",
        "1 应用平台预设 事件 应用平台预设",
        "2 保存参数 事件 保存参数",
        "3 打开登录浏览器 事件 打开登录浏览器",
        "4 登录完成检查 事件 登录完成检查",
        "5 执行冒烟测试 事件 执行冒烟测试",
        "6 一键准备 事件 一键准备",
        "7 开始执行 事件 开始执行",
        "8 复用上次输入 事件 复用上次输入",
        "9 导出结果 事件 导出结果",
        "10 刷新历史 事件 刷新历史",
        "11 清空历史 事件 清空历史",
        "12 健康检查 事件 健康检查",
        "13 查看最近错误日志 事件 查看最近错误日志",
        "",
        "平台支持",
    ]
    for p in PROVIDERS.values():
        lines.append(f"- {p['label']} {p['url']} 发送方式 {p['send_mode']}")
    lines.extend(
        [
            "",
            "说明",
            "本工具通过浏览器自动化与网页 AI 交互",
            "登录 验证码 风控等步骤需用户人工配合",
        ]
    )
    return "\n".join(lines)


def _export_api_doc() -> Tuple[str, str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DOCS_DIR / f"api_doc_{ts}.md"
    path.write_text(_build_api_doc_text(), encoding="utf-8")
    return str(path), f"接口文档已生成 {path.name}"


def _profile_has_login_data() -> bool:
    try:
        return core.PROFILE_DIR.exists() and any(core.PROFILE_DIR.iterdir())
    except Exception:
        return False


def _history_has_success(template: str | None = None) -> bool:
    rows = core.read_history(limit=120)
    for row in rows:
        if not bool(row.get("ok", False)):
            continue
        if template is None or row.get("template") == template:
            return True
    return False


def _build_guide_markdown() -> str:
    cfg = core.load_config()
    has_login = _profile_has_login_data()
    has_smoke = _history_has_success("smoke")
    has_task_success = _history_has_success()

    step1 = "已完成 已保存配置" if cfg.get("target_url") else "待完成 请先保存配置"
    step2 = "已完成 检测到登录会话" if has_login else "待完成 请点击 打开登录浏览器"
    step3 = "已完成 冒烟测试通过" if has_smoke else "待完成 建议先执行冒烟测试"
    step4 = "已完成 已有成功任务" if has_task_success else "待完成 前往 执行任务 完成首个任务"

    return "\n".join(
        [
            "### 新手进度",
            f"1 {step1}",
            f"2 {step2}",
            f"3 {step3}",
            f"4 {step4}",
            "",
            "建议 首次使用按顺序完成一到四",
        ]
    )


def _template_help(template_label: str) -> str:
    guide = TEMPLATE_GUIDE.get(template_label, "")
    return f"模板说明 {guide}" if guide else "模板说明 请选择模板后开始输入"


def _input_tip(user_input: str) -> str:
    text = (user_input or "").strip()
    length = len(text)
    if length == 0:
        return "输入提示 请粘贴正文或直接写需求"
    if length < 20:
        return f"输入长度 {length} 字 建议补充上下文 结果会更稳定"
    if length > 6000:
        return f"输入长度 {length} 字 内容较长 建议分段执行"
    return f"输入长度 {length} 字 内容质量正常 可直接执行"


def _history_table(filter_mode: str = "全部") -> List[List[Any]]:
    rows = core.read_history(limit=120)
    out: List[List[Any]] = []
    for row in rows:
        ok = bool(row.get("ok", False))
        if filter_mode == "仅成功" and not ok:
            continue
        if filter_mode == "仅失败" and ok:
            continue
        out.append(
            [
                row.get("time", "-"),
                KEY_TO_TEMPLATE_LABEL.get(str(row.get("template", "-")), str(row.get("template", "-"))),
                row.get("duration_seconds", "-"),
                row.get("response_chars", "-"),
                "成功" if ok else "失败",
                str(row.get("error", ""))[:200],
            ]
        )
    return out


def _clear_history() -> Tuple[str, List[List[Any]]]:
    core.HISTORY_PATH.write_text("", encoding="utf-8")
    return "历史记录已清空", _history_table("全部")


def _latest_errors() -> str:
    files = sorted(core.ERROR_DIR.glob("error_*.txt"), reverse=True)
    if not files:
        return f"暂无错误日志 目录 {core.ERROR_DIR}"
    lines: List[str] = []
    for fp in files[:5]:
        lines.append(f"[{fp.name}]")
        try:
            lines.append(fp.read_text(encoding="utf-8")[:800])
        except Exception as exc:
            lines.append(f"读取失败 {exc}")
        lines.append("")
    return "\n".join(lines)


def _health_check() -> str:
    cfg = core.load_config()
    status = {
        "状态目录": str(core.STATE_DIR),
        "登录目录存在": core.PROFILE_DIR.exists(),
        "登录目录有内容": _profile_has_login_data(),
        "历史文件存在": core.HISTORY_PATH.exists(),
        "错误目录存在": core.ERROR_DIR.exists(),
        "目标网址": cfg.get("target_url"),
        "发送前确认": cfg.get("confirm_before_send"),
        "重试次数": cfg.get("max_retries"),
        "当前平台": cfg.get("provider_key", "deepseek"),
    }
    return json.dumps(status, ensure_ascii=False, indent=2)


def _pick_available_port(start: int = 7860, end: int = 7875) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"{start} 到 {end} 端口均被占用 请先关闭占用进程")


def _load_config_for_form() -> Tuple[str, str, str, bool, int, int, str, str, str, str]:
    cfg = core.load_config()
    provider_label = _provider_label_from_config(cfg)
    status = f"已加载配置 URL {cfg['target_url']} 重试 {cfg['max_retries']} 超时 {cfg['response_timeout_seconds']} 秒"
    return (
        provider_label,
        str(cfg["target_url"]),
        str(cfg["send_mode"]),
        bool(cfg["confirm_before_send"]),
        int(cfg["max_retries"]),
        int(cfg["response_timeout_seconds"]),
        status,
        _build_guide_markdown(),
        _provider_guide_text(provider_label),
        _build_api_doc_text(),
    )


def _apply_provider(provider_label: str) -> Tuple[str, str, str, str]:
    key = PROVIDER_LABEL_TO_KEY.get(provider_label, "deepseek")
    item = PROVIDERS[key]
    return item["url"], item["send_mode"], _provider_guide_text(provider_label), f"已切换平台 {item['label']}"


def _save_config_from_form(
    provider_label: str,
    target_url: str,
    send_mode: str,
    confirm_before_send: bool,
    max_retries: int,
    response_timeout_seconds: int,
) -> Tuple[str, str, str]:
    cfg = core.load_config()
    cfg["provider_key"] = PROVIDER_LABEL_TO_KEY.get(provider_label, "deepseek")
    cfg["target_url"] = target_url.strip() or cfg["target_url"]
    cfg["send_mode"] = send_mode
    cfg["confirm_before_send"] = bool(confirm_before_send)
    cfg["max_retries"] = int(max_retries)
    cfg["response_timeout_seconds"] = int(response_timeout_seconds)
    core.save_config(cfg)
    return "配置已保存", _build_guide_markdown(), _provider_guide_text(provider_label)


def _close_login_session() -> None:
    with LOGIN_LOCK:
        ctx = LOGIN_STATE.get("context")
        p = LOGIN_STATE.get("p")
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass
        if p is not None:
            try:
                p.stop()
            except Exception:
                pass
        LOGIN_STATE.update({"p": None, "context": None, "page": None})


def _open_login_browser() -> Tuple[str, str]:
    cfg = core.load_config()
    try:
        with LOGIN_LOCK:
            if LOGIN_STATE.get("context") is not None:
                return "登录浏览器已打开 请在该窗口完成登录", _build_guide_markdown()
            p, context, page = core.open_chat_page(cfg)
            LOGIN_STATE.update({"p": p, "context": context, "page": page})
        return "已打开登录浏览器 请登录后回到本页面点击 登录完成检查", _build_guide_markdown()
    except Exception as exc:
        _close_login_session()
        return (
            "打开浏览器失败 请先执行 .venv\\Scripts\\python.exe -m playwright install chromium 然后重试 错误 "
            f"{exc}",
            _build_guide_markdown(),
        )


def _finish_login_check() -> Tuple[str, str]:
    with LOGIN_LOCK:
        page = LOGIN_STATE.get("page")
        if page is None:
            return "未检测到登录会话 请先点击 打开登录浏览器", _build_guide_markdown()

    cfg = core.load_config()
    ok = core.get_first_visible_locator(page, cfg["input_selectors"], timeout_ms=3500) is not None
    _close_login_session()
    if ok:
        return "登录检查通过 会话已持久化保存", _build_guide_markdown()
    return "未检测到聊天输入框 请重新打开登录浏览器确认页面状态", _build_guide_markdown()


def _run_smoke_test(smoke_confirm: bool, smoke_pause_seconds: int) -> Tuple[str, str]:
    if not smoke_confirm:
        return "请先勾选冒烟测试确认后再执行", _build_guide_markdown()
    cfg = core.load_config()
    cfg["smoke_pause_seconds"] = int(smoke_pause_seconds)
    run_cfg = copy.deepcopy(cfg)
    run_cfg["confirm_before_send"] = False

    started = time.time()
    try:
        pause_seconds = max(0, int(run_cfg.get("smoke_pause_seconds", 3)))
        if pause_seconds > 0:
            time.sleep(pause_seconds)

        result = core.send_with_retry(run_cfg, "Reply with exactly: READY")
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": "smoke",
                "input_chars": 24,
                "response_chars": len(result),
                "duration_seconds": elapsed,
                "ok": True,
            }
        )
        return f"冒烟测试成功 用时 {elapsed} 秒 返回 {result[:120]}", _build_guide_markdown()
    except Exception as exc:
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": "smoke",
                "input_chars": 24,
                "response_chars": 0,
                "duration_seconds": elapsed,
                "ok": False,
                "error": str(exc),
            }
        )
        return f"冒烟测试失败 用时 {elapsed} 秒 错误 {exc}", _build_guide_markdown()


def _one_click_prepare() -> Tuple[str, str]:
    msg, guide = _open_login_browser()
    tip = "已执行自动准备 下一步请在新浏览器中登录 然后点击 登录完成检查 和 执行冒烟测试"
    return f"{tip}\n{msg}", guide


def _run_task(template_label: str, user_input: str, confirmed: bool) -> Tuple[str, str, str, str, List[List[Any]]]:
    raw_input = (user_input or "").strip()
    if not raw_input:
        return "任务已取消 输入为空", "", "", "输入提示 请先填写任务内容", _history_table("全部")

    LAST_INPUT["template"] = template_label
    LAST_INPUT["content"] = raw_input

    cfg = core.load_config()
    if cfg.get("confirm_before_send", True) and not confirmed:
        return "请先勾选 我确认发送 后再执行", "", "", _input_tip(raw_input), _history_table("全部")

    template_key = TEMPLATE_LABEL_TO_KEY.get(template_label, "custom")
    prompt = core.build_prompt(template_key, raw_input)
    run_cfg = copy.deepcopy(cfg)
    run_cfg["confirm_before_send"] = False

    started = time.time()
    try:
        response = core.send_with_retry(run_cfg, prompt)
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": template_key,
                "input_chars": len(raw_input),
                "response_chars": len(response),
                "duration_seconds": elapsed,
                "ok": True,
            }
        )
        status = f"执行成功 用时 {elapsed} 秒 返回 {len(response)} 字"
        return status, prompt[:3000], response, _input_tip(raw_input), _history_table("全部")
    except Exception as exc:
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": template_key,
                "input_chars": len(raw_input),
                "response_chars": 0,
                "duration_seconds": elapsed,
                "ok": False,
                "error": str(exc),
            }
        )
        return f"执行失败 用时 {elapsed} 秒 错误 {exc}", prompt[:3000], "", _input_tip(raw_input), _history_table("全部")


def _reuse_last_input() -> Tuple[str, str]:
    template = LAST_INPUT.get("template", "摘要总结")
    content = LAST_INPUT.get("content", "")
    return template, content


def _export_response(response: str) -> Tuple[str, str]:
    text = (response or "").strip()
    if not text:
        return "", "没有可导出的结果 请先执行任务"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt = EXPORT_DIR / f"result_{ts}.txt"
    md = EXPORT_DIR / f"result_{ts}.md"
    txt.write_text(text, encoding="utf-8")
    md.write_text(f"# 执行结果\n\n{text}\n", encoding="utf-8")
    return str(txt), f"导出完成 文件 {txt.name} 和 {md.name}"


def build_ui() -> gr.Blocks:
    provider_labels = [v["label"] for v in PROVIDERS.values()]

    with gr.Blocks(title="网页 AI 半自动助手") as demo:
        gr.HTML(
            """
<div class='hero'>
  <div class='hero-title'>网页 AI 半自动助手</div>
  <div class='hero-sub'>现代化配色 多平台模型入口 引导式流程与可审计执行</div>
  <div class='hero-chips'>
    <span class='hero-chip'>多平台适配</span>
    <span class='hero-chip'>自动重试和错误日志</span>
    <span class='hero-chip'>新手引导和一键准备</span>
  </div>
</div>
""".strip()
        )

        with gr.Tab("新手向导"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>快速开始</div>")
                guide_markdown = gr.Markdown()
                with gr.Row():
                    refresh_guide_btn = gr.Button("刷新进度建议", elem_classes=["action-secondary"])
                    one_click_btn = gr.Button("一键准备", elem_classes=["action-primary"])

            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown(
                    """
<div class='section-title'>常见问题</div>
1 登录后仍失败 先点击 登录完成检查 再点击 执行冒烟测试
2 页面元素找不到 在平台与参数把发送方式切到 点击按钮发送
3 长文本效果差 建议分段执行 每段三千字以内
4 出现验证码 请在浏览器手动完成后重试
""".strip()
                )

        with gr.Tab("平台与参数"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>平台选择</div>")
                with gr.Row():
                    provider_label = gr.Dropdown(provider_labels, value=PROVIDERS["deepseek"]["label"], label="目标平台")
                    apply_provider_btn = gr.Button("应用平台预设", elem_classes=["action-primary"])
                provider_guide = gr.Textbox(label="平台引导", lines=4, elem_classes=["provider-card"])

            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>连接与执行参数</div>")
                with gr.Row():
                    target_url = gr.Textbox(label="目标网址", value="https://chat.deepseek.com/", scale=2)
                    send_mode = gr.Radio(
                        choices=[("回车发送", "enter"), ("点击按钮发送", "button")],
                        value="enter",
                        label="发送方式",
                        scale=1,
                    )
                with gr.Row():
                    confirm_before_send = gr.Checkbox(value=True, label="执行前需要确认发送")
                    max_retries = gr.Slider(minimum=1, maximum=6, step=1, value=3, label="失败自动重试次数")
                    response_timeout = gr.Slider(minimum=30, maximum=600, step=10, value=120, label="响应超时秒数")

                save_btn = gr.Button("保存参数", elem_classes=["action-primary"])
                setup_status = gr.Textbox(label="状态反馈", lines=4)

                with gr.Row():
                    open_login_btn = gr.Button("打开登录浏览器", elem_classes=["action-secondary"])
                    finish_login_btn = gr.Button("登录完成检查", elem_classes=["action-secondary"])
                    smoke_btn = gr.Button("执行冒烟测试", elem_classes=["action-primary"])

                with gr.Row():
                    smoke_confirm = gr.Checkbox(value=False, label="我确认开始冒烟测试")
                    smoke_pause = gr.Slider(minimum=0, maximum=15, step=1, value=3, label="冒烟测试暂停秒数")

        with gr.Tab("执行任务"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>任务输入</div>")
                template_label = gr.Dropdown(list(TEMPLATE_LABEL_TO_KEY.keys()), value="摘要总结", label="任务模板")
                template_help = gr.Markdown(_template_help("摘要总结"))
                task_input = gr.Textbox(label="任务输入", lines=10, placeholder="示例 请总结这段内容 并给出三条下一步建议")
                input_tip = gr.Markdown("输入提示 请粘贴正文或直接写需求")
                send_confirm = gr.Checkbox(value=True, label="我确认发送本次任务")
                with gr.Row():
                    run_btn = gr.Button("开始执行", elem_classes=["action-primary"])
                    reuse_btn = gr.Button("复用上次输入", elem_classes=["action-secondary"])
                gr.Examples(examples=EXAMPLE_INPUTS, inputs=[template_label, task_input], label="示例输入 点击自动填充")

            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>执行结果</div>")
                run_status = gr.Textbox(label="执行状态", lines=2)
                prompt_preview = gr.Textbox(label="生成提示词预览", lines=8)
                response_box = gr.Textbox(label="AI 返回结果", lines=16)
                with gr.Row():
                    export_btn = gr.Button("导出结果", elem_classes=["action-secondary"])
                    export_file = gr.File(label="下载文件", interactive=False)
                    export_status = gr.Textbox(label="导出状态", lines=2)

        with gr.Tab("历史与诊断"):
            with gr.Group(elem_classes=["section-card"]):
                with gr.Row():
                    history_filter = gr.Radio(choices=HISTORY_FILTERS, value="全部", label="历史筛选", elem_id="history-filter")
                    refresh_history_btn = gr.Button("刷新历史", elem_classes=["action-secondary"])

                history_grid = gr.Dataframe(
                    headers=["时间", "模板", "耗时秒", "返回字数", "结果", "错误摘要"],
                    datatype=["str", "str", "number", "number", "str", "str"],
                    row_count=15,
                    column_count=(6, "fixed"),
                    wrap=True,
                    interactive=False,
                    elem_id="history-table",
                )

                with gr.Row():
                    clear_history_btn = gr.Button("清空历史", elem_classes=["action-secondary"])
                    health_btn = gr.Button("健康检查", elem_classes=["action-secondary"])
                    error_btn = gr.Button("查看最近错误日志", elem_classes=["action-secondary"])

                diag_box = gr.Textbox(label="诊断输出", lines=14)

        with gr.Tab("帮助文档"):
            with gr.Group(elem_classes=["section-card"]):
                gr.Markdown("<div class='section-title'>接口文档与使用指引</div>")
                api_doc_box = gr.Textbox(label="接口文档内容", lines=18)
                with gr.Row():
                    refresh_doc_btn = gr.Button("刷新接口文档", elem_classes=["action-secondary"])
                    export_doc_btn = gr.Button("导出接口文档", elem_classes=["action-primary"])
                api_doc_file = gr.File(label="接口文档下载", interactive=False)
                api_doc_status = gr.Textbox(label="文档状态", lines=2)

        apply_provider_btn.click(
            fn=_apply_provider,
            inputs=[provider_label],
            outputs=[target_url, send_mode, provider_guide, setup_status],
        )

        save_btn.click(
            fn=_save_config_from_form,
            inputs=[provider_label, target_url, send_mode, confirm_before_send, max_retries, response_timeout],
            outputs=[setup_status, guide_markdown, provider_guide],
        )

        open_login_btn.click(fn=_open_login_browser, outputs=[setup_status, guide_markdown])
        finish_login_btn.click(fn=_finish_login_check, outputs=[setup_status, guide_markdown])
        smoke_btn.click(fn=_run_smoke_test, inputs=[smoke_confirm, smoke_pause], outputs=[setup_status, guide_markdown])
        one_click_btn.click(fn=_one_click_prepare, outputs=[setup_status, guide_markdown])

        template_label.change(fn=_template_help, inputs=[template_label], outputs=[template_help])
        task_input.change(fn=_input_tip, inputs=[task_input], outputs=[input_tip])
        reuse_btn.click(fn=_reuse_last_input, outputs=[template_label, task_input])

        run_btn.click(
            fn=_run_task,
            inputs=[template_label, task_input, send_confirm],
            outputs=[run_status, prompt_preview, response_box, input_tip, history_grid],
        )
        export_btn.click(fn=_export_response, inputs=[response_box], outputs=[export_file, export_status])

        refresh_guide_btn.click(fn=_build_guide_markdown, outputs=[guide_markdown])
        refresh_history_btn.click(fn=_history_table, inputs=[history_filter], outputs=[history_grid])
        history_filter.change(fn=_history_table, inputs=[history_filter], outputs=[history_grid])
        clear_history_btn.click(fn=_clear_history, outputs=[diag_box, history_grid])
        health_btn.click(fn=_health_check, outputs=[diag_box])
        error_btn.click(fn=_latest_errors, outputs=[diag_box])

        refresh_doc_btn.click(fn=_build_api_doc_text, outputs=[api_doc_box])
        export_doc_btn.click(fn=_export_api_doc, outputs=[api_doc_file, api_doc_status])

        demo.load(
            fn=_load_config_for_form,
            outputs=[
                provider_label,
                target_url,
                send_mode,
                confirm_before_send,
                max_retries,
                response_timeout,
                setup_status,
                guide_markdown,
                provider_guide,
                api_doc_box,
            ],
        )
        demo.load(fn=_history_table, inputs=[history_filter], outputs=[history_grid])

        gr.HTML(
            """
<div class='cn-quick-actions'>
  <div class='cn-quick-title'>常用功能</div>
  <div class='cn-quick-grid'>
    <a class='cn-quick-btn' href='javascript:window.scrollTo({top:0,behavior:"smooth"})'>返回顶部</a>
    <a class='cn-quick-btn' href='https://www.gradio.app/docs' target='_blank'>框架说明</a>
    <a class='cn-quick-btn' href='https://platform.openai.com/docs' target='_blank'>开发参考</a>
  </div>
  <div class='cn-quick-tip'>接口文档功能已内置在帮助文档页 可直接刷新和导出</div>
</div>
""".strip()
        )

    return demo


def main() -> None:
    _ensure_dirs()
    app = build_ui()
    app.queue(default_concurrency_limit=1)
    port = _pick_available_port(7860, 7875)
    app.launch(server_name="127.0.0.1", server_port=port, inbrowser=True, theme=gr.themes.Soft(), css=CUSTOM_CSS)


if __name__ == "__main__":
    main()
