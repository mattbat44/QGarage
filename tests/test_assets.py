from __future__ import annotations

from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "qgarage"
ICONS_DIR = PLUGIN_DIR / "resources" / "icons"
FONTS_DIR = PLUGIN_DIR / "resources" / "fonts"

EXPECTED_ICONS = {
    "arrow_back",
    "installing_tool",
    "open_tool",
    "qgarage_icon",
    "qgarage_logo",
    "running_tool",
    "search",
    "toolbox_dropdown",
    "toolbox_icon",
    "update_tool",
}


def test_bundled_icons_exist():
    present = {p.stem for p in ICONS_DIR.glob("*.svg")}
    assert EXPECTED_ICONS <= present


def test_bundled_fonts_and_licenses_exist():
    assert (FONTS_DIR / "Jersey15-Regular.ttf").is_file()
    assert (FONTS_DIR / "JetBrainsMono-Regular.ttf").is_file()
    assert (FONTS_DIR / "OFL-Jersey15.txt").is_file()
    assert (FONTS_DIR / "OFL-JetBrainsMono.txt").is_file()


def test_plugin_icon_is_design_asset():
    assert (PLUGIN_DIR / "icon.svg").read_bytes() == (
        ICONS_DIR / "qgarage_icon.svg"
    ).read_bytes()


def test_stylesheets_do_not_use_web_imports():
    for name in ("qgarage.qss",):
        assert "@import" not in (PLUGIN_DIR / "themes" / name).read_text(
            encoding="utf-8"
        )
