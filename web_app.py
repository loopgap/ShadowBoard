"""
网页 AI 半自动助手 - Gradio 图形界面模块 (Web UI Layer)

本模块构建了一个基于 Gradio 的交互式 Web 界面，提供以下功能:
1. 平台预设管理与参数配置
2. 引导式登录与冒烟测试流程
3. 单次任务执行与结果实时预览
4. 批量任务队列 (Task Queue) 系统
5. 历史记录审计、健康检查与接口文档导出
"""

from __future__ import annotations

import asyncio
import copy
import json
import socket
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    import gradio as gr

import main as core


# --- Task Queue System (批量任务队列系统) ---
from dataclasses import dataclass, field
import uuid

@dataclass
class QueueItem:
    """表示队列中的单个任务项"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    template_label: str = ""
    user_input: str = ""
    status: str = "等待中"  # 等待中 / 执行中 / 执行成功 / 执行失败
    result: str = ""
    added_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

TASK_QUEUE: List[QueueItem] = []
_QUEUE_LOCK = None

def get_queue_lock():
    """获取队列操作的异步锁，确保线程/并发安全"""
    global _QUEUE_LOCK
    if _QUEUE_LOCK is None:
        _QUEUE_LOCK = asyncio.Lock()
    return _QUEUE_LOCK
# ------------------------------------------

_LOGIN_LOCK = None
def get_login_lock():
    """获取浏览器登录会话的锁，防止同时打开多个登录窗口"""
    global _LOGIN_LOCK
    if _LOGIN_LOCK is None:
        _LOGIN_LOCK = asyncio.Lock()
    return _LOGIN_LOCK
LOGIN_STATE: Dict[str, Any] = {"p": None, "context": None, "page": None}
LAST_INPUT: Dict[str, str] = {"template": "摘要总结", "content": ""}

EXPORT_DIR = core.STATE_DIR / "exports"
DOCS_DIR = core.STATE_DIR / "docs"

PROVIDERS: Dict[str, Dict[str, str]] = {}
PROVIDER_LABEL_TO_KEY: Dict[str, str] = {}
TEMPLATE_LABEL_TO_KEY: Dict[str, str] = {}
KEY_TO_TEMPLATE_LABEL: Dict[str, str] = {}
TEMPLATE_GUIDE: Dict[str, str] = {}
CUSTOM_CSS: str = ""

def _load_metadata():
    """从外部 JSON 和 CSS 文件加载元数据"""
    global PROVIDERS, PROVIDER_LABEL_TO_KEY, TEMPLATE_LABEL_TO_KEY, KEY_TO_TEMPLATE_LABEL, TEMPLATE_GUIDE, CUSTOM_CSS
    
    # 加载 Providers 和 Templates
    meta_path = core.STATE_DIR / "providers.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            PROVIDERS = meta.get("providers", {})
            templates = meta.get("templates", {})
            
            PROVIDER_LABEL_TO_KEY = {v["label"]: k for k, v in PROVIDERS.items()}
            TEMPLATE_LABEL_TO_KEY = {k: v["key"] for k, v in templates.items()}
            KEY_TO_TEMPLATE_LABEL = {v["key"]: k for k, v in templates.items()}
            KEY_TO_TEMPLATE_LABEL["smoke"] = "冒烟测试"
            TEMPLATE_GUIDE = {k: v["guide"] for k, v in templates.items()}
        except Exception as e:
            print(f"Error loading providers.json: {e}")

    # 加载 CSS
    css_path = core.STATE_DIR / "style.css"
    if css_path.exists():
        CUSTOM_CSS = css_path.read_text(encoding="utf-8")
    else:
        CUSTOM_CSS = ""

_load_metadata()

EXAMPLE_INPUTS: List[List[str]] = [
    ["摘要总结", "请总结下面会议纪要并输出三条结论和三条行动项\n本周完成接口联调\n下周开始灰度发布\n风险是测试资源不足"],
    ["润色改写", "请把这段话改得专业但简洁 这个功能目前不够稳定 我们后续会持续优化"],
    ["信息抽取", "从以下文本提取日期 负责人 截止时间 王明二月二十八日前完成验收文档 李华三月一日提交测试报告"],
    ["自定义原样发送", "你是一名项目助理 请把我的需求拆成可执行清单"],
]

HISTORY_FILTERS = ["全部", "仅成功", "仅失败"]


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
        "Chorus-WebAI | 网页 AI 协同引擎 接口文档",
        "",
        "--- 核心架构特性 ---",
        "1. 多模型接力 (Relay)：支持使用 {prev_result} 引用前序任务输出",
        "2. 语义锚点 (Anchor)：内置 A11y 降级定位策略，增强对 UI 改版的抗性",
        "3. 视觉证据链 (Evidence)：自动记录错误现场快照与黑匣子日志",
        "",
        "--- 功能事件列表 ---",
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


async def _close_login_session() -> None:
    async with get_login_lock():
        ctx = LOGIN_STATE.get("context")
        p = LOGIN_STATE.get("p")
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:
                pass
        if p is not None:
            try:
                await p.stop()
            except Exception:
                pass
        LOGIN_STATE.update({"p": None, "context": None, "page": None})


async def _open_login_browser() -> Tuple[str, str]:
    cfg = core.load_config()
    try:
        async with get_login_lock():
            if LOGIN_STATE.get("context") is not None:
                return "登录浏览器已打开 请在该窗口完成登录", _build_guide_markdown()
            p, context, page = await core.open_chat_page(cfg)
            LOGIN_STATE.update({"p": p, "context": context, "page": page})
        return "已打开登录浏览器 请登录后回到本页面点击 登录完成检查", _build_guide_markdown()
    except Exception as exc:
        await _close_login_session()
        return (
            "打开浏览器失败 请先执行 .venv\\Scripts\\python.exe -m playwright install chromium 然后重试 错误 "
            f"{exc}",
            _build_guide_markdown(),
        )


async def _finish_login_check() -> Tuple[str, str]:
    async with get_login_lock():
        page = LOGIN_STATE.get("page")
        if page is None:
            return "未检测到登录会话 请先点击 打开登录浏览器", _build_guide_markdown()

    cfg = core.load_config()
    ok = await core.get_first_visible_locator(page, cfg["input_selectors"], timeout_ms=3500) is not None
    await _close_login_session()
    if ok:
        return "登录检查通过 会话已持久化保存", _build_guide_markdown()
    return "未检测到聊天输入框 请重新打开登录浏览器确认页面状态", _build_guide_markdown()


async def _run_smoke_test(smoke_confirm: bool, smoke_pause_seconds: int) -> Tuple[str, str]:
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
            await asyncio.sleep(pause_seconds)

        result = ""
        async for chunk in core.send_with_retry(run_cfg, "Reply with exactly: READY"):
            result = chunk
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


async def _one_click_prepare() -> Tuple[str, str]:
    msg, guide = await _open_login_browser()
    tip = "已执行自动准备 下一步请在新浏览器中登录 然后点击 登录完成检查 和 执行冒烟测试"
    return f"{tip}\n{msg}", guide


async def _run_task(template_label: str, user_input: str, confirmed: bool):
    raw_input = (user_input or "").strip()
    if not raw_input:
        yield "任务已取消 输入为空", "", "", "输入提示 请先填写任务内容", _history_table("全部")
        return

    LAST_INPUT["template"] = template_label
    LAST_INPUT["content"] = raw_input

    cfg = core.load_config()
    if cfg.get("confirm_before_send", True) and not confirmed:
        yield "请先勾选 我确认发送 后再执行", "", "", _input_tip(raw_input), _history_table("全部")
        return

    template_key = TEMPLATE_LABEL_TO_KEY.get(template_label, "custom")
    prompt = core.build_prompt(template_key, raw_input)
    run_cfg = copy.deepcopy(cfg)
    run_cfg["confirm_before_send"] = False

    started = time.time()
    response = ""
    try:
        async for chunk in core.send_with_retry(run_cfg, prompt):
            response = chunk
            elapsed = round(time.time() - started, 2)
            yield f"执行中... 用时 {elapsed} 秒，收到 {len(response)} 字", prompt[:3000], response, _input_tip(raw_input), _history_table("全部")
            
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
        yield status, prompt[:3000], response, _input_tip(raw_input), _history_table("全部")
    except Exception as exc:
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": template_key,
                "input_chars": len(raw_input),
                "response_chars": len(response),
                "duration_seconds": elapsed,
                "ok": False,
                "error": str(exc),
            }
        )
        yield f"执行失败 用时 {elapsed} 秒 错误 {exc}", prompt[:3000], response, _input_tip(raw_input), _history_table("全部")


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



async def _add_to_queue(template_label: str, user_input: str) -> str:
    raw_input = (user_input or "").strip()
    if not raw_input:
        return "提示: 任务内容为空，未加入队列"
    async with get_queue_lock():
        item = QueueItem(template_label=template_label, user_input=raw_input)
        TASK_QUEUE.append(item)
    return f"已成功加入队列 (ID: {item.id})，当前队列长度: {len(TASK_QUEUE)}"

def _render_queue_table() -> List[List[Any]]:
    return [[item.id, item.added_at, item.template_label, item.user_input[:20], item.status, item.result[:30]] for item in TASK_QUEUE]

async def _process_queue_once():
    async with get_queue_lock():
        pending = [item for item in TASK_QUEUE if item.status == "等待中"]
        if not pending:
            return "队列中没有等待执行的任务", _render_queue_table()
        
        # 获取当前任务及其索引
        current_idx = TASK_QUEUE.index(pending[0])
        target = TASK_QUEUE[current_idx]
        
        # 提取前序任务结果 (如果有的话)
        prev_result = ""
        if current_idx > 0:
            # 仅在明确引用时才注入
            prev_result = str(TASK_QUEUE[current_idx - 1].result)
        
        target.status = "执行中"
    
    cfg = core.load_config()
    run_cfg = copy.deepcopy(cfg)
    run_cfg["confirm_before_send"] = False
    template_key = TEMPLATE_LABEL_TO_KEY.get(target.template_label, "custom")
    
    # 动态注入前序结果 (处理可能存在的 Null 或异常)
    processed_input = target.user_input.replace("{prev_result}", prev_result)
    prompt = core.build_prompt(template_key, processed_input)

    started = time.time()
    response = ""
    ok = False
    try:
        async for chunk in core.send_with_retry(run_cfg, prompt):
            response = chunk
            target.result = f"收到 {len(response)} 字..."
        
        if not response:
            raise RuntimeError("Task executed but returned empty response.")
            
        target.status = "执行成功"
        target.result = response
        ok = True
    except Exception as exc:
        target.status = "执行失败"
        target.result = f"Error: {exc}"
        ok = False
    finally:
        elapsed = round(time.time() - started, 2)
        core.append_history(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "template": template_key,
                "input_chars": len(target.user_input),
                "response_chars": len(response),
                "duration_seconds": elapsed,
                "ok": ok,
                "error": str(target.result) if not ok else "",
            }
        )
    return f"任务 {target.id} 已处理完毕 ({target.status})", _render_queue_table()

async def _clear_queue():
    async with get_queue_lock():
        TASK_QUEUE.clear()
    return "队列已清空", _render_queue_table()

def build_ui() -> gr.Blocks:
    import gradio as gr
    provider_labels = [v["label"] for v in PROVIDERS.values()]

    with gr.Blocks(title="Chorus-WebAI | 网页 AI 协同引擎") as demo:
        gr.HTML(
            """
