"""
网页 AI 浏览器自动化核心模块 (Browser Automation Core)

本模块使用 Playwright 实现与各大网页 AI (如 DeepSeek, Kimi 等) 的半自动交互。
支持:
1. 持久化浏览器会话 (Browser Context Persistence)
2. 动态元素定位 (Dynamic Selectors)
3. 响应流式监控与稳定性检测 (Response Monitoring)
4. 任务重试与异常快照 (Retry & Snapshots)
"""

from __future__ import annotations

import json
import sys
import textwrap
import asyncio
import time
import traceback
import os
import httpx
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncGenerator

# 针对 Python 性能的优化：在非 Windows 环境下尝试使用 uvloop
if sys.platform != "win32":
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright, Page, Locator, BrowserContext, Playwright

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / ".semi_agent"
CONFIG_PATH = STATE_DIR / "config.json"
HISTORY_PATH = STATE_DIR / "history.jsonl"
ERROR_DIR = STATE_DIR / "errors"
PROFILE_DIR = STATE_DIR / "browser_profile"

DEFAULT_CONFIG: Dict[str, Any] = {
    "target_url": "https://chat.deepseek.com/",
    "browser_channel": "msedge",
    "send_mode": "enter",
    "confirm_before_send": True,
    "max_retries": 3,
    "backoff_seconds": 1.5,
    "input_selectors": [
        "textarea",
        "[contenteditable='true']",
        "textarea[placeholder*='message' i]",
        "textarea[placeholder*='chat' i]",
    ],
    "assistant_selectors": [
        "[data-role='assistant']",
        ".assistant",
        ".markdown",
        "article",
    ],
    "send_button_selectors": [
        "button[type='submit']",
        "button[aria-label*='send' i]",
    ],
    "navigation_timeout_seconds": 30,
    "response_timeout_seconds": 120,
    "stable_response_seconds": 3,
    "smoke_pause_seconds": 3,
}

TEMPLATES: Dict[str, str] = {
    "summary": "Summarize the following content in 5 bullets:\n\n{user_input}",
    "translation": "Translate the following text to Chinese and keep meaning precise:\n\n{user_input}",
    "rewrite": "Rewrite the following text to be clear and professional:\n\n{user_input}",
    "extract": "Extract key entities, dates, and action items from the following:\n\n{user_input}",
    "qa": "Answer the request below with concise steps:\n\n{user_input}",
}

