from __future__ import annotations

import json
import sys
import textwrap
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

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
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ERROR_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    if not HISTORY_PATH.exists():
        HISTORY_PATH.touch()


def load_config() -> Dict[str, Any]:
    ensure_state()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        return merged
    except Exception:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=True, indent=2), encoding="utf-8")


def append_history(entry: Dict[str, Any]) -> None:
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")


def read_history(limit: int = 10) -> List[Dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    rows: List[Dict[str, Any]] = []
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


def get_first_visible_locator(page, selectors: List[str], timeout_ms: int):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(timeout=timeout_ms)
            return locator
        except PlaywrightTimeoutError:
            continue
    return None


def get_latest_response_text(page, selectors: List[str]) -> str:
    best = ""
    for selector in selectors:
        loc = page.locator(selector)
        count = loc.count()
        if count <= 0:
            continue
        text = loc.nth(count - 1).inner_text().strip()
        if len(text) > len(best):
            best = text
    return best


def save_error_snapshot(page, error: Exception) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot_path = ERROR_DIR / f"error_{ts}.png"
    txt_path = ERROR_DIR / f"error_{ts}.txt"
    try:
        page.screenshot(path=str(shot_path), full_page=True)
    except Exception:
        pass
    txt_path.write_text(
        "\n".join([
            f"time={datetime.now().isoformat()}",
            f"error={type(error).__name__}: {error}",
            "traceback:",
            traceback.format_exc(),
        ]),
        encoding="utf-8",
    )
    return txt_path


def wait_for_response(page, selectors: List[str], timeout_seconds: int, stable_seconds: int) -> str:
    start = time.time()
    last = ""
    last_change = time.time()

    while time.time() - start < timeout_seconds:
        try:
            current = get_latest_response_text(page, selectors)
        except Exception:
            current = ""

        if current and current != last:
            last = current
            last_change = time.time()

        if last and (time.time() - last_change) >= stable_seconds:
            return last

        time.sleep(1)

    raise TimeoutError("Timed out while waiting for response.")


def open_chat_page(config: Dict[str, Any]):
    p = sync_playwright().start()
    launch_kwargs = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "viewport": {"width": 1320, "height": 900},
    }
    preferred_channel = str(config.get("browser_channel", "msedge")).strip()
    if preferred_channel:
        try:
            context = p.chromium.launch_persistent_context(channel=preferred_channel, **launch_kwargs)
        except Exception:
            context = p.chromium.launch_persistent_context(**launch_kwargs)
    else:
        context = p.chromium.launch_persistent_context(**launch_kwargs)
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(
        config["target_url"],
        wait_until="domcontentloaded",
        timeout=int(config["navigation_timeout_seconds"]) * 1000,
    )
    return p, context, page


def first_login(config: Dict[str, Any]) -> None:
    print("\nOpening browser for first login...")
    p, context, page = open_chat_page(config)
    try:
        print("Please finish login in the browser.")
        input("After login and seeing chat input, press Enter here...")
        locator = get_first_visible_locator(page, config["input_selectors"], timeout_ms=2500)
        if locator is None:
            print("Login check warning: chat input not found yet. You can continue and test with a task.")
        else:
            print("Login check passed. Session should be saved.")
    finally:
        context.close()
        p.stop()


def send_once(config: Dict[str, Any], prompt: str) -> str:
    p, context, page = open_chat_page(config)
    try:
        input_box = get_first_visible_locator(page, config["input_selectors"], timeout_ms=4000)
        if input_box is None:
            raise RuntimeError("Chat input not found. You may need to login again or update selectors.")

        input_box.fill(prompt)

        if config.get("confirm_before_send", True):
            if not ask_bool("Ready to send this prompt?", default=True):
                raise RuntimeError("Canceled by user before send.")

        if config.get("send_mode") == "button":
            send_btn = get_first_visible_locator(page, config["send_button_selectors"], timeout_ms=1200)
            if send_btn is not None:
                send_btn.click()
            else:
                input_box.press("Enter")
        else:
            input_box.press("Enter")

        response = wait_for_response(
            page,
            selectors=config["assistant_selectors"],
            timeout_seconds=int(config["response_timeout_seconds"]),
            stable_seconds=int(config["stable_response_seconds"]),
        )
        return response
    except Exception as exc:
        debug_path = save_error_snapshot(page, exc)
        raise RuntimeError(f"Task failed. Debug file: {debug_path}") from exc
    finally:
        context.close()
        p.stop()


def send_with_retry(config: Dict[str, Any], prompt: str) -> str:
    retries = max(1, int(config.get("max_retries", 3)))
    backoff = float(config.get("backoff_seconds", 1.5))
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            return send_once(config, prompt)
        except Exception as exc:
            last_error = exc
            print(f"Attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                wait_s = backoff * (2 ** (attempt - 1))
                print(f"Retrying in {wait_s:.1f}s...")
                time.sleep(wait_s)

    raise RuntimeError(str(last_error) if last_error else "Unknown error")


def run_task(config: Dict[str, Any]) -> None:
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
    response = send_with_retry(config, final_prompt)
    elapsed = time.time() - started

    print("\nResponse:\n")
    print(response)

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


def quick_setup(config: Dict[str, Any]) -> Dict[str, Any]:
    print("\nQuick setup")
    print("Step 1/3: target page")
    if ask_bool("Use default target URL (https://chat.deepseek.com/)?", default=True):
        config["target_url"] = "https://chat.deepseek.com/"
    else:
        raw = input("Input target URL: ").strip()
        if raw:
            config["target_url"] = raw

    print("Step 2/3: login")
    first_login(config)

    print("Step 3/3: run smoke test")
    smoke_prompt = "Reply with exactly: READY"
    try:
        result = send_with_retry(config, smoke_prompt)
        print(f"Smoke result: {result[:120]}")
    except Exception as exc:
        print(f"Smoke test failed: {exc}")

    save_config(config)
    return config


def main() -> None:
    ensure_state()
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
                config = quick_setup(config)
            elif choice == "2":
                first_login(config)
            elif choice == "3":
                run_task(config)
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


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExit.")
        sys.exit(0)
