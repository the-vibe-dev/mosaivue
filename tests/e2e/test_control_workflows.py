"""Control-plane regressions. Run only against a disposable, seeded test appliance."""
from __future__ import annotations

import os
import shutil
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOSAIVUE_E2E_URL"), reason="MOSAIVUE_E2E_URL is not configured"
)


@pytest.fixture
def control_page():
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    base = os.environ["MOSAIVUE_E2E_URL"].rstrip("/")
    with sync_playwright() as playwright:
        executable = os.environ.get("MOSAIVUE_CHROMIUM_EXECUTABLE") or shutil.which("chromium") or shutil.which("chromium-browser")
        options = {"headless": True}
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.goto(base, wait_until="domcontentloaded")
        page.locator('[name="username"]').fill(os.environ["MOSAIVUE_E2E_USER"])
        page.locator('[name="password"]').fill(os.environ["MOSAIVUE_E2E_PASSWORD"])
        page.locator('#login-form button[type="submit"]').click()
        page.wait_for_selector(".dashboard-hero")
        yield page, base
        browser.close()


def test_camera_edit_retains_profiles_and_invalid_form_can_cancel(control_page):
    page, base = control_page
    before = page.request.get(f"{base}/api/v1/cameras").json()
    assert before, "Seed cameras before running this workflow"
    camera = before[0]
    page.locator('[data-nav="/cameras"]').click()
    page.locator(f'[data-camera-edit="{camera["id"]}"]').click()
    page.locator('dialog [name="name"]').fill("")
    page.get_by_role("button", name="Cancel", exact=True).click()
    assert page.locator("dialog[open]").count() == 0
    page.locator(f'[data-camera-edit="{camera["id"]}"]').click()
    page.get_by_role("button", name="Save changes", exact=True).click()
    page.wait_for_selector("dialog[open]", state="detached")
    after = page.request.get(f"{base}/api/v1/cameras/{camera['id']}").json()
    assert [profile["id"] for profile in after["stream_profiles"]] == [profile["id"] for profile in camera["stream_profiles"]]
    for old, new in zip(camera["stream_profiles"], after["stream_profiles"], strict=True):
        for field in ("codec", "fps", "bitrate", "width", "height"):
            assert new[field] == old[field]
    assert after["has_password"] == camera["has_password"]
    page.locator("#camera-filter").fill("no-camera-matches-this-unique-query")
    assert page.locator("[data-camera-row]:visible").count() == 0
    assert page.locator("#camera-no-matches").is_visible()


def test_schedule_create_edit_disable_and_delete(control_page):
    page, base = control_page
    assert page.request.get(f"{base}/api/v1/layouts").json(), "Seed a layout first"
    name = f"Browser QA {uuid.uuid4().hex[:8]}"
    page.locator('[data-nav="/schedules"]').click()
    page.get_by_role("button", name="New schedule", exact=True).click()
    page.locator('dialog [name="name"]').fill(name)
    page.locator('dialog [name="start"]').fill("22:00")
    page.locator('dialog [name="end"]').fill("06:00")
    page.locator('dialog [name="enabled"]').uncheck()
    page.get_by_role("button", name="Save schedule", exact=True).click()
    page.wait_for_selector("dialog[open]", state="detached")
    row = page.locator("tr").filter(has_text=name)
    assert "(+1 day)" in row.inner_text()
    row.get_by_role("button", name=f"Edit {name}", exact=True).click()
    page.locator('dialog [name="priority"]').fill("7")
    page.get_by_role("button", name="Save schedule", exact=True).click()
    page.wait_for_selector("dialog[open]", state="detached")
    saved = next(item for item in page.request.get(f"{base}/api/v1/schedules").json() if item["name"] == name)
    assert saved["priority"] == 7 and saved["enabled"] is False
    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name=f"Delete {name}", exact=True).click()
    page.wait_for_selector(f'[data-delete-schedule="{saved["id"]}"]', state="detached")
    assert all(item["name"] != name for item in page.request.get(f"{base}/api/v1/schedules").json())


def test_dirty_layout_navigation_requires_discard(control_page):
    page, _base = control_page
    page.locator('[data-nav="/layouts"]').click()
    page.locator('a[href$="/edit"]').first.click()
    page.locator(".canvas-slot").first.click()
    page.locator('[data-field="label"]').fill("Unsaved browser regression check")
    page.locator('[data-field="label"]').blur()
    assert "Unsaved changes" in page.locator(".editor-title-block").inner_text()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("link", name="Back to layouts", exact=True).click()
    assert page.locator(".layout-canvas").is_visible()
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("link", name="Back to layouts", exact=True).click()
    page.wait_for_selector(".layout-list")


def test_onvif_empty_form_cancel_and_mobile_navigation(control_page):
    page, _base = control_page
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.locator('[data-nav="/cameras"]').click()
    page.get_by_role("button", name="Import ONVIF", exact=True).click()
    assert page.get_by_role("heading", name="Import an ONVIF camera").is_visible()
    page.get_by_role("button", name="Cancel", exact=True).click()
    assert page.locator("dialog[open]").count() == 0
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Open navigation").click()
    page.locator('[data-nav="/schedules"]').click()
    page.get_by_role("heading", name="Schedules", exact=True).wait_for()
    assert not errors