def ensure_state() -> None:
    """初始化必要的状态目录和默认配置文件"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ERROR_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    if not HISTORY_PATH.exists():
        HISTORY_PATH.touch()


def load_config() -> Dict[str, Any]:
    """从磁盘加载配置，验证关键字段，若失败则返回默认值"""
    ensure_state()
    try:
        content = CONFIG_PATH.read_text(encoding="utf-8")
        if not content.strip():
            return DEFAULT_CONFIG.copy()
        data = json.loads(content)
        
        # 基础验证：确保 target_url 是合法的 URL
        url = str(data.get("target_url", "")).strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            print(f"Warning: Invalid target_url in config: {url}. Using default.")
            data["target_url"] = DEFAULT_CONFIG["target_url"]
            
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        return merged
    except json.JSONDecodeError:
        print("Warning: config.json is corrupted. Resetting to default.")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        print(f"Warning: Failed to load config: {e}. Using default.")
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    """保存配置到 config.json (UTF-8 编码)"""
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=True, indent=2), encoding="utf-8")


def append_history(entry: Dict[str, Any]) -> None:
    """追加任务记录到 history.jsonl"""
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")


def read_history(limit: int = 10) -> List[Dict[str, Any]]:
    """
    高效读取最近的 N 条历史记录。
    使用从文件末尾倒序读取的方式，避免 O(N) 内存占用。
    """
    if not HISTORY_PATH.exists() or HISTORY_PATH.stat().st_size == 0:
        return []

    rows: List[Dict[str, Any]] = []
    chunk_size = 4096
    
    with HISTORY_PATH.open("rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        buffer = bytearray()
        pointer = file_size
        
        while pointer > 0 and len(rows) < limit:
            step = min(pointer, chunk_size)
            pointer -= step
            f.seek(pointer)
            new_chunk = f.read(step)
            buffer = new_chunk + buffer
            
            # 从 buffer 中拆分行
            lines = buffer.splitlines()
            # 如果不是文件的开头，最后一行可能不完整，保留到下一次循环
            if pointer > 0:
                buffer = lines[0]
                to_process = lines[1:]
            else:
                buffer = bytearray()
                to_process = lines
                
            for line in reversed(to_process):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line.decode("utf-8")))
                    if len(rows) >= limit:
                        break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                    
    return rows


def ask_bool(message: str, default: bool = True) -> bool:
    """CLI 工具函数: 询问用户布尔值"""
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        raw = input(f"{message} {suffix}: ").strip().lower()
        if not raw:
            return default
        return raw in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return default


def choose_from_list(title: str, options: List[str]) -> int:
    """CLI 工具函数: 从列表中选择一项"""
    print(f"\n{title}")
    for i, item in enumerate(options, start=1):
        print(f"  {i}) {item}")
    while True:
        try:
            raw = input("Choose number: ").strip()
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(options):
                    return idx - 1
            print("Invalid input. Try again.")
        except (EOFError, KeyboardInterrupt):
            return 0


def collect_multiline(prompt: str) -> str:
    """CLI 工具函数: 收集多行输入直到遇到 /end"""
    print(f"\n{prompt}")
    print("Input multiple lines, then type /end on a new line.")
    lines: List[str] = []
    while True:
        try:
            line = input()
            if line.strip() == "/end":
                break
            lines.append(line)
        except (EOFError, KeyboardInterrupt):
            break
    return "\n".join(lines).strip()


def build_prompt(template_key: str, user_input: str) -> str:
    """根据模板 key 构建最终提示词"""
    if template_key == "custom":
        return user_input
    return TEMPLATES.get(template_key, "{user_input}").format(user_input=user_input)


async def get_first_visible_locator(page: Page, selectors: List[str], timeout_ms: int) -> Locator | None:
    """
    语义锚点定位策略 (Semantic Anchor Strategy):
    1. 尝试显式选择器 (CSS/XPath)
    2. 尝试 A11y 语义角色 (Textbox/Button)
    3. 尝试视觉占位符
    """
    # Step 1: 基础选择器
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(timeout=timeout_ms // 2, state="visible")
            return locator
        except PlaywrightTimeoutError:
            continue
            
    # Step 2: 语义降级 (Semantic Fallback)
    # 针对输入框
    if "textarea" in selectors[0]:
        for role in ["textbox", "searchbox"]:
            loc = page.get_by_role(role).first
            if await loc.count() > 0 and await loc.is_visible():
                return loc
                
    # Step 3: 视觉占位符降级
    placeholders = ["输入", "message", "chat", "问我", "ask"]
    for p in placeholders:
        loc = page.get_by_placeholder(p, exact=False).first
        if await loc.count() > 0 and await loc.is_visible():
            return loc
            
    return None


async def get_latest_response_text(page: Page, selectors: List[str]) -> str:
    """获取页面中最后一条助手回复的内容"""
    best = ""
    for selector in selectors:
        loc = page.locator(selector)
        try:
            count = await loc.count()
            if count <= 0:
                continue
            text = await loc.nth(count - 1).inner_text()
            text = text.strip()
            if len(text) > len(best):
                best = text
        except Exception:
            continue
    return best


async def save_error_snapshot(page: Page, error: Exception) -> Path:
    """当任务失败时，保存当前页面截图和错误堆栈信息"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot_path = ERROR_DIR / f"error_{ts}.png"
    txt_path = ERROR_DIR / f"error_{ts}.txt"
    try:
        await page.screenshot(path=str(shot_path), full_page=True)
    except Exception:
        pass
    
    error_info = [
        f"time={datetime.now().isoformat()}",
        f"error={type(error).__name__}: {error}",
        "traceback:",
        traceback.format_exc(),
    ]
    txt_path.write_text("\n".join(error_info), encoding="utf-8")
    return txt_path


