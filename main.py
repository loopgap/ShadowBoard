"""
Chorus-WebAI Main Entry Point (Refactored)

This module provides the CLI interface while delegating to the new modular architecture.
"""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "2.3.0"

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.core.config import get_config_manager
from src.core.browser import get_first_visible_locator, get_latest_response_text
from src.services.task_tracker import TaskTracker
from src.services.memory_store import MemoryStore, SessionManager
from src.services.workflow import WorkflowEngine
from src.services.monitor import Monitor
from src.utils.helpers import build_prompt

# Legacy imports for backward compatibility
import json
import textwrap
import asyncio
import time
import traceback
import os
import httpx
from datetime import datetime
from typing import Any, Dict, List, Optional, AsyncGenerator

from playwright.async_api import async_playwright, Page, BrowserContext, Playwright

# Legacy constants (for backward compatibility)
ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / ".semi_agent"
CONFIG_PATH = STATE_DIR / "config.json"
HISTORY_PATH = STATE_DIR / "history.jsonl"
ERROR_DIR = STATE_DIR / "errors"
PROFILE_DIR = STATE_DIR / "browser_profile"

# Legacy templates
TEMPLATES: Dict[str, str] = {
    "summary": "Summarize the following content in 5 bullets:\n\n{user_input}",
    "translation": "Translate the following text to Chinese and keep meaning precise:\n\n{user_input}",
    "rewrite": "Rewrite the following text to be clear and professional:\n\n{user_input}",
    "extract": "Extract key entities, dates, and action items from the following:\n\n{user_input}",
    "qa": "Answer the request below with concise steps:\n\n{user_input}",
}

# Global service instances
_task_tracker: Optional[TaskTracker] = None
_memory_store: Optional[MemoryStore] = None
_session_manager: Optional[SessionManager] = None
_workflow_engine: Optional[WorkflowEngine] = None
_monitor: Optional[Monitor] = None


def get_task_tracker() -> TaskTracker:
    """Get or create the global TaskTracker instance."""
    global _task_tracker
    if _task_tracker is None:
        _task_tracker = TaskTracker()
    return _task_tracker


def get_memory_store() -> MemoryStore:
    """Get or create the global MemoryStore instance."""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store


def get_session_manager() -> SessionManager:
    """Get or create the global SessionManager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(get_memory_store())
    return _session_manager


def get_workflow_engine() -> WorkflowEngine:
    """Get or create the global WorkflowEngine instance."""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine


def get_monitor() -> Monitor:
    """Get or create the global Monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = Monitor()
    return _monitor


# ============== Legacy Functions (for backward compatibility) ==============

def ensure_state() -> None:
    """Initialize necessary state directories and default config file."""
    config = get_config_manager()
    config.state_dir.mkdir(parents=True, exist_ok=True)
    config.error_dir.mkdir(parents=True, exist_ok=True)
    config.profile_dir.mkdir(parents=True, exist_ok=True)
    if not config.config_path.exists():
        config._save_config(config.get_all())
    if not config.history_path.exists():
        config.history_path.touch()


def load_config() -> Dict[str, Any]:
    """Load configuration from disk."""
    return get_config_manager().get_all()


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to config.json."""
    get_config_manager().update(config, save=True)


def append_history(entry: Dict[str, Any]) -> None:
    """Append task record to history.jsonl."""
    config = get_config_manager()
    with config.history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")


def read_history(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Efficiently read the last N history records.
    Uses reverse file reading to avoid O(N) memory usage.
    """
    config = get_config_manager()
    if not config.history_path.exists() or config.history_path.stat().st_size == 0:
        return []

    rows: List[Dict[str, Any]] = []
    chunk_size = 4096
    
    with config.history_path.open("rb") as f:
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
            
            lines = buffer.splitlines()
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


# ============== CLI Helper Functions ==============

def ask_bool(message: str, default: bool = True) -> bool:
    """CLI utility: ask user for boolean input."""
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        raw = input(f"{message} {suffix}: ").strip().lower()
        if not raw:
            return default
        return raw in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return default


def choose_from_list(title: str, options: List[str]) -> int:
    """CLI utility: choose from a list."""
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
    """CLI utility: collect multiline input until /end."""
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


# ============== Browser Functions ==============

async def open_chat_page(config: Dict[str, Any]) -> tuple[Playwright, BrowserContext, Page]:
    """Open browser page with persistent profile."""
    config_mgr = get_config_manager()
    p = await async_playwright().start()
    launch_kwargs = {
        "user_data_dir": str(config_mgr.profile_dir),
        "headless": False,
        "viewport": {"width": 1280, "height": 800},
    }
    preferred_channel = str(config.get("browser_channel", "msedge")).strip()
    
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


