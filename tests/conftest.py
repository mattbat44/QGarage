"""Shared fixtures for QHub tests.

All fixtures here are QGIS-free — they mock the qgis package so that
the pure-Python core modules can be imported and tested outside QGIS.
"""

import json
import sys
import textwrap
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Mock the entire qgis package tree before any qhub module is imported.
# ---------------------------------------------------------------------------


def _install_qgis_mock():
    """Install a recursive MagicMock for every qgis.* path used by qhub."""

    if "qgis" in sys.modules and not isinstance(sys.modules["qgis"], MagicMock):
        return  # running inside real QGIS — nothing to do

    qgis = types.ModuleType("qgis")
    qgis.__path__ = []

    # Sub-modules / packages we need
    submodules = [
        "qgis.core",
        "qgis.gui",
        "qgis.PyQt",
        "qgis.PyQt.QtCore",
        "qgis.PyQt.QtGui",
        "qgis.PyQt.QtWidgets",
    ]

    sys.modules["qgis"] = qgis

    for name in submodules:
        mock = MagicMock()
        mock.__path__ = []
        sys.modules[name] = mock

    # Make qgis.core.Qgis.MessageLevel.* resolve without AttributeError
    core_mock = sys.modules["qgis.core"]
    core_mock.Qgis.MessageLevel.Info = 0
    core_mock.Qgis.MessageLevel.Warning = 1
    core_mock.Qgis.MessageLevel.Critical = 2

    # QgsMapLayerProxyModel needs a Filter attribute
    core_mock.QgsMapLayerProxyModel.Filter.VectorLayer = 1
    core_mock.QgsMapLayerProxyModel.Filter.RasterLayer = 2

    # QgsFileWidget needs StorageMode
    gui_mock = sys.modules["qgis.gui"]
    gui_mock.QgsFileWidget.StorageMode.GetFile = 0
    gui_mock.QgsFileWidget.StorageMode.GetDirectory = 1

    # Qt namespace stubs used by base_app and card widget
    qtcore = sys.modules["qgis.PyQt.QtCore"]
    qtcore.Qt.CursorShape.PointingHandCursor = 13
    qtcore.Qt.AspectRatioMode.KeepAspectRatio = 1
    qtcore.Qt.TransformationMode.SmoothTransformation = 1
    qtcore.Qt.AlignmentFlag.AlignCenter = 0x0084
    qtcore.Qt.MouseButton.LeftButton = 1

    qtwidgets = sys.modules["qgis.PyQt.QtWidgets"]
    qtwidgets.QFrame.Shape.StyledPanel = 1
    qtwidgets.QSizePolicy.Policy.Preferred = 5
    qtwidgets.QSizePolicy.Policy.Fixed = 0
    qtwidgets.QToolButton.ToolButtonPopupMode.InstantPopup = 2


_install_qgis_mock()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_apps_dir(tmp_path: Path) -> Path:
    """Return an empty temporary apps directory."""
    apps = tmp_path / "apps"
    apps.mkdir()
    return apps


@pytest.fixture
def make_app_dir(tmp_apps_dir: Path):
    """Factory fixture: create an app directory with given meta and optional main.py.

    Usage::

        app_dir = make_app_dir({"id": "demo", "name": "Demo"}, main_py="...")
    """

    def _make(
        meta: dict, *, main_py: str | None = None, requirements: str = ""
    ) -> Path:
        app_id = meta["id"]
        d = tmp_apps_dir / app_id
        d.mkdir(exist_ok=True)
        (d / "app_meta.json").write_text(json.dumps(meta), encoding="utf-8")
        if main_py is not None:
            (d / meta.get("entry_point", "main.py")).write_text(
                main_py, encoding="utf-8"
            )
        if requirements:
            (d / "requirements.txt").write_text(requirements, encoding="utf-8")
        return d

    return _make


MINIMAL_MAIN_PY = textwrap.dedent("""\
    from qhub.core.base_app import BaseApp, InputType

    class App(BaseApp):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.add_input("name", "Name", InputType.STRING, default="World")

        def execute_logic(self, inputs):
            return {"status": "success", "message": f"Hello {inputs['name']}"}
""")

MINIMAL_META = {
    "id": "test_app",
    "name": "Test App",
    "version": "0.1.0",
    "description": "A test app",
    "entry_point": "main.py",
    "class_name": "App",
    "tags": [],
}