async def wait_for_response(
    page: Page, 
    selectors: List[str], 
    timeout_seconds: int, 
    stable_seconds: int
) -> AsyncGenerator[str, None]:
    """
    监控助手回复的流式更新。
    当内容在 stable_seconds 内不再变化时，认为生成结束。
    """
    start = time.time()
    last = ""
    last_change = time.time()

    while time.time() - start < timeout_seconds:
        try:
            current = await get_latest_response_text(page, selectors)
        except Exception as e:
            # 记录异常但不中断，等待下一次尝试
            print(f"Warning during stream read: {e}")
            current = ""

        if current and current != last:
            last = current
            last_change = time.time()
            yield last
        elif not current and not last:
            # 初始阶段未获取到内容，不更新计时器
            pass

        if last and (time.time() - last_change) >= stable_seconds:
            # 内容已稳定超过预设时间，认为输出完毕
            return

        await asyncio.sleep(1)

    raise TimeoutError(f"Timed out after {timeout_seconds}s while waiting for response. Current length: {len(last)}")


async def open_chat_page(config: Dict[str, Any]) -> tuple[Playwright, BrowserContext, Page]:
    """使用持久化 Profile 打开浏览器页面，支持 Edge/Chrome 渠道"""
    p = await async_playwright().start()
    launch_kwargs = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "viewport": {"width": 1280, "height": 800},
    }
    preferred_channel = str(config.get("browser_channel", "msedge")).strip()
    
    # 探测到的硬路径回退
    HARD_CHROME_PATH = r"C:\Users\32806\AppData\Local\Google\Chrome\Application\chrome.exe"
    
    try:
        if preferred_channel:
            context = await p.chromium.launch_persistent_context(channel=preferred_channel, **launch_kwargs)
        else:
            context = await p.chromium.launch_persistent_context(**launch_kwargs)
    except Exception as e:
        print(f"Warning: Failed to launch with channel '{preferred_channel}': {e}.")
        print(f"Attempting hard path fallback: {HARD_CHROME_PATH}")
        try:
            # 移除 channel 参数，改用 executable_path
            fallback_kwargs = launch_kwargs.copy()
            fallback_kwargs["executable_path"] = HARD_CHROME_PATH
            context = await p.chromium.launch_persistent_context(**fallback_kwargs)
        except Exception as inner_e:
            print(f"Hard path fallback failed: {inner_e}. Final attempt with default chromium.")
            try:
                context = await p.chromium.launch_persistent_context(**launch_kwargs)
            except Exception as final_e:
                await p.stop()
                raise RuntimeError(f"Critical: Browser failed to launch after 3 attempts: {final_e}") from final_e
        
    if not context.pages:
        await context.new_page()
    page = context.pages[0]
    
    # 设置合理的超时限制
    page.set_default_timeout(30000)
    page.set_default_navigation_timeout(60000)
    
    try:
        await page.goto(
            config["target_url"],
            wait_until="domcontentloaded",
            timeout=int(config.get("navigation_timeout_seconds", 30)) * 1000,
        )
    except Exception as e:
        print(f"Navigation warning: {e}")
        
    return p, context, page


async def first_login(config: Dict[str, Any]) -> None:
    """引导式登录流程，让用户在浏览器中完成登录并保存会话"""
    print("\nOpening browser for first login...")
    p, context, page = await open_chat_page(config)
    try:
        print(f"Please finish login at {config['target_url']} in the browser.")
        input("After login and seeing chat input, press Enter here...")
        locator = await get_first_visible_locator(page, config["input_selectors"], timeout_ms=3000)
        if locator is None:
            print("Login check warning: chat input not found yet. You can continue and test with a task.")
        else:
            print("Login check passed. Session should be saved.")
    finally:
        await context.close()
        await p.stop()


