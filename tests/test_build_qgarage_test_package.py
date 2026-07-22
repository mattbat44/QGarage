from __future__ import annotations

import importlib.util
from pathlib import Path
import textwrap


def _load_build_module():
    script_path = (
        Path(__file__).resolve().parent.parent / "build-qgarage-test-package.py"
    )
    spec = importlib.util.spec_from_file_location(
        "build_qgarage_test_package", script_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_update_init_text_uses_managed_apps_dir():
    module = _load_build_module()

    old = textwrap.dedent(
        """\
        def classFactory(iface):
            \"\"\"QGIS plugin entry point.\"\"\"
            from .plugin import QGaragePlugin

            return QGaragePlugin(iface)
        """
    )

    updated = module.update_init_text(old)

    assert "get_managed_apps_dir" in updated
    assert 'plugin.APPS_DIR = get_managed_apps_dir()' in updated
    assert 'Path(plugin.PLUGIN_DIR) / "apps"' not in updated
    assert 'plugin.APPS_DIR = Path(plugin.PLUGIN_DIR)' not in updated
