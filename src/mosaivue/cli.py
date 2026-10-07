from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from . import __version__
from .api.app import main as serve_main
from .config import load_settings
from .constants import CONFIG_DIR, DATA_DIR
from .db import get_session_factory, init_db
from .logging_utils import configure_logging, redact
from .models import Layout
from .renderer.daemon import main as renderer_main
from .renderer.rpc import RendererRPCClient, RendererRPCError
from .schemas import (
    CameraCreate,
    CameraUpdate,
    LayoutCreate,
    LayoutData,
    LayoutUpdate,
    StreamProfileIn,
)
from .security import CredentialCipher, KeyManager
from .services.backup import create_backup, export_configuration, import_configuration, read_backup
from .services.benchmark import BenchmarkUnavailable, synthetic_benchmark
from .services.cameras import CameraService
from .services.capabilities import detect_capabilities, write_capabilities
from .services.diagnostics import build_support_bundle, security_audit
from .services.layouts import LayoutService
from .services.migration_displaycameras import build_plan, discover_files
from .services.stream_probe import StreamProbeUnavailable, probe_stream

app = typer.Typer(no_args_is_help=True, help="Mosaivue camera-monitor appliance")
camera_app = typer.Typer(no_args_is_help=True, help="Manage saved cameras")
layout_app = typer.Typer(no_args_is_help=True, help="Manage layouts")
rotation_app = typer.Typer(no_args_is_help=True, help="Control rotation")
renderer_app = typer.Typer(no_args_is_help=True, help="Manage the renderer")
config_app = typer.Typer(no_args_is_help=True, help="Validate and inspect configuration")
security_app = typer.Typer(no_args_is_help=True, help="Security checks")
migrate_app = typer.Typer(no_args_is_help=True, help="Migration tools")
update_app = typer.Typer(no_args_is_help=True, help="Update Mosaivue")
app.add_typer(camera_app, name="camera")
app.add_typer(layout_app, name="layout")
app.add_typer(rotation_app, name="rotation")
app.add_typer(renderer_app, name="renderer")
app.add_typer(config_app, name="config")
app.add_typer(security_app, name="security")
app.add_typer(migrate_app, name="migrate")
app.add_typer(update_app, name="update")
console = Console()


def _init() -> CredentialCipher:
    configure_logging(load_settings().log_level)
    init_db()
    return CredentialCipher(KeyManager().load_or_create())


def _print(data: Any, json_output: bool = False) -> None:
    if json_output:
        typer.echo(json.dumps(data, indent=2, default=str))
    else:
        console.print(data)


@app.command()
def serve() -> None:
    """Run the API and web service in the foreground."""
    serve_main()


@app.command(hidden=True)
def renderer_daemon() -> None:
    """Run the renderer daemon in the foreground."""
    renderer_main()


@app.command()
def version() -> None:
    typer.echo(__version__)


@app.command()
def status(json_output: bool = typer.Option(False, "--json")) -> None:
    """Show renderer and service status."""
    _init()
    try:
        renderer = RendererRPCClient().call_sync("status")
    except RendererRPCError as exc:
        renderer = {"state": "UNAVAILABLE", "error": str(exc)}
    service_states = {}
    if shutil.which("systemctl"):
        for service in ("mosaivue-server.service", "mosaivue-renderer.service"):
            completed = subprocess.run(
                ["systemctl", "is-active", service], capture_output=True, text=True, check=False
            )
            service_states[service] = completed.stdout.strip() or "unknown"
    result = {"version": __version__, "services": service_states, "renderer": renderer}
    if json_output:
        _print(result, True)
        return
    table = Table(title="Mosaivue Status")
    table.add_column("Component")
    table.add_column("State")
    for key, value in service_states.items():
        table.add_row(key, value)
    table.add_row("Renderer", str(renderer.get("state", "unknown")))
    table.add_row("Active layout", str(renderer.get("active_layout_id") or "none"))
    table.add_row("Streams", str(len(renderer.get("streams", {}))))
    console.print(table)


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json"), refresh: bool = True) -> None:
    """Detect hardware, display, codecs and renderer capabilities."""
    _init()
    report = write_capabilities() if refresh else detect_capabilities()
    _print(report, json_output)