async def send_once(config: Dict[str, Any], prompt: str) -> AsyncGenerator[str, None]:
    """执行单词发送与等待回复流程 (内部核心)"""
    p, context, page = await open_chat_page(config)
    try:
        input_box = await get_first_visible_locator(page, config["input_selectors"], timeout_ms=5000)
        if input_box is None:
            raise RuntimeError("Chat input not found. You may need to login again or update selectors.")

        await input_box.fill(prompt)

        if config.get("confirm_before_send", True):
            if not ask_bool("Ready to send this prompt?", default=True):
                raise RuntimeError("Canceled by user before send.")

        if config.get("send_mode") == "button":
            send_btn = await get_first_visible_locator(page, config["send_button_selectors"], timeout_ms=2000)
            if send_btn is not None:
                await send_btn.click()
            else:
                await input_box.press("Enter")
        else:
            await input_box.press("Enter")

        async for chunk in wait_for_response(
            page,
            selectors=config["assistant_selectors"],
            timeout_seconds=int(config.get("response_timeout_seconds", 120)),
            stable_seconds=int(config.get("stable_response_seconds", 3)),
        ):
            yield chunk
    except Exception as exc:
        debug_path = await save_error_snapshot(page, exc)
        raise RuntimeError(f"Task failed. Debug file: {debug_path}") from exc
    finally:
        await context.close()
        await p.stop()


async def send_local_ollama(config: Dict[str, Any], prompt: str) -> AsyncGenerator[str, None]:
    """
    本地 AI 接口实现 (针对 Ollama/OpenAI-compatible)
    作为网页端失效时的自动降级方案。
    """
    url = config.get("target_url", "http://localhost:11434/v1/chat/completions")
    payload = {
        "model": config.get("local_model", "llama3"),
        "messages": [{"role": "user", "content": prompt}],
        "stream": True
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"Ollama API Error: {response.status_code}")
                
                full_text = ""
                async for line in response.aiter_lines():
                    if not line.strip() or line.strip() == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            full_text += content
                            yield full_text
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            raise RuntimeError(f"Failed to connect to local AI (Ollama): {e}. Please ensure Ollama is running.")


async def send_with_retry(config: Dict[str, Any], prompt: str) -> AsyncGenerator[str, None]:
    """
    带重试与自动降级机制的发送流程。
    如果网页端重试失败，将自动尝试本地 AI (若配置)。
    """
    retries = max(1, int(config.get("max_retries", 3)))
    backoff = float(config.get("backoff_seconds", 1.5))
    last_error: Optional[Exception] = None
    
    # 检查是否为本地模式
    if config.get("send_mode") == "api":
        async for chunk in send_local_ollama(config, prompt):
            yield chunk
        return

    # 网页端重试循环
    for attempt in range(1, retries + 1):
        try:
            async for chunk in send_once(config, prompt):
                yield chunk
            return
        except Exception as exc:
            last_error = exc
            print(f"Attempt {attempt}/{retries} (Web) failed: {exc}")
            if attempt < retries:
                wait_s = backoff * (2 ** (attempt - 1))
                print(f"Retrying in {wait_s:.1f}s...")
                await asyncio.sleep(wait_s)
    
    # 网页端彻底失败，触发自动降级 (若非本地模式且存在本地配置)
    print("\n[Fallback] Web AI failed all retries. Attempting Local AI (Ollama) fallback...")
    try:
        # 临时切换到本地配置执行
        local_cfg = config.copy()
        local_cfg["target_url"] = "http://localhost:11434/v1/chat/completions"
        async for chunk in send_local_ollama(local_cfg, prompt):
            yield chunk
    except Exception as local_exc:
        print(f"[Fallback] Local AI also failed: {local_exc}")
        raise RuntimeError(f"Both Web and Local AI failed. Last Web Error: {last_error}")


async def run_task(config: Dict[str, Any]) -> None:
    keys = list(TEMPLATES.keys()) + ["custom"]
    idx = choose_from_list("Select task template", keys)
    template_key = keys[idx]
    user_input = collect_multiline("Enter your task content")
    if not user_input:
        print("Empty input. Task canceled.")
        return

    final_prompt = build_prompt(template_key, user_input)
    print("\nPrompt preview:")
    print("-" * 70)
    print(textwrap.shorten(final_prompt.replace("\n", " "), width=260, placeholder=" ..."))
    print("-" * 70)

    started = time.time()
    print("\nResponse:\n")
    response = ""
    async for chunk in send_with_retry(config, final_prompt):
        print(chunk[len(response):], end="", flush=True)
        response = chunk
    print()
    elapsed = time.time() - started

    append_history(
        {
            "time": datetime.now().isoformat(timespec="seconds"),
            "template": template_key,
            "input_chars": len(user_input),
            "response_chars": len(response),
            "duration_seconds": round(elapsed, 2),
            "ok": True,
        }
    )


