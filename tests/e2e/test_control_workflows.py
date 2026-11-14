"""Control-plane regressions. Run only against a disposable, seeded test appliance."""
from __future__ import annotations

import json
import os
import shutil
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOSAIVUE_E2E_URL"), reason="MOSAIVUE_E2E_URL is not configured"
)


@pytest.fixture(scope="module")
def authenticated_context():
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    base = os.environ["MOSAIVUE_E2E_URL"].rstrip("/")
    with sync_playwright() as playwright:
        executable = os.environ.get("MOSAIVUE_CHROMIUM_EXECUTABLE") or shutil.which("chromium") or shutil.which("chromium-browser")
        options = {"headless": True}
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = context.new_page()
        page.goto(base, wait_until="domcontentloaded")
        page.locator('[name="username"]').fill(os.environ["MOSAIVUE_E2E_USER"])
        page.locator('[name="password"]').fill(os.environ["MOSAIVUE_E2E_PASSWORD"])
        with page.expect_response("**/api/v1/auth/login") as login:
            page.locator('#login-form button[type="submit"]').click()
        assert login.value.status == 200
        page.wait_for_selector(".dashboard-hero")
        page.close()
        yield context, base
        browser.close()


@pytest.fixture
def control_page(authenticated_context):
    context, base = authenticated_context
    page = context.new_page()
    page.goto(base, wait_until="domcontentloaded")
    page.wait_for_selector(".dashboard-hero")
    yield page, base
    page.close()


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
    width = page.locator('[data-geometry="width"]')
    width.fill(str(float(width.input_value()) * 0.9))
    width.blur()
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


def test_saved_revision_can_apply_then_reapply_with_reported_renderer_state(control_page):
    """Exercises UI state using a mocked renderer; does not qualify HDMI playback."""
    page, base = control_page
    layouts = page.request.get(f"{base}/api/v1/layouts").json()
    assert layouts, "Seed a layout first"
    layout = layouts[0]
    old_revision = layout["current_revision"]
    layout["current_revision"] = old_revision + 1
    layout["active"] = True
    status = {"state": "RUNNING", "active_layout_id": layout["id"], "active_revision": old_revision, "streams": {}, "focused": False}
    applied = []
    page.route("**/api/v1/layouts", lambda route: route.fulfill(json=[layout]))
    page.route("**/api/v1/renderer/status", lambda route: route.fulfill(json=status))

    def apply(route):
        applied.append(route.request.method)
        status["active_revision"] = layout["current_revision"]
        route.fulfill(json={"layout": layout, "renderer": status})

    page.route(f"**/api/v1/layouts/{layout['id']}/activate", apply)
    page.locator('[data-nav="/layouts"]').click()
    row = page.locator(f'[data-layout-id="{layout["id"]}"]')
    row.locator('[data-layout-activate]').wait_for()
    assert row.get_attribute("data-display-state") == "pending"
    button = row.get_by_role("button", name="Apply saved changes", exact=True)
    assert button.is_enabled()
    button.click()
    row.get_by_role("button", name="Reapply", exact=True).wait_for()
    assert row.get_attribute("data-display-state") == "applied"
    assert row.get_by_role("button", name="Reapply", exact=True).is_enabled()
    assert applied == ["POST"]


def test_json_import_uses_configuration_route_and_retains_display_warning(control_page):
    """Intercepts the import API so no existing appliance configuration is replaced."""
    page, _base = control_page
    requests = []

    def imported(route):
        requests.append(route.request.post_data_json)
        route.fulfill(json={"imported": {"cameras": 1}, "renderer_applied": False, "renderer_warning": "Fixture renderer is offline"})

    page.route("**/api/v1/backup/import", imported)
    page.locator('[data-nav="/backup"]').click()
    document = {"format": "mosaivue", "cameras": [{"name": "Fixture camera"}]}
    page.locator("#restore-file").set_input_files({"name": "configuration.json", "mimeType": "application/json", "buffer": json.dumps(document).encode()})
    page.get_by_role("heading", name="Import JSON configuration", exact=True).wait_for()
    assert page.locator('dialog [name="mode"][value="merge"]').is_checked()
    page.get_by_role("button", name="Validate and import", exact=True).click()
    page.wait_for_selector("dialog[open]", state="detached")
    assert "Fixture renderer is offline" in page.locator("#restore-result").inner_text()
    assert requests == [{"document": document, "merge": True}]


