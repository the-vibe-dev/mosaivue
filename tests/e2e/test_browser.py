from __future__ import annotations

import os
import shutil

import pytest


@pytest.mark.skipif(not os.environ.get("MOSAIVUE_E2E_URL"), reason="MOSAIVUE_E2E_URL is not configured")
def test_authenticated_browser_workflow() -> None:
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    base = os.environ["MOSAIVUE_E2E_URL"].rstrip("/")
    username = os.environ["MOSAIVUE_E2E_USER"]
    password = os.environ["MOSAIVUE_E2E_PASSWORD"]
    with sync_playwright() as playwright:
        executable = os.environ.get("MOSAIVUE_CHROMIUM_EXECUTABLE") or shutil.which("chromium") or shutil.which("chromium-browser")
        launch_options = {"headless": True}
        if executable:
            launch_options["executable_path"] = executable
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.goto(base, wait_until="domcontentloaded")
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="password"]').fill(password)
        page.locator('#login-form button[type="submit"]').click()
        page.wait_for_selector(".dashboard-hero")
        page.goto(f"{base}/layouts", wait_until="domcontentloaded")
        page.wait_for_selector(".layout-row")
        page.locator('a[href$="/edit"]').first.click()
        page.wait_for_selector(".layout-canvas")
        box = page.locator(".layout-canvas").bounding_box()
        assert box and box["width"] > 400 and box["height"] > 200
        assert page.locator(".canvas-slot").count() >= 1
        page.locator(".canvas-slot").first.click()
        page.wait_for_selector(".canvas-slot.is-selected")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("Control+z")
        browser.close()