def show_history() -> None:
    rows = read_history(limit=15)
    if not rows:
        print("No history yet.")
        return

    print("\nRecent history:")
    for i, row in enumerate(rows, start=1):
        print(
            f"{i:>2}. {row.get('time', '-')}, template={row.get('template', '-')}, "
            f"duration={row.get('duration_seconds', '-')}, "
            f"response_chars={row.get('response_chars', '-')}, ok={row.get('ok', False)}"
        )


def edit_config(config: Dict[str, Any]) -> Dict[str, Any]:
    while True:
        print("\nConfig")
        print(f"1) target_url = {config['target_url']}")
        print(f"2) send_mode = {config['send_mode']} (enter/button)")
        print(f"3) confirm_before_send = {config['confirm_before_send']}")
        print(f"4) max_retries = {config['max_retries']}")
        print(f"5) response_timeout_seconds = {config['response_timeout_seconds']}")
        print("0) Back")
        choice = input("Choose: ").strip()

        if choice == "0":
            save_config(config)
            return config
        if choice == "1":
            raw = input("New target_url: ").strip()
            if raw:
                config["target_url"] = raw
        elif choice == "2":
            raw = input("send_mode (enter/button): ").strip().lower()
            if raw in {"enter", "button"}:
                config["send_mode"] = raw
        elif choice == "3":
            config["confirm_before_send"] = ask_bool("Enable confirm_before_send?", bool(config["confirm_before_send"]))
        elif choice == "4":
            raw = input("max_retries (1-6): ").strip()
            if raw.isdigit() and 1 <= int(raw) <= 6:
                config["max_retries"] = int(raw)
        elif choice == "5":
            raw = input("response_timeout_seconds (30-600): ").strip()
            if raw.isdigit() and 30 <= int(raw) <= 600:
                config["response_timeout_seconds"] = int(raw)
        else:
            print("Invalid choice.")


async def quick_setup(config: Dict[str, Any]) -> Dict[str, Any]:
    print("\nQuick setup")
    print("Step 1/3: target page")
    if ask_bool("Use default target URL (https://chat.deepseek.com/)?", default=True):
        config["target_url"] = "https://chat.deepseek.com/"
    else:
        raw = input("Input target URL: ").strip()
        if raw:
            config["target_url"] = raw

    print("Step 2/3: login")
    await first_login(config)

    print("Step 3/3: run smoke test")
    smoke_prompt = "Reply with exactly: READY"
    try:
        result = ""
        async for chunk in send_with_retry(config, smoke_prompt):
            result = chunk
        print(f"Smoke result: {result[:120]}")
    except Exception as exc:
        print(f"Smoke test failed: {exc}")

    save_config(config)
    return config


async def async_main() -> None:
    ensure_state()
    config = load_config()

    while True:
        print("\n" + "=" * 70)
        print("Chorus-WebAI | 网页 AI 协同引擎")
        print("1) Quick setup (recommended)")
        print("2) First login only")
        print("3) Run task")
        print("4) Recent history")
        print("5) Settings")
        print("0) Exit")

        choice = input("Choose: ").strip()
        try:
            if choice == "1":
                config = await quick_setup(config)
            elif choice == "2":
                await first_login(config)
            elif choice == "3":
                await run_task(config)
            elif choice == "4":
                show_history()
            elif choice == "5":
                config = edit_config(config)
            elif choice == "0":
                print("Bye.")
                return
            else:
                print("Invalid choice.")
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
        except Exception as exc:
            print(f"Error: {exc}")


def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExit.")
        sys.exit(0)