<div class='hero'>
  <div class='hero-title'>Chorus-WebAI</div>
  <div class='hero-sub'>跨平台 AI 协同引擎：让网页 AI 成为您的生产力突触</div>
  <div class='hero-chips'>
    <span class='hero-chip'>🎭 多模型接力 (Relay)</span>
    <span class='hero-chip'>📸 视觉证据链</span>
    <span class='hero-chip'>⚓ 语义锚点</span>
    <span class='hero-chip'>🛡️ 故障自愈</span>
  </div>
</div>
""".strip()
        )

        with gr.Tabs():
            with gr.Tab("🚀 快速上手"):
                with gr.Row():
                    with gr.Column(scale=2):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>操作向导</div>")
                            guide_markdown = gr.Markdown()
                            with gr.Row():
                                refresh_guide_btn = gr.Button("刷新进度", elem_classes=["action-secondary"])
                                one_click_btn = gr.Button("一键初始化环境", elem_classes=["action-primary"])
                    
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>智能特性</div>")
                            gr.Markdown(
                                """
- **链式接力**: `{prev_result}` 自动注入
- **自愈定位**: A11y 语义树 fallback
- **执行存证**: 自动生成错误快照
- **本地回退**: 支持 Ollama 离线方案
""".strip()
                            )

            with gr.Tab("⚙️ 平台与配置"):
                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>平台预设</div>")
                            provider_label = gr.Dropdown(provider_labels, value=PROVIDERS["deepseek"]["label"], label="目标平台")
                            apply_provider_btn = gr.Button("应用预设", elem_classes=["action-secondary"])
                            provider_guide = gr.Textbox(label="平台指引", lines=3, elem_classes=["provider-card"])

                    with gr.Column(scale=2):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>执行参数</div>")
                            with gr.Row():
                                target_url = gr.Textbox(label="入口地址", scale=2)
                                send_mode = gr.Radio(choices=[("回车", "enter"), ("点击", "button")], label="交互方式", scale=1)
                            with gr.Row():
                                confirm_before_send = gr.Checkbox(label="启用确认发送", value=True)
                                max_retries = gr.Slider(1, 6, 3, label="重试次数")
                                response_timeout = gr.Slider(30, 600, 120, label="超时限制 (s)")
                            save_btn = gr.Button("保存配置", elem_classes=["action-primary"])

                with gr.Row():
                    with gr.Column():
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>浏览器会话控制</div>")
                            with gr.Row():
                                open_login_btn = gr.Button("🔑 打开登录窗口", elem_classes=["action-secondary"])
                                finish_login_btn = gr.Button("✅ 登录状态验证", elem_classes=["action-secondary"])
                                smoke_btn = gr.Button("🔥 链路冒烟测试", elem_classes=["action-primary"])
                            with gr.Row():
                                smoke_confirm = gr.Checkbox(label="我已准备好测试")
                                smoke_pause = gr.Slider(0, 15, 3, label="测试前暂停 (s)")
                                setup_status = gr.Textbox(label="系统日志", lines=1)

            with gr.Tab("📝 执行任务"):
                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>任务编排</div>")
                            template_label = gr.Dropdown(list(TEMPLATE_LABEL_TO_KEY.keys()), value="摘要总结", label="任务模板")
                            template_help = gr.Markdown()
                            task_input = gr.Textbox(label="输入原始内容", lines=12, placeholder="在此粘贴文本或输入指令...")
                            input_tip = gr.Markdown()
                            send_confirm = gr.Checkbox(label="确认发送 (建议开启)", value=True)
                            with gr.Row():
                                run_btn = gr.Button("立即执行", elem_classes=["action-primary"])
                                reuse_btn = gr.Button("填入上次内容", elem_classes=["action-secondary"])

                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["section-card"]):
                            gr.Markdown("<div class='section-title'>执行反馈</div>")
                            run_status = gr.Textbox(label="执行进度", lines=1)
                            prompt_preview = gr.Textbox(label="提示词预览", lines=2, visible=False)
                            response_box = gr.Textbox(label="AI 响应内容", lines=18)
                            with gr.Row():
                                export_btn = gr.Button("导出 MD 报告", elem_classes=["action-secondary"])
                                export_file = gr.File(label="点击下载", interactive=False)
                                export_status = gr.Textbox(label="导出状态", lines=1, visible=False)

            with gr.Tab("📊 批量任务队列"):
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>添加链式任务</div>")
                    with gr.Row():
                        q_template = gr.Dropdown(list(TEMPLATE_LABEL_TO_KEY.keys()), value="摘要总结", label="模板")
                        q_input = gr.Textbox(label="内容 (支持 {prev_result})", scale=3)
                        q_add_btn = gr.Button("加入队列", elem_classes=["action-primary"], scale=1)
                        q_add_status = gr.Textbox(label="添加结果", lines=1, visible=False)
                
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("<div class='section-title'>队列监控</div>")
                    with gr.Row():
                        q_run_btn = gr.Button("▶ 执行首项", elem_classes=["action-primary"])
                        q_clear_btn = gr.Button("🗑️ 清空全部", elem_classes=["action-secondary"])
                        q_refresh_btn = gr.Button("🔄 刷新状态", elem_classes=["action-secondary"])
                    q_run_status = gr.Textbox(label="运行状态", lines=1)
                    q_grid = gr.Dataframe(headers=["ID", "添加时间", "模板", "预览", "状态", "结果"], interactive=False)

            with gr.Tab("🛠️ 诊断与历史"):
                with gr.Group(elem_classes=["section-card"]):
                    with gr.Row():
                        history_filter = gr.Radio(choices=HISTORY_FILTERS, value="全部", label="结果过滤")
                        refresh_history_btn = gr.Button("同步历史", elem_classes=["action-secondary"])
                    history_grid = gr.Dataframe(interactive=False)
                    with gr.Row():
                        health_btn = gr.Button("系统体检", elem_classes=["action-secondary"])
                        error_btn = gr.Button("日志回溯", elem_classes=["action-secondary"])
                        clear_history_btn = gr.Button("清空记录", elem_classes=["action-secondary"])
                    diag_box = gr.Textbox(label="控制台输出", lines=10, elem_classes=["provider-card"])

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


        q_add_btn.click(fn=_add_to_queue, inputs=[q_template, q_input], outputs=[q_add_status])
        q_refresh_btn.click(fn=_render_queue_table, outputs=[q_grid])
        q_clear_btn.click(fn=_clear_queue, outputs=[q_run_status, q_grid])
        q_run_btn.click(fn=_process_queue_once, outputs=[q_run_status, q_grid])
        demo.load(fn=_render_queue_table, outputs=[q_grid])

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
    # 确保元数据已加载，以便 build_ui 能正确渲染
    _load_metadata()
    import gradio as gr
    app = build_ui()
    app.queue(default_concurrency_limit=1)
    port = _pick_available_port(7860, 7875)
    
    app.launch(
        server_name="127.0.0.1", 
        server_port=port, 
        inbrowser=True, 
        theme=gr.themes.Soft(), 
        css=CUSTOM_CSS
    )


if __name__ == "__main__":
    main()
