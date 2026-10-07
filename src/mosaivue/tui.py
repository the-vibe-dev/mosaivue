from __future__ import annotations

from typing import Any

from .db import get_session_factory
from .renderer.rpc import RendererRPCClient, RendererRPCError
from .security import CredentialCipher, KeyManager
from .services.cameras import CameraService
from .services.capabilities import detect_capabilities
from .services.layouts import LayoutService
from .services.stream_probe import probe_stream


def run_tui() -> None:
    try:
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.containers import Horizontal, VerticalScroll
        from textual.screen import ModalScreen
        from textual.widgets import (
            Button,
            DataTable,
            Footer,
            Header,
            Input,
            Label,
            OptionList,
            Select,
            Static,
            TabbedContent,
            TabPane,
        )
    except ImportError as exc:
        raise RuntimeError("The Textual package is required for `mosaivue tui`") from exc

    cipher = CredentialCipher(KeyManager().load_or_create())

    class AddCameraScreen(ModalScreen[dict[str, str] | None]):
        CSS = """
        AddCameraScreen { align: center middle; }
        #dialog { width: 76; height: auto; border: round $accent; background: $surface; padding: 1 2; }
        #dialog Input { margin-bottom: 1; }
        #buttons { height: 3; align: right middle; }
        """

        def compose(self) -> ComposeResult:
            with VerticalScroll(id="dialog"):
                yield Label("Add RTSP camera", classes="title")
                yield Input(placeholder="Camera name", id="camera-name")
                yield Input(placeholder="rtsp:// or rtsps://camera/stream", id="camera-url")
                yield Input(placeholder="Username (optional)", id="camera-user")
                yield Input(placeholder="Password (optional)", password=True, id="camera-password")
                with Horizontal(id="buttons"):
                    yield Button("Cancel", id="cancel")
                    yield Button("Save", id="save", variant="primary")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "cancel":
                self.dismiss(None)
                return
            self.dismiss(
                {
                    "name": self.query_one("#camera-name", Input).value,
                    "url": self.query_one("#camera-url", Input).value,
                    "username": self.query_one("#camera-user", Input).value,
                    "password": self.query_one("#camera-password", Input).value,
                }
            )

    class MosaivueTUI(App[None]):
        TITLE = "Mosaivue"
        SUB_TITLE = "Camera wall appliance"
        CSS = """
        .title { text-style: bold; color: $accent; margin-bottom: 1; }
        .toolbar { height: 3; }
        DataTable { height: 1fr; }
        #summary { padding: 1 2; }
        """
        BINDINGS = [
            Binding("q", "quit", "Quit"),
            Binding("r", "refresh", "Refresh"),
            Binding("a", "add_camera", "Add camera"),
        ]

        def compose(self) -> ComposeResult:
            yield Header()
            with TabbedContent():
                with TabPane("Dashboard", id="dashboard"):
                    yield Static(id="summary")
                with TabPane("Cameras", id="cameras"):
                    with Horizontal(classes="toolbar"):
                        yield Button("Add camera", id="add-camera", variant="primary")
                        yield Button("Test selected", id="test-camera")
                        yield Button("Remove selected", id="remove-camera", variant="error")
                    yield DataTable(id="camera-table")
                with TabPane("Layouts", id="layouts"):
                    with Horizontal(classes="toolbar"):
                        yield Button("Activate selected", id="activate-layout", variant="primary")
                    yield DataTable(id="layout-table")
                with TabPane("System", id="system"):
                    yield Static(id="system-info")
            yield Footer()

        def on_mount(self) -> None:
            camera_table = self.query_one("#camera-table", DataTable)
            camera_table.add_columns("Name", "Location", "Profiles", "State", key="columns")
            layout_table = self.query_one("#layout-table", DataTable)
            layout_table.add_columns("Name", "Revision", "Slots", "Active", key="columns")
            self.action_refresh()

        def action_refresh(self) -> None:
            with get_session_factory()() as db:
                cameras = CameraService(db, cipher).list()
                layouts = LayoutService(db).list()
            camera_table = self.query_one("#camera-table", DataTable)
            camera_table.clear()
            for camera in cameras:
                camera_table.add_row(
                    camera.name,
                    camera.location or "—",
                    str(len(camera.stream_profiles)),
                    "enabled" if camera.enabled else "disabled",
                    key=camera.id,
                )
            layout_table = self.query_one("#layout-table", DataTable)
            layout_table.clear()
            with get_session_factory()() as db:
                service = LayoutService(db)
                for layout in layouts:
                    revision = service.current_revision(layout)
                    layout_table.add_row(
                        layout.name,
                        str(layout.current_revision),
                        str(len((revision.data if revision else {}).get("slots", []))),
                        "●" if layout.active else "",
                        key=layout.id,
                    )
            try:
                renderer = RendererRPCClient().call_sync("status")
            except RendererRPCError as exc:
                renderer = {"state": "UNAVAILABLE", "error": str(exc), "streams": {}}
            self.query_one("#summary", Static).update(
                f"Renderer: {renderer.get('state', 'unknown')}\n"
                f"Active layout: {renderer.get('active_layout_id') or 'none'}\n"
                f"Active streams: {len(renderer.get('streams', {}))}\n"
                f"Cameras: {len(cameras)}\nLayouts: {len(layouts)}"
            )
            capabilities = detect_capabilities()
            self.query_one("#system-info", Static).update(
                f"Platform: {capabilities.get('pi_model') or capabilities.get('platform')}\n"
                f"Kernel: {capabilities.get('kernel')}\n"
                f"Displays: {len(capabilities.get('displays', []))}\n"
                f"Recommended backend: {capabilities.get('recommended_backend')}\n"
                f"Recommended sink: {capabilities.get('recommended_sink')}"
            )

        def action_add_camera(self) -> None:
            self.push_screen(AddCameraScreen(), self._camera_added)

        def _camera_added(self, result: dict[str, str] | None) -> None:
            if not result:
                return
            from .schemas import CameraCreate, StreamProfileIn

            try:
                payload = CameraCreate(
                    name=result["name"],
                    username=result["username"] or None,
                    password=result["password"] or None,
                    stream_profiles=[StreamProfileIn(name="Main", url=result["url"])],
                )
                with get_session_factory()() as db:
                    CameraService(db, cipher).create(payload)
                    db.commit()
                self.notify("Camera saved", severity="information")
                self.action_refresh()
            except Exception as exc:
                self.notify(str(exc), severity="error")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "add-camera":
                self.action_add_camera()
            elif event.button.id == "activate-layout":
                table = self.query_one("#layout-table", DataTable)
                if table.cursor_row is None or table.row_count == 0:
                    return
                row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
                try:
                    RendererRPCClient().call_sync("apply_layout", layout_id=row_key)
                    with get_session_factory()() as db:
                        LayoutService(db).activate(row_key)
                        db.commit()
                    self.notify("Layout activated")
                    self.action_refresh()
                except Exception as exc:
                    self.notify(str(exc), severity="error")
            elif event.button.id == "test-camera":
                table = self.query_one("#camera-table", DataTable)
                if table.cursor_row is None or table.row_count == 0:
                    self.notify("Select a camera first", severity="warning")
                    return
                row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
                try:
                    with get_session_factory()() as db:
                        _, _, stream_url = CameraService(db, cipher).resolve_stream_url(row_key)
                        result = probe_stream(stream_url)
                    if result.get("success"):
                        dimensions = "x".join(
                            str(value) for value in (result.get("width"), result.get("height")) if value
                        )
                        summary = " · ".join(
                            str(value)
                            for value in (
                                result.get("codec"),
                                dimensions or None,
                                f"{result.get('time_to_first_frame_ms')} ms"
                                if result.get("time_to_first_frame_ms") is not None
                                else None,
                            )
                            if value
                        )
                        self.notify(f"Stream test passed: {summary or 'reachable'}")
                    else:
                        self.notify(
                            f"Stream test failed: {result.get('error') or 'unknown error'}",
                            severity="error",
                        )
                except Exception as exc:
                    self.notify(str(exc), severity="error")
            elif event.button.id == "remove-camera":
                table = self.query_one("#camera-table", DataTable)
                if table.cursor_row is None or table.row_count == 0:
                    return
                row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
                try:
                    with get_session_factory()() as db:
                        CameraService(db, cipher).delete(row_key)
                        db.commit()
                    self.notify("Camera removed")
                    self.action_refresh()
                except Exception as exc:
                    self.notify(str(exc), severity="error")

    MosaivueTUI().run()