def test_unsupported_display_controls_are_disabled_and_explained(control_page):
    page, _base = control_page
    page.route("**/api/v1/renderer/status", lambda route: route.fulfill(json={
        "state": "RUNNING", "backend": "omxplayer", "streams": {},
        "capabilities": {"name": "omxplayer", "available": True, "feature_support": {
            "output_selection": False, "refresh_rate": False, "portrait": False,
            "prevent_blanking": False, "labels": False, "native_size": False,
        }},
    }))
    page.locator('[data-nav="/display"]').click()
    page.get_by_role("button", name="New profile", exact=True).click()
    for name in ("output", "refresh", "rotation", "blanking"):
        assert page.locator(f'dialog [name="{name}"]').is_disabled()
    assert page.locator('dialog [name="width"]').is_enabled()
    assert "unsupported or not reported" in page.locator("dialog").inner_text()
    page.get_by_role("button", name="Cancel", exact=True).click()
    page.locator('[data-nav="/layouts"]').click()
    page.locator('a[href$="/edit"]').first.click()
    page.locator(".canvas-slot").first.click()
    assert page.locator('[data-field="label"]').is_disabled()
    assert page.locator('[data-field="aspect_mode"] option[value="native"]').is_disabled()
    page.set_viewport_size({"width": 390, "height": 844})
    assert not page.locator("#editor-tile-inspector").is_visible()
    page.get_by_role("button", name="Tile", exact=True).click()
    assert page.locator("#editor-tile-inspector").is_visible()
    assert page.locator('[data-field="label"]').is_disabled()
    inspector = page.locator("#editor-tile-inspector").bounding_box()
    selected_tile = page.locator(".canvas-slot.is-selected").bounding_box()
    assert inspector and selected_tile
    left = max(inspector["x"], selected_tile["x"])
    top = max(inspector["y"], selected_tile["y"])
    right = min(inspector["x"] + inspector["width"], selected_tile["x"] + selected_tile["width"])
    bottom = min(inspector["y"] + inspector["height"], selected_tile["y"] + selected_tile["height"])
    assert right - left > 20 and bottom - top > 20
    assert page.evaluate(
        "({ x, y }) => Boolean(document.elementFromPoint(x, y)?.closest('#editor-tile-inspector'))",
        {"x": (left + right) / 2, "y": (top + bottom) / 2},
    )
    page.get_by_role("button", name="Close inspector", exact=True).click()
    assert not page.locator("#editor-tile-inspector").is_visible()
    page.get_by_role("button", name="Cameras", exact=True).click()
    assert page.locator("#editor-camera-library").is_visible()
    page.get_by_role("button", name="Close camera library", exact=True).click()
    assert not page.locator("#editor-camera-library").is_visible()


def test_display_profile_edit_assignment_and_custom_dimensions(control_page):
    """Uses real configuration APIs but never applies a layout to physical output."""
    page, base = control_page
    suffix = uuid.uuid4().hex[:8]
    profile_name, layout_name = f"QA dimensions {suffix}", f"QA profile wall {suffix}"
    headers = {"X-CSRF-Token": page.request.get(f"{base}/api/v1/auth/me").json()["csrf_token"]}
    profile_id = layout_id = None
    try:
        page.locator('[data-nav="/display"]').click()
        page.get_by_role("button", name="New profile", exact=True).click()
        page.locator('dialog [name="name"]').fill(profile_name)
        page.locator('dialog [name="width"]').fill("800")
        page.locator('dialog [name="height"]').fill("600")
        page.get_by_role("button", name="Create profile", exact=True).click()
        page.wait_for_selector("dialog[open]", state="detached")
        profile_id = next(item["id"] for item in page.request.get(f"{base}/api/v1/display/profiles").json() if item["name"] == profile_name)
        page.locator('[data-nav="/layouts"]').click()
        page.get_by_role("button", name="New layout", exact=True).click()
        page.locator('dialog [name="name"]').fill(layout_name)
        page.locator('dialog [name="layout_display_profile"]').select_option(profile_id)
        assert page.locator('dialog [name="layout_output_width"]').is_disabled()
        with page.expect_response(lambda response: response.url.endswith("/api/v1/layouts") and response.request.method == "POST") as created:
            page.get_by_role("button", name="Create and edit", exact=True).click()
        assert created.value.status == 201
        layout_id = created.value.json()["id"]
        page.wait_for_selector('.display-frame[data-render-width="800"][data-render-height="600"]')
        page.get_by_role("link", name="Back to layouts", exact=True).click()
        page.locator('[data-nav="/display"]').click()
        row = page.locator(f'[data-display-profile="{profile_id}"]')
        assert row.get_by_role("button", name=f"Delete {profile_name}", exact=True).is_disabled()
        row.get_by_role("button", name=f"Edit {profile_name}", exact=True).click()
        page.locator('dialog [name="width"]').fill("1024")
        page.locator('dialog [name="height"]').fill("768")
        page.get_by_role("button", name="Save profile", exact=True).click()
        page.wait_for_selector("dialog[open]", state="detached")
        row.get_by_role("link", name=layout_name, exact=True).click()
        page.wait_for_selector('.display-frame[data-render-width="1024"][data-render-height="768"]')
        # Simulate another operator changing this shared profile while the editor stays open.
        changed = page.request.put(f"{base}/api/v1/display/profiles/{profile_id}", headers={**headers, "Content-Type": "application/json"}, data=json.dumps({"name": profile_name, "width": 1280, "height": 720}))
        assert changed.status == 200
        page.get_by_role("button", name="Refresh status", exact=True).click()
        page.wait_for_selector('.display-frame[data-render-width="1280"][data-render-height="720"]')
        page.get_by_role("button", name="Layout settings", exact=True).click()
        page.locator('dialog [name="layout_display_profile"]').select_option("")
        page.locator('dialog [name="layout_output_width"]').fill("1440")
        page.locator('dialog [name="layout_output_height"]').fill("900")
        page.get_by_role("button", name="Update draft settings", exact=True).click()
        page.wait_for_selector('.display-frame[data-render-width="1440"][data-render-height="900"]')
        assert "Unsaved changes" in page.locator(".editor-title-block").inner_text()
        with page.expect_response(lambda response: response.url.endswith(f"/api/v1/layouts/{layout_id}") and response.request.method == "PUT") as saved:
            page.get_by_role("button", name="Save draft", exact=True).click()
        assert saved.value.status == 200
        result = saved.value.json()
        assert result["display_profile_id"] is None
        assert result["revision"]["data"]["output_width"] == 1440
        assert result["revision"]["data"]["output_height"] == 900
        assert saved.value.request.post_data_json["expected_revision_id"]
    finally:
        if layout_id:
            assert page.request.delete(f"{base}/api/v1/layouts/{layout_id}", headers=headers).status == 204
        if profile_id:
            assert page.request.delete(f"{base}/api/v1/display/profiles/{profile_id}", headers=headers).status == 204


