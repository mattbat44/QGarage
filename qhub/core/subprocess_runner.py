"""
Isolated subprocess execution for QHub apps.

Every call to execute_logic() is marshalled into a ``uv run --isolated``
child process that:
  - opens its own console window (live output visible to the user)
  - uses the same Python interpreter as QGIS so native packages like GDAL
    are available without re-installation
  - has all ``qgis.*`` modules stubbed so apps that import them still work
  - captures ``QgsProject.addMapLayer()`` calls and replays them on the
    QGIS main thread after the subprocess finishes

Communication between QGIS and the subprocess is via two temp JSON files:
  inputs.json   – serialised input values
  output.json   – result dict written by the subprocess when done
The ProcessMonitor QThread polls for output.json so QGIS reacts as soon as
the script finishes, without blocking the UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qgis.PyQt.QtCore import QThread, pyqtSignal

# ── Input serialisation ───────────────────────────────────────────────────────


def serialize_inputs(inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
    """Convert QGIS objects in *inputs* to JSON-serialisable representations.

    Vector layers are exported to a temp GeoJSON file so the subprocess can
    perform geometry operations with GDAL/OGR without needing a live QGIS.
    """
    try:
        from qgis.core import (
            QgsVectorLayer,
            QgsRasterLayer,
            QgsCoordinateReferenceSystem,
            QgsVectorFileWriter,
            QgsCoordinateTransformContext,
        )
    except ImportError:
        # Already outside QGIS (test context) – pass through unchanged
        return inputs

    result: dict[str, Any] = {}
    for key, val in inputs.items():
        if isinstance(val, QgsVectorLayer):
            geojson_path = tmp_dir / f"{key}_layer.geojson"
            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GeoJSON"
            QgsVectorFileWriter.writeAsVectorFormatV2(
                val, str(geojson_path), QgsCoordinateTransformContext(), opts
            )
            extent = val.extent()
            result[key] = {
                "__type__": "VectorLayer",
                "source": str(geojson_path) if geojson_path.exists() else val.source(),
                "name": val.name(),
                "crs": val.crs().authid() if val.crs() else "EPSG:4326",
                "extent": {
                    "xmin": extent.xMinimum(),
                    "ymin": extent.yMinimum(),
                    "xmax": extent.xMaximum(),
                    "ymax": extent.yMaximum(),
                },
                "feature_count": val.featureCount(),
            }
        elif isinstance(val, QgsRasterLayer):
            result[key] = {
                "__type__": "RasterLayer",
                "source": val.source(),
                "name": val.name(),
                "crs": val.crs().authid() if val.crs() else "EPSG:4326",
            }
        elif isinstance(val, QgsCoordinateReferenceSystem):
            result[key] = {"__type__": "CRS", "authid": val.authid()}
        elif isinstance(val, (str, int, float, bool, type(None))):
            result[key] = val
        else:
            result[key] = str(val)
    return result


# ── Embedded runner script ────────────────────────────────────────────────────
# Written to a temp file and executed by ``uv run --isolated --python <qgis_py>``.

RUNNER_SCRIPT = r'''
"""QHub isolated app runner – auto-generated, do not edit."""
import json
import sys
import os
import shutil
import traceback as _tb_mod
from pathlib import Path
from unittest.mock import MagicMock

# ── Output path from config (resolved early for crash handling) ───────────────
# We need this available at module scope so the outer try/except can always
# write a result file, even if the error happens during config loading.
_output_path = None
_stderr_log_file = None


def _safe_print(*args, **kwargs):
    """print() that silently swallows OSError when stdout is broken."""
    try:
        print(*args, **kwargs)
    except OSError:
        pass


class _StderrTee:
    """Duplicates writes to the original stderr AND a log file."""
    def __init__(self, original, log_path):
        self._orig = original
        self._file = open(log_path, "w", encoding="utf-8")

    def write(self, s):
        try:
            self._orig.write(s)
        except OSError:
            pass
        self._file.write(s)
        self._file.flush()

    def flush(self):
        try:
            self._orig.flush()
        except OSError:
            pass
        self._file.flush()

    def close_log(self):
        try:
            self._file.close()
        except Exception:
            pass


try:

    # ── QGIS stubs (injected before any app import) ───────────────────────────

    _ADDED_LAYERS: list[dict] = []


    class _FakeExtent:
        def __init__(self, xmin, ymin, xmax, ymax):
            self._xmin, self._ymin, self._xmax, self._ymax = xmin, ymin, xmax, ymax
        def xMinimum(self): return self._xmin
        def xMaximum(self): return self._xmax
        def yMinimum(self): return self._ymin
        def yMaximum(self): return self._ymax
        def isNull(self):   return False


    class _FakeCrs:
        def __init__(self, authid):
            self._authid = authid
        def authid(self):  return self._authid
        def isValid(self): return bool(self._authid)


    class _FakeVectorLayer:
        """Shim for a serialised QgsVectorLayer passed via inputs.json."""
        def __init__(self, d: dict):
            self._d = d
            e = d.get("extent", {})
            self._extent = _FakeExtent(
                e.get("xmin", 0), e.get("ymin", 0),
                e.get("xmax", 0), e.get("ymax", 0),
            )
            self._crs = _FakeCrs(d.get("crs", "EPSG:4326"))

        def source(self):       return self._d.get("source", "")
        def name(self):         return self._d.get("name", "")
        def crs(self):          return self._crs
        def extent(self):       return self._extent
        def featureCount(self): return self._d.get("feature_count", 0)
        def isValid(self):      return bool(self._d.get("source"))


    class _FakeRasterLayerData:
        """Shim for a serialised QgsRasterLayer passed via inputs.json."""
        def __init__(self, d: dict):
            self._d = d
            self._crs = _FakeCrs(d.get("crs", "EPSG:4326"))

        def source(self): return self._d.get("source", "")
        def name(self):   return self._d.get("name", "")
        def crs(self):    return self._crs
        def isValid(self): return bool(self._d.get("source"))


    class _FakeRasterLayer:
        """Shim for ``QgsRasterLayer(path, name)`` calls inside execute_logic."""
        def __init__(self, source="", name="", *args, **kwargs):
            self._source = source
            self._name   = name

        def source(self):  return self._source
        def name(self):    return self._name
        def isValid(self): return bool(self._source)


    class _FakeProject:
        _inst = None

        @classmethod
        def instance(cls):
            if cls._inst is None:
                cls._inst = cls()
            return cls._inst

        def addMapLayer(self, layer, add_to_legend=True):
            _ADDED_LAYERS.append({"source": layer.source(), "name": layer.name()})
            return layer

        # Provide no-op stubs for other common calls
        def mapLayersByName(self, name):  return []
        def mapLayers(self):              return {}


    class _FakeVectorFileWriter:
        """Stubs for QgsVectorFileWriter used in clip helpers."""

        class SaveVectorOptions:
            driverName = "GeoJSON"
            fileEncoding = "UTF-8"

        class WriterError:
            NoError = 0

        @staticmethod
        def writeAsVectorFormatV2(layer, path, transform_ctx, options):
            """Copy the layer source to *path* if it is already a GeoJSON file."""
            src = layer.source() if hasattr(layer, "source") else ""
            if src and src.lower().endswith(".geojson") and os.path.exists(src):
                shutil.copy(src, path)
            return (0, "", "", "")


    def _deserialize(v):
        if isinstance(v, dict) and "__type__" in v:
            t = v["__type__"]
            if t == "VectorLayer":
                return _FakeVectorLayer(v)
            if t == "RasterLayer":
                return _FakeRasterLayerData(v)
            if t == "CRS":
                return _FakeCrs(v.get("authid", ""))
        if isinstance(v, dict):
            return {k: _deserialize(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [_deserialize(i) for i in v]
        return v


    # Build qgis.core stub with our specific shims
    _qgis_core = MagicMock()
    _qgis_core.QgsProject                  = _FakeProject
    _qgis_core.QgsVectorLayer               = _FakeVectorLayer
    _qgis_core.QgsRasterLayer               = _FakeRasterLayer
    _qgis_core.QgsVectorFileWriter          = _FakeVectorFileWriter
    _qgis_core.QgsCoordinateTransformContext = MagicMock(return_value=MagicMock())
    _qgis_core.QgsMapLayerProxyModel        = MagicMock()

    sys.modules["qgis"]                 = MagicMock()
    sys.modules["qgis.core"]            = _qgis_core
    sys.modules["qgis.PyQt"]            = MagicMock()
    sys.modules["qgis.PyQt.QtCore"]     = MagicMock()
    sys.modules["qgis.PyQt.QtWidgets"]  = MagicMock()
    sys.modules["qgis.PyQt.QtGui"]      = MagicMock()
    sys.modules["qgis.gui"]             = MagicMock()
    sys.modules["qgis.utils"]           = MagicMock()

    # ── Load configuration ────────────────────────────────────────────────────

    config_path = Path(sys.argv[1])
    with open(config_path) as _f:
        cfg = json.load(_f)

    inputs_path  = Path(cfg["inputs_path"])
    _output_path = Path(cfg["output_path"])
    plugin_dir   = Path(cfg["plugin_dir"])   # e.g. .../python/plugins/qhub
    app_dir      = Path(cfg["app_dir"])
    module_path  = Path(cfg["module_path"])
    class_name   = cfg["class_name"]
    app_meta     = cfg["app_meta"]

    # ── Redirect stderr to a tee (console + log file) ─────────────────────
    _stderr_log_path = cfg.get("stderr_log_path")
    if _stderr_log_path:
        _stderr_tee = _StderrTee(sys.stderr, _stderr_log_path)
        sys.stderr = _stderr_tee
        _stderr_log_file = _stderr_tee

    with open(inputs_path) as _f:
        inputs = _deserialize(json.load(_f))

    # ── sys.path setup ────────────────────────────────────────────────────────

    # Make qhub package importable (for BaseApp, InputType, etc.)
    sys.path.insert(0, str(plugin_dir.parent))
    # Make the app dir importable (for any local imports in the app)
    sys.path.insert(0, str(app_dir))

    # ── Import and instantiate the app ────────────────────────────────────────

    import importlib.util

    _spec = importlib.util.spec_from_file_location("_qhub_app_main", str(module_path))
    _mod  = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _mod
    _spec.loader.exec_module(_mod)
    AppClass = getattr(_mod, class_name)
    app = AppClass(app_meta=app_meta, app_dir=app_dir)

    # Redirect app.log() to _safe_print so output appears live in the console
    app.log          = lambda msg: _safe_print(msg, flush=True)
    app.set_progress = lambda v, m=100: _safe_print(f"[PROGRESS] {v}/{m}", flush=True)

    # ── Execute ───────────────────────────────────────────────────────────────

    _safe_print(f"[QHub] Running {app_meta.get('name', class_name)} ...\n", flush=True)
    try:
        result = app.execute_logic(inputs)
        if not isinstance(result, dict):
            result = {"status": "success", "message": str(result)}
    except Exception as _e:
        result = {
            "status": "error",
            "message": f"{type(_e).__name__}: {_e}",
            "traceback": _tb_mod.format_exc(),
        }
        _safe_print(result["traceback"], flush=True)

    result["__added_layers__"] = _ADDED_LAYERS

    # Write output JSON – QGIS side starts watching for this file
    with open(_output_path, "w") as _f:
        json.dump(result, _f)

    status = result.get("status", "unknown").upper()
    _safe_print(f"\n[QHub] [{status}] {result.get('message', '')}", flush=True)

except Exception as _fatal:
    # ── Catch-all: any error during setup, import, or config loading ──────
    _tb_text = _tb_mod.format_exc()
    _safe_print(f"\n[QHub] FATAL ERROR during runner initialisation:\n{_tb_text}", flush=True)

    # Also write to stderr log if available
    try:
        if _stderr_log_file is None:
            # stderr tee wasn't set up yet — try writing directly
            _cfg_path = Path(sys.argv[1])
            with open(_cfg_path) as _ff:
                _slp = json.load(_ff).get("stderr_log_path")
            if _slp:
                Path(_slp).write_text(_tb_text, encoding="utf-8")
    except Exception:
        pass

    _crash_result = {
        "status": "error",
        "message": f"Runner crash: {type(_fatal).__name__}: {_fatal}",
        "traceback": _tb_text,
        "__added_layers__": [],
    }

    # Try to write output.json so QGIS side gets the full error
    _out = _output_path
    if _out is None:
        # output_path wasn't resolved yet — try to derive it from argv
        try:
            _cfg_path = Path(sys.argv[1])
            with open(_cfg_path) as _ff:
                _out = Path(json.load(_ff)["output_path"])
        except Exception:
            _out = None

    if _out is not None:
        try:
            with open(_out, "w") as _f:
                json.dump(_crash_result, _f)
        except Exception:
            pass  # file system is broken — nothing more we can do

# Close stderr log if we tee'd it
if _stderr_log_file is not None:
    try:
        _stderr_log_file.close_log()
    except Exception:
        pass

# Keep window open so the user can read logs
try:
    input("\n--- Press Enter to close this window ---")
except (EOFError, KeyboardInterrupt, OSError):
    pass
'''


# ── Process monitor thread ────────────────────────────────────────────────────


class ProcessMonitor(QThread):
    """Polls for the output JSON written by the runner script.

    Emits ``completed(dict)`` as soon as the subprocess writes its result,
    so QGIS-side finalisation (e.g. addMapLayer) can happen without waiting
    for the user to close the console window.
    """

    completed = pyqtSignal(dict)
    error = pyqtSignal(str)

    _POLL_MS = 500

    def __init__(
        self,
        process,
        output_path: Path,
        tmp_dir: Path,
        stderr_log_path: Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._process = process
        self._output = output_path
        self._tmp_dir = tmp_dir
        self._stderr_log = stderr_log_path
        self._signalled = False

    def run(self) -> None:
        import time

        while True:
            if not self._signalled and self._output.exists():
                self._emit_result()

            if self._process.poll() is not None:
                # Process has exited
                if not self._signalled:
                    if self._output.exists():
                        self._emit_result()
                    else:
                        detail = self._read_stderr_log()
                        msg = (
                            f"Process exited with code {self._process.returncode} "
                            "before writing a result."
                        )
                        if detail:
                            msg += f"\n\n{detail}"
                        else:
                            msg += " Check the console for errors."
                        self.error.emit(msg)
                break

            time.sleep(self._POLL_MS / 1000)

    def _emit_result(self) -> None:
        try:
            with open(self._output) as f:
                result = json.load(f)
            self._signalled = True
            self.completed.emit(result)
        except Exception as exc:
            self.error.emit(f"Could not parse result JSON: {exc}")
            self._signalled = True

    def _read_stderr_log(self) -> str:
        """Read captured stderr from the log file, if it exists."""
        if self._stderr_log is None:
            return ""
        try:
            if self._stderr_log.exists():
                content = self._stderr_log.read_text(
                    encoding="utf-8", errors="replace"
                ).strip()
                return content
        except Exception:
            pass
        return ""
