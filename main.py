from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import textwrap
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from src.core.dependencies import initialize_services
from src.core.templates import TEMPLATES
from src.utils.i18n import t

logger = logging.getLogger(__name__)

# History file size limit for rolling (10MB)
HISTORY_MAX_SIZE_BYTES = 10 * 1024 * 1024

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


def ensure_state() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ERROR_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    if not HISTORY_PATH.exists():
        HISTORY_PATH.touch()


def get_config_manager():
    """Backward compatibility alias for tests and legacy call sites."""
    from src.core.config import get_config_manager as _get_config_manager

    return _get_config_manager()


def load_config() -> Dict[str, Any]:
    ensure_state()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        return merged
    except Exception as exc:
        logger.warning(f"Failed to merge config, using defaults: {exc}")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=True, indent=2), encoding="utf-8")


def append_history(entry: Dict[str, Any]) -> None:
    # Check if rolling is needed before appending
    if HISTORY_PATH.exists():
        file_size = HISTORY_PATH.stat().st_size
        if file_size >= HISTORY_MAX_SIZE_BYTES:
            _roll_history()
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")


def _roll_history() -> None:
    """Roll history file by renaming current to timestamped backup."""
    if not HISTORY_PATH.exists():
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = HISTORY_PATH.parent / f"history_{timestamp}.jsonl"
    HISTORY_PATH.rename(backup_path)
    HISTORY_PATH.touch()
    logger.info(f"History rolled to {backup_path.name}")


def read_history(limit: int = 10) -> List[Dict[str, Any]]:
    """Read recent history entries using efficient file tail reading.

    Optimized to read only from the end of file, avoiding full file load.
    """
    if not HISTORY_PATH.exists():
        return []
    rows: List[Dict[str, Any]] = []

    # Read file from end using tail approach
    with HISTORY_PATH.open("r", encoding="utf-8") as f:
        # Seek to end to get file size
        f.seek(0, os.SEEK_END)
        file_size = f.tell()

        if file_size == 0:
            return []

        # Calculate position to start reading (estimate ~200 bytes per line)
        avg_line_size = 200
        read_size = min(limit * avg_line_size + 100, file_size)
        start_pos = max(0, file_size - read_size)

        # Read from calculated position
        f.seek(start_pos)
        if start_pos > 0:
            # Skip potentially partial first line
            f.readline()

        lines = f.readlines()

    # Iterate in reverse and stop early
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(rows) >= limit:
            break
    return rows