@app.command()
def tui() -> None:
    """Open the interactive terminal configuration interface."""
    _init()
    from .tui import run_tui

    run_tui()


@camera_app.command("list")
def camera_list(json_output: bool = typer.Option(False, "--json")) -> None:
    cipher = _init()
    with get_session_factory()() as db:
        service = CameraService(db, cipher)
        items = [service.output(item).model_dump(mode="json") for item in service.list()]
    if json_output:
        _print(items, True)
        return
    table = Table(title="Cameras")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Location")
    table.add_column("Profiles", justify="right")
    table.add_column("Enabled")
    for item in items:
        table.add_row(
            item["id"][:8],
            item["name"],
            item.get("location") or "—",
            str(len(item["stream_profiles"])),
            "yes" if item["enabled"] else "no",
        )
    console.print(table)


@camera_app.command("add")
def camera_add(
    name: str = typer.Option(..., prompt=True),
    url: str = typer.Option(..., prompt=True),
    username: str | None = typer.Option(None),
    password: str | None = typer.Option(None, prompt=False, hide_input=True),
    location: str | None = typer.Option(None),
    tags: str = typer.Option("", help="Comma-separated tags"),
    test: bool = typer.Option(True, help="Probe the stream after saving"),
) -> None:
    cipher = _init()
    payload = CameraCreate(
        name=name,
        location=location,
        tags=[item.strip() for item in tags.split(",") if item.strip()],
        username=username,
        password=password,
        stream_profiles=[StreamProfileIn(name="Main", url=url)],
    )
    with get_session_factory()() as db:
        service = CameraService(db, cipher)
        camera = service.create(payload)
        db.commit()
        camera_id = camera.id
    console.print(f"[green]Added camera[/green] {name} ({camera_id})")
    if test:
        camera_test(camera_id)


