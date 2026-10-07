from pathlib import Path


def test_built_frontend_assets_are_packaged() -> None:
    static = Path(__file__).parents[2] / "src" / "mosaivue" / "static"
    assert (static / "index.html").exists()
    assert (static / "assets" / "app.js").stat().st_size > 10_000
    assert (static / "assets" / "styles.css").stat().st_size > 20_000
    assert (static / "brand" / "mosaivue-logo.png").stat().st_size > 0
    assert (static / "brand" / "mosaivue-icon.png").stat().st_size > 0