def ask_bool(message: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    raw = input(f"{message} {suffix}: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def choose_from_list(title: str, options: List[str]) -> int:
    print(f"\n{title}")
    for i, item in enumerate(options, start=1):
        print(f"  {i}) {item}")
    while True:
        raw = input("Choose number: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return idx - 1
        print("Invalid input. Try again.")


def collect_multiline(prompt: str) -> str:
    print(f"\n{prompt}")
    print("Input multiple lines, then type /end on a new line.")
    lines: List[str] = []
    while True:
        line = input()
        if line.strip() == "/end":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def build_prompt(template_key: str, user_input: str) -> str:
    if template_key == "custom":
        return user_input
    return TEMPLATES[template_key].format(user_input=user_input)


async def get_first_visible_locator(page, selectors: List[str], timeout_ms: int):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(timeout=timeout_ms)
            return locator
        except PlaywrightTimeoutError:
            continue
    return None


async def get_latest_response_text(page, selectors: List[str]) -> str:
    best = ""
    for selector in selectors:
        loc = page.locator(selector)
        count = await loc.count()
        if count <= 0:
            continue
        text = await loc.nth(count - 1).inner_text()
        text = text.strip()
        if len(text) > len(best):
            best = text
    return best


async def save_error_snapshot(page, error: Exception) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot_path = ERROR_DIR / f"error_{ts}.png"
    txt_path = ERROR_DIR / f"error_{ts}.txt"
    try:
        await page.screenshot(path=str(shot_path), full_page=True)
    except Exception as exc:
        logger.error(f"Snapshot failed: {exc}")
    txt_path.write_text(
        "\n".join(
            [
                f"time={datetime.now().isoformat()}",
                f"error={type(error).__name__}: {error}",
                "traceback:",
                traceback.format_exc(),
            ]
        ),
        encoding="utf-8",
    )
    return txt_path


async def wait_for_response(page, selectors: List[str], timeout_seconds: int, stable_seconds: int):
    start = time.time()
    last = ""
    last_change = time.time()

    while time.time() - start < timeout_seconds:
        try:
            current = await get_latest_response_text(page, selectors)
        except Exception as exc:
            logger.debug(f"Response wait failed: {exc}")
            current = ""

        if current and current != last:
            last = current
            last_change = time.time()
            yield last

        if last and (time.time() - last_change) >= stable_seconds:
            return

        await asyncio.sleep(1)

    raise TimeoutError(t("errors.timed_out_waiting_response"))


async def open_chat_page(config: Dict[str, Any]):
    p = await async_playwright().start()
    launch_kwargs = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "viewport": {"width": 1320, "height": 900},
    }
    preferred_channel = str(config.get("browser_channel", "msedge")).strip()
    if preferred_channel:
        try:
            context = await p.chromium.launch_persistent_context(channel=preferred_channel, **launch_kwargs)
        except Exception as exc:
            logger.warning(f"Failed to launch with channel {preferred_channel}, trying default: {exc}")
            context = await p.chromium.launch_persistent_context(**launch_kwargs)
    else:
        context = await p.chromium.launch_persistent_context(**launch_kwargs)
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(
        config["target_url"],
        wait_until="domcontentloaded",
        timeout=int(config["navigation_timeout_seconds"]) * 1000,
    )
    return p, context, page


async def first_login(config: Dict[str, Any]) -> None:
    logger.info("Opening browser for first login...")
    p, context, page = await open_chat_page(config)
    try:
        print("Please finish login in the browser.")
        input("After login and seeing chat input, press Enter here...")
        locator = await get_first_visible_locator(page, config["input_selectors"], timeout_ms=2500)
        if locator is None:
            logger.warning("Login check warning: chat input not found yet. You can continue and test with a task.")
        else:
            logger.info("Login check passed. Session should be saved.")
    finally:
        await context.close()
        await p.stop()


async def send_once(config: Dict[str, Any], prompt: str):
    p = None
    context = None
    page = None
    try:
        p, context, page = await open_chat_page(config)
        input_box = await get_first_visible_locator(page, config["input_selectors"], timeout_ms=4000)
        if input_box is None:
            raise RuntimeError(t("errors.chat_input_not_found"))

        await input_box.fill(prompt)

        if config.get("confirm_before_send", True):
            if not ask_bool("Ready to send this prompt?", default=True):
                raise RuntimeError(t("errors.canceled_by_user"))

        if config.get("send_mode") == "button":
            send_btn = await get_first_visible_locator(page, config["send_button_selectors"], timeout_ms=1200)
            if send_btn is not None:
                await send_btn.click()
            else:
                await input_box.press("Enter")
        else:
            await input_box.press("Enter")

        async for chunk in wait_for_response(
            page,
            selectors=config["assistant_selectors"],
            timeout_seconds=int(config["response_timeout_seconds"]),
            stable_seconds=int(config["stable_response_seconds"]),
        ):
            yield chunk
    except Exception as exc:
        logger.error(f"Send failed: {exc}")
        if page is not None:
            debug_path = await save_error_snapshot(page, exc)
            raise RuntimeError(t("errors.task_failed_debug", path=debug_path)) from exc
        raise
    finally:
        if context is not None:
            await context.close()
        if p is not None:
            await p.stop()


async def send_with_retry(config: Dict[str, Any], prompt: str):
    retries = max(1, int(config.get("max_retries", 3)))
    backoff = float(config.get("backoff_seconds", 1.5))
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            async for chunk in send_once(config, prompt):
                yield chunk
            return
        except Exception as exc:
            last_error = exc
            logger.debug(f"Attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                wait_s = backoff * (2 ** (attempt - 1))
                logger.debug(f"Retrying in {wait_s:.1f}s...")
                await asyncio.sleep(wait_s)

    raise RuntimeError(str(last_error) if last_error else "Unknown error")


async def run_task(config: Dict[str, Any]) -> None:
    keys = list(TEMPLATES.keys()) + ["custom"]
    idx = choose_from_list("Select task template", keys)
    template_key = keys[idx]
    user_input = collect_multiline("Enter your task content")
    if not user_input:
        logger.info("Empty input. Task canceled.")
        return

    final_prompt = build_prompt(template_key, user_input)
    logger.info("Prompt preview:")
    logger.info("-" * 70)
    logger.info(textwrap.shorten(final_prompt.replace("\n", " "), width=260, placeholder=" ..."))
    logger.info("-" * 70)

    started = time.time()
    print("\nResponse:\n")
    response = ""
    async for chunk in send_with_retry(config, final_prompt):
        print(chunk[len(response) :], end="", flush=True)
        response = chunk
    print()
    logger.info(f"Response complete, {len(response)} chars in {time.time() - started:.1f}s")
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
        logger.info(f"Smoke result: {result[:120]}")
    except Exception as exc:
        logger.warning(f"Setup step failed: {exc}")

    save_config(config)
    return config


async def async_main() -> None:
    ensure_state()
    # Initialize async services
    await initialize_services()

    config = load_config()

    while True:
        print("\n" + "=" * 70)
        print("Semi-Auto Web AI Agent")
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
            logger.error(f"Error: {exc}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExit.")
        sys.exit(0)
