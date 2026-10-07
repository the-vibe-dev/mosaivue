#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture authenticated Mosaivue screenshots")
    parser.add_argument("base_url", nargs="?", default=os.environ.get("MOSAIVUE_SCREENSHOT_URL", "http://127.0.0.1:8080"))
    parser.add_argument("output", nargs="?", default="docs/images")
    args = parser.parse_args()
    username = os.environ.get("MOSAIVUE_SCREENSHOT_USER")
    password = os.environ.get("MOSAIVUE_SCREENSHOT_PASSWORD")
    if not username or not password:
        raise SystemExit("Set MOSAIVUE_SCREENSHOT_USER and MOSAIVUE_SCREENSHOT_PASSWORD")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("Install development dependencies and run `playwright install chromium`") from exc

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        executable = os.environ.get("MOSAIVUE_CHROMIUM_EXECUTABLE") or shutil.which("chromium") or shutil.which("chromium-browser")
        launch_options = {"headless": True}
        if executable:
            launch_options["executable_path"] = executable
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.goto(args.base_url, wait_until="domcontentloaded")
        if page.locator("#setup-form").count():
            raise RuntimeError("Complete first-run setup before capturing screenshots")
        if page.locator("#login-form").count():
            page.locator('input[name="username"]').fill(username)
            page.locator('input[name="password"]').fill(password)
            page.locator('#login-form button[type="submit"]').click()
        page.wait_for_selector(".dashboard-hero")
        page.screenshot(path=output / "dashboard.png", full_page=True)

        page.goto(f"{args.base_url.rstrip('/')}/layouts", wait_until="domcontentloaded")
        page.wait_for_selector(".layout-row")
        page.locator('a[href$="/edit"]').first.click()
        page.wait_for_selector(".layout-canvas")
        page.screenshot(path=output / "layout-editor.png", full_page=True)

        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.goto(args.base_url, wait_until="domcontentloaded")
        if mobile.locator("#login-form").count():
            mobile.locator('input[name="username"]').fill(username)
            mobile.locator('input[name="password"]').fill(password)
            mobile.locator('#login-form button[type="submit"]').click()
        mobile.wait_for_selector(".app-shell")
        mobile.goto(f"{args.base_url.rstrip('/')}/remote", wait_until="domcontentloaded")
        mobile.wait_for_selector(".remote-shell")
        mobile.screenshot(path=output / "remote-mobile.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
