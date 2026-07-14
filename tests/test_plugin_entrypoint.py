"""Tests for the QGIS plugin entrypoint exposed at package scope."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import qgarage


def test_package_exports_classfactory():
    assert hasattr(qgarage, "classFactory")
    assert callable(qgarage.classFactory)


def test_package_aliases_active_plugin_namespace():
    assert sys.modules["qgarage"] is qgarage


def test_classfactory_sets_runtime_plugin_paths(monkeypatch):
    class DummyPlugin:
        def __init__(self, iface):
            self.iface = iface

    monkeypatch.setattr("qgarage.plugin.QGaragePlugin", DummyPlugin)

    plugin = qgarage.classFactory(MagicMock())

    assert Path(plugin.PLUGIN_DIR).name == "qgarage"
    assert Path(plugin.PLUGIN_DIR) / "apps" == plugin.APPS_DIR