@camera_app.command("edit")
def camera_edit(
    camera_id: str,
    name: str | None = typer.Option(None),
    url: str | None = typer.Option(None, help="Replace the primary stream URL"),
    username: str | None = typer.Option(None),
    password: str | None = typer.Option(None, hide_input=True),
    location: str | None = typer.Option(None),
    tags: str | None = typer.Option(None, help="Replace tags with a comma-separated list"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled"),
    clear_credentials: bool = typer.Option(False, help="Remove the saved username/password"),
) -> None:
    """Edit a saved camera without exposing its existing password."""
    cipher = _init()
    updates: dict[str, Any] = {}
    for key, value in {
        "name": name,
        "username": username,
        "password": password,
        "location": location,
        "enabled": enabled,
    }.items():
        if value is not None:
            updates[key] = value
    if tags is not None:
        updates["tags"] = [item.strip() for item in tags.split(",") if item.strip()]
    if clear_credentials:
        updates["clear_credentials"] = True

    with get_session_factory()() as db:
        service = CameraService(db, cipher)
        camera = service.get(camera_id)
        if url is not None:
            current = camera.stream_profiles[0] if camera.stream_profiles else None
            updates["stream_profiles"] = [
                StreamProfileIn(
                    id=current.id if current else None,
                    name=current.name if current else "Main",
                    url=url,
                    transport=current.transport if current else "auto",
                    codec=current.codec if current else None,
                    width=current.width if current else None,
                    height=current.height if current else None,
                    fps=current.fps if current else None,
                    bitrate=current.bitrate if current else None,
                    latency_profile=current.latency_profile if current else "low",
                    priority=current.priority if current else 0,
                )
            ]
        if not updates:
            raise typer.BadParameter("Provide at least one field to change")
        updated = service.update(camera_id, CameraUpdate(**updates))
        db.commit()
        result = service.output(updated).model_dump(mode="json")
    console.print(f"[green]Updated camera[/green] {result['name']} ({camera_id})")


@camera_app.command("test")
def camera_test(camera_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    cipher = _init()
    try:
        with get_session_factory()() as db:
            service = CameraService(db, cipher)
            _, _, url = service.resolve_stream_url(camera_id)
            result = probe_stream(url)
    except (KeyError, StreamProbeUnavailable, RuntimeError, TimeoutError) as exc:
        _print({"success": False, "error": str(exc)}, json_output)
        raise typer.Exit(2) from exc
    _print(result, json_output)


@camera_app.command("remove")
def camera_remove(camera_id: str, yes: bool = typer.Option(False, "--yes")) -> None:
    cipher = _init()
    if not yes and not typer.confirm("Remove this camera? Layout references will become invalid."):
        raise typer.Abort()
    with get_session_factory()() as db:
        CameraService(db, cipher).delete(camera_id)
        db.commit()
    console.print("[green]Camera removed[/green]")


@layout_app.command("list")
def layout_list(json_output: bool = typer.Option(False, "--json")) -> None:
    _init()
    with get_session_factory()() as db:
        service = LayoutService(db)
        items = [service.output(item).model_dump(mode="json") for item in service.list()]
    if json_output:
        _print(items, True)
        return
    table = Table(title="Layouts")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Revision")
    table.add_column("Active")
    table.add_column("Slots")
    for item in items:
        revision = item.get("revision") or {}
        table.add_row(
            item["id"][:8],
            item["name"],
            str(item["current_revision"]),
            "●" if item["active"] else "",
            str(len((revision.get("data") or {}).get("slots", []))),
        )
    console.print(table)


@layout_app.command("show")
def layout_show(layout_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    _init()
    with get_session_factory()() as db:
        service = LayoutService(db)
        data = service.output(service.get(layout_id)).model_dump(mode="json")
    _print(data, json_output)


@layout_app.command("activate")
def layout_activate(layout_id: str) -> None:
    _init()
    client = RendererRPCClient()
    with get_session_factory()() as db:
        service = LayoutService(db)
        layout = service.get(layout_id)
        result = client.call_sync("apply_layout", layout_id=layout.id, revision=layout.current_revision)
        service.activate(layout_id)
        db.commit()
    console.print(f"[green]Activated[/green] {layout.name}")
    console.print(result)


@layout_app.command("export")
def layout_export(layout_id: str, output: Path) -> None:
    _init()
    with get_session_factory()() as db:
        service = LayoutService(db)
        data = service.output(service.get(layout_id)).model_dump(mode="json")
    output.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    console.print(f"Wrote {output}")


@layout_app.command("create")
def layout_create(
    name: str = typer.Option(..., prompt=True),
    description: str = typer.Option(""),
) -> None:
    """Create an empty reusable layout for later editing."""
    _init()
    with get_session_factory()() as db:
        layout = LayoutService(db).create(LayoutCreate(name=name, description=description))
        db.commit()
    console.print(f"[green]Created layout[/green] {layout.name} ({layout.id})")


@layout_app.command("import")
def layout_import(
    source: Path,
    name: str | None = typer.Option(None, help="Override the imported layout name"),
) -> None:
    """Import a layout previously produced by ``mosaivue layout export``."""
    _init()
    document = json.loads(source.read_text(encoding="utf-8"))
    revision = document.get("revision") or {}
    raw_data = revision.get("data") or document.get("data")
    if raw_data is None:
        raise typer.BadParameter("The file does not contain layout data")
    payload = LayoutCreate(
        name=name or document.get("name") or source.stem,
        description=document.get("description", ""),
        display_profile_id=document.get("display_profile_id"),
        data=LayoutData.model_validate(raw_data),
    )
    with get_session_factory()() as db:
        layout = LayoutService(db).create(payload)
        db.commit()
    console.print(f"[green]Imported layout[/green] {layout.name} ({layout.id})")


@rotation_app.command("list")
def rotation_list(json_output: bool = typer.Option(False, "--json")) -> None:
    _init()
    from .services.rotations import RotationService

    with get_session_factory()() as db:
        items = [
            {
                "id": group.id,
                "name": group.name,
                "interval_seconds": group.interval_seconds,
                "enabled": group.enabled,
                "cameras": len(group.camera_entries),
            }
            for group in RotationService(db).list()
        ]
    _print(items, json_output)


@rotation_app.command("start")
def rotation_start(group_id: str) -> None:
    _init()
    RendererRPCClient().call_sync("rotation_resume", group_id=group_id)
    console.print("[green]Rotation resumed[/green]")


@rotation_app.command("stop")
def rotation_stop(group_id: str) -> None:
    _init()
    RendererRPCClient().call_sync("rotation_pause", group_id=group_id)
    console.print("[yellow]Rotation paused[/yellow]")


@renderer_app.command("status")
def renderer_status(json_output: bool = typer.Option(False, "--json")) -> None:
    _init()
    _print(RendererRPCClient().call_sync("status"), json_output)


@renderer_app.command("restart")
def renderer_restart() -> None:
    if os.geteuid() != 0:
        console.print("Run with sudo: sudo mosaivue renderer restart")
        raise typer.Exit(1)
    subprocess.run(["systemctl", "restart", "mosaivue-renderer.service"], check=True)
    console.print("[green]Renderer service restarted[/green]")


@app.command("backup")
def backup_command(
    output: Path = typer.Option(Path("mosaivue-backup.zip"), "--output", "-o"),
    include_credentials: bool = typer.Option(False),
    passphrase: str | None = typer.Option(None, hide_input=True),
) -> None:
    cipher = _init()
    if include_credentials and not passphrase:
        passphrase = typer.prompt("Backup passphrase", hide_input=True, confirmation_prompt=True)
    with get_session_factory()() as db:
        content = create_backup(
            db,
            cipher,
            include_credentials=include_credentials,
            passphrase=passphrase,
        )
    output.write_bytes(content)
    os.chmod(output, 0o600)
    console.print(f"[green]Backup created[/green] {output}")


@app.command("restore")
def restore_command(
    source: Path,
    merge: bool = typer.Option(True),
    passphrase: str | None = typer.Option(None, hide_input=True),
) -> None:
    cipher = _init()
    payload = source.read_bytes()
    try:
        document = read_backup(payload, passphrase=passphrase)
    except ValueError as exc:
        if "passphrase" in str(exc).lower() and passphrase is None:
            passphrase = typer.prompt("Backup passphrase", hide_input=True)
            document = read_backup(payload, passphrase=passphrase)
        else:
            raise
    with get_session_factory()() as db:
        counts = import_configuration(db, cipher, document, merge=merge)
        db.commit()
    console.print({"restored": counts})


@app.command("export")
def export_command(output: Path = Path("mosaivue-export.json")) -> None:
    cipher = _init()
    with get_session_factory()() as db:
        document = export_configuration(db, cipher, include_credentials=False)
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    console.print(f"Wrote {output}")


@app.command("import")
def import_command(source: Path, merge: bool = True) -> None:
    cipher = _init()
    document = json.loads(source.read_text(encoding="utf-8"))
    with get_session_factory()() as db:
        counts = import_configuration(db, cipher, document, merge=merge)
        db.commit()
    console.print(counts)


@app.command("benchmark")
def benchmark_command(
    streams: int = 6,
    width: int = 1920,
    height: int = 1080,
    duration: int = 5,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _init()
    try:
        result = synthetic_benchmark(
            streams=streams, width=width, height=height, duration_seconds=duration
        )
    except (BenchmarkUnavailable, RuntimeError, ValueError) as exc:
        _print({"available": False, "error": str(exc)}, json_output)
        raise typer.Exit(2) from exc
    _print(result, json_output)


@app.command("optimize")
def optimize_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _init()
    report = detect_capabilities()
    result = {
        "profile": report.get("recommended_profile"),
        "backend": report.get("recommended_backend"),
        "sink": report.get("recommended_sink"),
        "changes_applied": False,
    }
    _print(result, json_output)


@app.command("support-bundle")
def support_bundle(output: Path = Path("mosaivue-support.zip")) -> None:
    _init()
    with get_session_factory()() as db:
        content = build_support_bundle(db)
    output.write_bytes(content)
    os.chmod(output, 0o600)
    console.print(f"Wrote sanitized support bundle {output}")


@config_app.command("validate")
def config_validate(json_output: bool = typer.Option(False, "--json")) -> None:
    _init()
    results = []
    valid = True
    with get_session_factory()() as db:
        service = LayoutService(db)
        for layout in service.list():
            revision = service.current_revision(layout)
            if revision is None:
                errors, warnings = ["No revision"], []
            else:
                try:
                    errors, warnings = service.validate(LayoutData.model_validate(revision.data))
                except Exception as exc:
                    errors, warnings = [str(exc)], []
            results.append({"layout": layout.name, "errors": errors, "warnings": warnings})
            valid = valid and not errors
    result = {"valid": valid, "layouts": results}
    _print(result, json_output)
    if not valid:
        raise typer.Exit(2)


@security_app.command("audit")
def security_audit_command(json_output: bool = typer.Option(False, "--json")) -> None:
    _init()
    result = security_audit()
    _print(result, json_output)
    if not result["passed"]:
        raise typer.Exit(2)


@migrate_app.command("displaycameras")
def migrate_displaycameras(
    source: list[Path] = typer.Option([], "--source"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    cipher = _init()
    files = discover_files(source)
    if not files:
        console.print("[red]No displaycameras configuration files found[/red]")
        raise typer.Exit(1)
    plan = build_plan(files)
    if dry_run:
        _print(plan.summary(), json_output)
        return
    camera_map: dict[str, str] = {}
    with get_session_factory()() as db:
        camera_service = CameraService(db, cipher)
        for index, camera_payload in enumerate(plan.cameras):
            camera = camera_service.create(camera_payload)
            camera_map[f"import-camera-{index}"] = camera.id
        db.flush()
        layout_service = LayoutService(db)
        for layout_payload in plan.layouts:
            raw = layout_payload.data.model_dump(mode="json")
            for slot in raw["slots"]:
                if slot.get("camera_id") in camera_map:
                    slot["camera_id"] = camera_map[slot["camera_id"]]
            layout_service.create(
                LayoutCreate(
                    name=layout_payload.name,
                    description=layout_payload.description,
                    data=LayoutData.model_validate(raw),
                )
            )
        db.commit()
    _print({**plan.summary(), "applied": True}, json_output)


@app.command("logs")
def logs_command(
    since: str = "1h",
    camera: str | None = None,
    renderer: bool = False,
    follow: bool = typer.Option(False, "--follow", "-f"),
) -> None:
    command = ["journalctl", "--since", since]
    command += ["-u", "mosaivue-renderer.service"] if renderer else ["-u", "mosaivue-server.service", "-u", "mosaivue-renderer.service"]
    if follow:
        command.append("-f")
    completed = subprocess.run(command, capture_output=not follow, text=True, check=False)
    if not follow:
        text = str(redact(completed.stdout))
        if camera:
            text = "\n".join(line for line in text.splitlines() if camera.casefold() in line.casefold())
        typer.echo(text)


def _install_prefix() -> Path:
    configured = os.environ.get("MOSAIVUE_INSTALL_PREFIX")
    if configured:
        return Path(configured)
    marker = Path("/etc/mosaivue/install-prefix")
    if marker.exists():
        try:
            value = marker.read_text(encoding="utf-8").strip()
            if value:
                return Path(value)
        except OSError:
            pass
    return Path("/opt/mosaivue")


@update_app.command("check")
def update_check() -> None:
    settings = load_settings()
    console.print(
        {
            "current_version": __version__,
            "update_checks_enabled": settings.update_checks_enabled,
            "release_api_configured": bool(os.environ.get("MOSAIVUE_RELEASE_API")),
        }
    )


@update_app.callback(invoke_without_command=True)
def update_default(ctx: typer.Context) -> None:
    """Run the installed transactional update helper."""
    if ctx.invoked_subcommand:
        return
    helper = _install_prefix() / "current/installer/update.sh"
    if not helper.exists():
        console.print("Update helper is not installed. Re-run the current release installer.")
        raise typer.Exit(1)
    command = [str(helper)]
    if os.geteuid() != 0:
        command.insert(0, "sudo")
    raise typer.Exit(subprocess.run(command, check=False).returncode)


@app.command("uninstall")
def uninstall() -> None:
    helper = _install_prefix() / "current/uninstall.sh"
    if not helper.exists():
        helper = Path(__file__).resolve().parents[2] / "uninstall.sh"
    command = [str(helper)]
    if os.geteuid() != 0:
        command.insert(0, "sudo")
    raise typer.Exit(subprocess.run(command, check=False).returncode)


if __name__ == "__main__":
    app()