def test_concurrent_editor_save_preserves_local_work_and_can_create_copy(control_page):
    """Two authenticated pages edit one disposable draft; no renderer apply occurs."""
    page, base = control_page
    headers = {"X-CSRF-Token": page.request.get(f"{base}/api/v1/auth/me").json()["csrf_token"]}
    name = f"QA conflict {uuid.uuid4().hex[:8]}"
    created = page.request.post(f"{base}/api/v1/layouts", headers={**headers, "Content-Type": "application/json"}, data=json.dumps({"name": name, "data": {"slots": [], "output_width": 1920, "output_height": 1080}}))
    assert created.status == 201
    layout_id = created.json()["id"]
    copy_id = None
    second = page.context.new_page()
    try:
        page.goto(f"{base}/layouts/{layout_id}/edit", wait_until="domcontentloaded")
        second.goto(f"{base}/layouts/{layout_id}/edit", wait_until="domcontentloaded")
        for tab, width in ((page, "1440"), (second, "1600")):
            tab.get_by_role("button", name="Layout settings", exact=True).click()
            tab.locator('dialog [name="layout_output_width"]').fill(width)
            tab.get_by_role("button", name="Update draft settings", exact=True).click()
        with second.expect_response(lambda response: response.url.endswith(f"/api/v1/layouts/{layout_id}") and response.request.method == "PUT") as saved:
            second.get_by_role("button", name="Save draft", exact=True).click()
        assert saved.value.status == 200
        with page.expect_response(lambda response: response.url.endswith(f"/api/v1/layouts/{layout_id}") and response.request.method == "PUT") as rejected:
            page.get_by_role("button", name="Save draft", exact=True).click()
        assert rejected.value.status == 409
        page.locator("[data-save-error]").wait_for()
        assert "unsaved edits are still open" in page.locator("[data-save-error]").inner_text()
        assert page.locator(".display-frame").get_attribute("data-render-width") == "1440"
        assert page.get_by_role("button", name="Save draft", exact=True).is_disabled()
        page.get_by_role("button", name="Save my edits as a copy", exact=True).click()
        with page.expect_response(lambda response: response.url.endswith("/api/v1/layouts") and response.request.method == "POST") as copied:
            page.get_by_role("button", name="Create copy", exact=True).click()
        assert copied.value.status == 201
        copy_id = copied.value.json()["id"]
        page.wait_for_url(f"{base}/layouts/{copy_id}/edit")
        original = page.request.get(f"{base}/api/v1/layouts/{layout_id}").json()
        assert original["revision"]["data"]["output_width"] == 1600
        assert copied.value.json()["revision"]["data"]["output_width"] == 1440
    finally:
        second.close()
        if copy_id:
            assert page.request.delete(f"{base}/api/v1/layouts/{copy_id}", headers=headers).status == 204
        assert page.request.delete(f"{base}/api/v1/layouts/{layout_id}", headers=headers).status == 204
