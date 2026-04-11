from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

if False:  # pragma: no cover
    from playwright.sync_api import Page

DEFAULT_PLAN: list[dict[str, Any]] = [
    {"action": "goto", "url": "https://chat.openai.com/"},
    {
        "action": "note",
        "message": "Log in manually in the opened browser window, then press Enter here.",
    },
    {"action": "pause"},
    {
        "action": "note",
        "message": "Example plan loaded. Replace plan.json with your own clicks and typing.",
    },
]


def load_plan(plan_path: Path | None) -> list[dict[str, Any]]:
    if plan_path is None:
        return DEFAULT_PLAN

    with plan_path.open("r", encoding="utf-8") as handle:
        plan = json.load(handle)

    if not isinstance(plan, list):
        raise ValueError("Plan file must contain a JSON list of steps.")

    return plan


def run_step(page: "Page", step: dict[str, Any]) -> None:
    action = step.get("action")

    if action == "goto":
        page.goto(step["url"], wait_until="domcontentloaded")
    elif action == "click":
        page.locator(step["selector"]).click()
    elif action == "fill":
        page.locator(step["selector"]).fill(step["text"])
    elif action == "type":
        delay = int(step.get("delay_ms", 50))
        page.locator(step["selector"]).press_sequentially(step["text"], delay=delay)
    elif action == "wait_for":
        page.locator(step["selector"]).wait_for()
    elif action == "sleep":
        page.wait_for_timeout(int(step.get("ms", 1000)))
    elif action == "pause":
        input("Press Enter to continue...")
    elif action == "note":
        print(step.get("message", ""))
    else:
        raise ValueError(f"Unsupported action: {action!r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quick local browser agent demo using Playwright and your own browser session.",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        help="Path to a JSON plan file. If omitted, a minimal ChatGPT login demo is used.",
    )
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep the browser open after running the plan.",
    )
    args = parser.parse_args()

    plan = load_plan(args.plan)

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Playwright is not installed. Run: pip install playwright && python -m playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, slow_mo=150)
        page = browser.new_page()

        for index, step in enumerate(plan, start=1):
            print(f"[{index}/{len(plan)}] {step.get('action', 'unknown')}")
            run_step(page, step)

        print("Done.")
        if args.keep_open:
            input("Browser left open. Press Enter to close it...")

        browser.close()


if __name__ == "__main__":
    main()
