"""Shared fixtures for QGarage tests.

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
# Mock the entire qgis package tree before any qgarage module is imported.
# ---------------------------------------------------------------------------


def _install_qgis_mock():
    """Install a recursive MagicMock for every qgis.* path used by qgarage."""

    class _DummyProcessingParameter:
        def __init__(self, name, description="", **kwargs):
            self._name = name
            self._description = description
            self.kwargs = kwargs

        def name(self):
            return self._name

        def description(self):
            return self._description

        def defaultValue(self):
            return self.kwargs.get("defaultValue")

        def options(self):
            return self.kwargs.get("options", [])

        def type(self):
            return self.kwargs.get("type")

        def minimum(self):
            return self.kwargs.get("minValue")

        def maximum(self):
            return self.kwargs.get("maxValue")

    class _DummyProcessingParameterNumber(_DummyProcessingParameter):
        class Type:
            Integer = 0
            Double = 1

        Integer = Type.Integer
        Double = Type.Double

    class _DummyProcessingParameterFile(_DummyProcessingParameter):
        class Behavior:
            File = 0
            Folder = 1

        File = Behavior.File
        Folder = Behavior.Folder

    class _DummyProcessingParameterField(_DummyProcessingParameter):
        Any = 0

    class _DummyProcessingOutput:
        def __init__(self, name, description="", **kwargs):
            self._name = name
            self._description = description
            self.kwargs = kwargs

        def name(self):
            return self._name

        def description(self):
            return self._description

    class _DummyProcessingAlgorithm:
        def __init__(self):
            self._parameters = []
            self._outputs = []

        def addParameter(self, parameter):
            self._parameters.append(parameter)

        def addOutput(self, output):
            self._outputs.append(output)

        def parameterDefinitions(self):
            return list(self._parameters)

        def outputDefinitions(self):
            return list(self._outputs)

        def parameterAsString(self, parameters, name, context):
            return parameters.get(name)

        def parameterAsInt(self, parameters, name, context):
            value = parameters.get(name)
            return None if value is None else int(value)

        def parameterAsDouble(self, parameters, name, context):
            value = parameters.get(name)
            return None if value is None else float(value)

        def parameterAsBool(self, parameters, name, context):
            return bool(parameters.get(name))

        def parameterAsEnum(self, parameters, name, context):
            value = parameters.get(name)
            return 0 if value is None else int(value)

        def parameterAsVectorLayer(self, parameters, name, context):
            return parameters.get(name)

        def parameterAsRasterLayer(self, parameters, name, context):
            return parameters.get(name)

        def parameterAsLayer(self, parameters, name, context):
            return parameters.get(name)

        def parameterAsCrs(self, parameters, name, context):
            return parameters.get(name)

        def parameterAsFile(self, parameters, name, context):
            return parameters.get(name)

    class _DummyProcessingProvider:
        def __init__(self):
            self._algorithms = []

        def addAlgorithm(self, algorithm):
            if hasattr(algorithm, "initAlgorithm"):
                algorithm.initAlgorithm({})
            self._algorithms.append(algorithm)

        def algorithms(self):
            return list(self._algorithms)

        def refreshAlgorithms(self):
            self._algorithms = []
            self.loadAlgorithms()

    class _DummyProcessingRegistry:
        def __init__(self):
            self.providers = []

        def addProvider(self, provider):
            self.providers.append(provider)
            return True

        def removeProvider(self, provider):
            if provider in self.providers:
                self.providers.remove(provider)
            return True

    class _DummyQgsApplication:
        _registry = _DummyProcessingRegistry()

        @staticmethod
        def processingRegistry():
            return _DummyQgsApplication._registry

    class _DummyProcessingContext:
        pass

    class _DummyProcessingFeedback:
        def __init__(self):
            self.info_messages = []
            self.error_messages = []

        def pushInfo(self, message):
            self.info_messages.append(message)

        def reportError(self, message, fatalError=False):
            self.error_messages.append((message, fatalError))

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
    core_mock.QgsProcessingAlgorithm = _DummyProcessingAlgorithm
    core_mock.QgsProcessingProvider = _DummyProcessingProvider
    core_mock.QgsProcessingException = type("QgsProcessingException", (Exception,), {})
    core_mock.QgsProcessingParameterString = _DummyProcessingParameter
    core_mock.QgsProcessingParameterNumber = _DummyProcessingParameterNumber
    core_mock.QgsProcessingParameterBoolean = _DummyProcessingParameter
    core_mock.QgsProcessingParameterEnum = _DummyProcessingParameter
    core_mock.QgsProcessingParameterFile = _DummyProcessingParameterFile
    core_mock.QgsProcessingParameterVectorLayer = _DummyProcessingParameter
    core_mock.QgsProcessingParameterRasterLayer = _DummyProcessingParameter
    core_mock.QgsProcessingParameterMapLayer = _DummyProcessingParameter
    core_mock.QgsProcessingParameterField = _DummyProcessingParameterField
    core_mock.QgsProcessingParameterCrs = _DummyProcessingParameter
    core_mock.QgsProcessingContext = _DummyProcessingContext
    core_mock.QgsProcessingFeedback = _DummyProcessingFeedback
    core_mock.QgsApplication = _DummyQgsApplication
    core_mock.QgsProcessingOutputBoolean = _DummyProcessingOutput
    core_mock.QgsProcessingOutputFile = _DummyProcessingOutput
    core_mock.QgsProcessingOutputFolder = _DummyProcessingOutput
    core_mock.QgsProcessingOutputMapLayer = _DummyProcessingOutput
    core_mock.QgsProcessingOutputNumber = _DummyProcessingOutput
    core_mock.QgsProcessingOutputRasterLayer = _DummyProcessingOutput
    core_mock.QgsProcessingOutputString = _DummyProcessingOutput
    core_mock.QgsProcessingOutputVectorLayer = _DummyProcessingOutput

    # QgsMapLayerProxyModel needs a Filter attribute
    core_mock.QgsMapLayerProxyModel.Filter.VectorLayer = 1
    core_mock.QgsMapLayerProxyModel.Filter.RasterLayer = 2

    # QgsFileWidget needs StorageMode
    gui_mock = sys.modules["qgis.gui"]
    gui_mock.QgsFileWidget.StorageMode.GetFile = 0
    gui_mock.QgsFileWidget.StorageMode.GetDirectory = 1

    # Qt namespace stubs used by base_app and card widget
    qtcore = sys.modules["qgis.PyQt.QtCore"]
    qtcore.QCoreApplication.translate = staticmethod(lambda context, text: text)
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
    from qgarage.core.base_app import BaseApp, InputType

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