async def save_error_snapshot(page: Page, error: Exception) -> Path:
    """Save screenshot and error trace when task fails."""
    config = get_config_manager()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot_path = config.error_dir / f"error_{ts}.png"
    txt_path = config.error_dir / f"error_{ts}.txt"
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
    """Monitor assistant response stream."""
    start = time.time()
    last = ""
    last_change = time.time()

    while time.time() - start < timeout_seconds:
        try:
            current = await get_latest_response_text(page, selectors)
        except Exception as e:
            print(f"Warning during stream read: {e}")
            current = ""

        if current and current != last:
            last = current
            last_change = time.time()
            yield last
        elif not current and not last:
            pass

        if last and (time.time() - last_change) >= stable_seconds:
            return

        await asyncio.sleep(1)

    raise TimeoutError(f"Timed out after {timeout_seconds}s while waiting for response. Current length: {len(last)}")


async def first_login(config: Dict[str, Any]) -> None:
    """Guided login flow."""
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
    """Execute single send and wait for response."""
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
    """Local AI interface implementation (Ollama/OpenAI-compatible)."""
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
    """Send with retry and automatic fallback to local AI."""
    retries = max(1, int(config.get("max_retries", 3)))
    backoff = float(config.get("backoff_seconds", 1.5))
    last_error: Optional[Exception] = None
    
    # Check if API mode
    if config.get("send_mode") == "api":
        async for chunk in send_local_ollama(config, prompt):
            yield chunk
        return

    # Web retry loop
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
    
    # Fallback to local AI
    print("\n[Fallback] Web AI failed all retries. Attempting Local AI (Ollama) fallback...")
    try:
        local_cfg = config.copy()
        local_cfg["target_url"] = "http://localhost:11434/v1/chat/completions"
        async for chunk in send_local_ollama(local_cfg, prompt):
            yield chunk
    except Exception as local_exc:
        print(f"[Fallback] Local AI also failed: {local_exc}")
        raise RuntimeError(f"Both Web and Local AI failed. Last Web Error: {last_error}")


# ============== Task Execution with Tracking ==============

async def run_task_tracked(config: Dict[str, Any], template_key: str, user_input: str) -> str:
    """
    Execute a task with full tracking via the new TaskTracker service.
    Returns the response text.
    """
    tracker = get_task_tracker()
    monitor = get_monitor()
    
    # Create task
    task = await tracker.create_task(
        template_key=template_key,
        user_input=user_input,
        prompt=build_prompt(template_key, user_input),
    )
    
    # Start execution
    await tracker.start_task(task.id)
    
    started = time.time()
    response = ""
    
    try:
        async for chunk in send_with_retry(config, task.prompt):
            response = chunk
        
        await tracker.complete_task(task.id, response)
        monitor.record_task_execution(True, time.time() - started, template_key)
        
        # Record to history
        append_history({
            "time": datetime.now().isoformat(timespec="seconds"),
            "template": template_key,
            "input_chars": len(user_input),
            "response_chars": len(response),
            "duration_seconds": round(time.time() - started, 2),
            "ok": True,
            "task_id": task.id,
        })
        
    except Exception as e:
        await tracker.fail_task(task.id, str(e))
        monitor.record_task_execution(False, time.time() - started, template_key)
        
        append_history({
            "time": datetime.now().isoformat(timespec="seconds"),
            "template": template_key,
            "input_chars": len(user_input),
            "response_chars": 0,
            "duration_seconds": round(time.time() - started, 2),
            "ok": False,
            "error": str(e),
            "task_id": task.id,
        })
        raise
    
    return response


async def run_task(config: Dict[str, Any]) -> None:
    """Run interactive task (legacy CLI mode)."""
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
    """Display recent history."""
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
    """Interactive config editor."""
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
    """Guided quick setup."""
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
    """Main CLI entry point."""
    ensure_state()
    config = load_config()

    while True:
        print("\n" + "=" * 70)
        print("Chorus-WebAI | Web AI Orchestration Engine v2.3")
        print("1) Quick setup (recommended)")
        print("2) First login only")
        print("3) Run task")
        print("4) Recent history")
        print("5) Settings")
        print("6) Task statistics")
        print("7) System health")
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
            elif choice == "6":
                tracker = get_task_tracker()
                stats = tracker.get_statistics()
                print("\nTask Statistics:")
                for k, v in stats.items():
                    print(f"  {k}: {v}")
            elif choice == "7":
                monitor = get_monitor()
                health = monitor.get_system_health()
                print(f"\nSystem Health: {'Healthy' if health.healthy else 'Issues detected'}")
                print(f"Message: {health.message}")
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
    """Entry point."""
    asyncio.run(async_main())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExit.")
        sys.exit(0)
