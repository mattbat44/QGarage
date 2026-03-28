from __future__ import annotations

from typing import Any, Optional

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterMapLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
    QgsProcessingProvider,
)

from .app_executor import run_app_isolated
from .app_registry import AppEntry, AppRegistry
from .base_app import BaseApp, InputSpec, InputType

DEFAULT_GROUP_ID = "qgarage_apps"
DEFAULT_GROUP_NAME = "Apps"
SHOW_CONSOLE_PARAM = "SHOW_SUBPROCESS_CONSOLE"


class QGarageProcessingAlgorithm(QgsProcessingAlgorithm):
    def __init__(self, registry: AppRegistry, entry: AppEntry):
        super().__init__()
        self._registry = registry
        self._entry = entry

    def createInstance(self) -> "QGarageProcessingAlgorithm":
        return QGarageProcessingAlgorithm(self._registry, self._entry)

    def name(self) -> str:
        return self._entry.app_id

    def displayName(self) -> str:
        return self._entry.app_name

    def group(self) -> str:
        toolbox_entry = self._toolbox_entry()
        return toolbox_entry.toolbox_name if toolbox_entry is not None else DEFAULT_GROUP_NAME

    def groupId(self) -> str:
        toolbox_entry = self._toolbox_entry()
        return toolbox_entry.toolbox_id if toolbox_entry is not None else DEFAULT_GROUP_ID

    def shortHelpString(self) -> str:
        description = self._entry.app_meta.get("description", "")
        if not description:
            return "QGarage app exposed through the Processing pane."
        return description

    def tags(self) -> list[str]:
        return list(self._entry.app_meta.get("tags", []))

    def initAlgorithm(self, config: Optional[dict] = None) -> None:
        self.addParameter(
            QgsProcessingParameterBoolean(
                SHOW_CONSOLE_PARAM,
                "Show subprocess console",
                defaultValue=False,
                optional=True,
            )
        )

        app = self._get_app()
        if app is None:
            return

        for spec in app._input_specs:
            parameter = self._build_parameter(spec)
            if parameter is not None:
                self.addParameter(parameter)

    def processAlgorithm(self, parameters: dict, context, feedback) -> dict[str, Any]:
        app = self._get_app()
        if app is None:
            raise QgsProcessingException(
                f"QGarage app '{self._entry.app_id}' is not available"
            )

        inputs = {}
        for spec in app._input_specs:
            inputs[spec.key] = self._parameter_value(spec, parameters, context)

        error = app.validate_inputs(inputs)
        if error:
            raise QgsProcessingException(error)

        if feedback is not None:
            feedback.pushInfo(f"Running {app.app_name}")

        show_console = self.parameterAsBool(parameters, SHOW_CONSOLE_PARAM, context)

        result = run_app_isolated(
            app,
            self._registry.uv_bridge,
            inputs,
            show_console=show_console,
        )

        for layer_info in result.get("__added_layers__", []):
            app._add_layer_to_project(layer_info)

        app.on_finalize(result)

        if feedback is not None and result.get("message"):
            feedback.pushInfo(result["message"])

        if result.get("status") == "error":
            traceback_text = result.get("traceback")
            if feedback is not None and traceback_text:
                feedback.reportError(traceback_text, fatalError=False)
            raise QgsProcessingException(result.get("message", "QGarage app failed"))

        return {
            "STATUS": result.get("status", "success"),
            "MESSAGE": result.get("message", ""),
        }

    def _get_app(self) -> Optional[BaseApp]:
        app = self._registry.load_app(self._entry.app_id)
        if app is None or not self._supports_processing(app):
            return None
        return app

    def _toolbox_entry(self):
        toolbox_id = self._entry.parent_toolbox_id
        if not toolbox_id:
            return None
        return self._registry.toolbox_entries.get(toolbox_id)

    @staticmethod
    def _supports_processing(app: BaseApp) -> bool:
        return type(app).execute_logic is not BaseApp.execute_logic

    @staticmethod
    def _build_parameter(spec: InputSpec):
        optional = not spec.required
        default_value = spec.default

        if spec.input_type == InputType.STRING:
            return QgsProcessingParameterString(
                spec.key,
                spec.label,
                defaultValue=default_value,
                optional=optional,
            )

        if spec.input_type == InputType.TEXT_AREA:
            return QgsProcessingParameterString(
                spec.key,
                spec.label,
                defaultValue=default_value,
                optional=optional,
                multiLine=True,
            )

        if spec.input_type == InputType.INTEGER:
            return QgsProcessingParameterNumber(
                spec.key,
                spec.label,
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=default_value,
                optional=optional,
                minValue=spec.min_value,
                maxValue=spec.max_value,
            )

        if spec.input_type == InputType.FLOAT:
            return QgsProcessingParameterNumber(
                spec.key,
                spec.label,
                type=QgsProcessingParameterNumber.Double,
                defaultValue=default_value,
                optional=optional,
                minValue=spec.min_value,
                maxValue=spec.max_value,
            )

        if spec.input_type == InputType.BOOLEAN:
            return QgsProcessingParameterBoolean(
                spec.key,
                spec.label,
                defaultValue=bool(default_value),
                optional=optional,
            )

        if spec.input_type == InputType.CHOICE:
            default_index = 0
            if default_value in spec.choices:
                default_index = spec.choices.index(default_value)
            return QgsProcessingParameterEnum(
                spec.key,
                spec.label,
                options=spec.choices,
                defaultValue=default_index,
                optional=optional,
            )

        if spec.input_type == InputType.FILE_PATH:
            return QgsProcessingParameterFile(
                spec.key,
                spec.label,
                behavior=QgsProcessingParameterFile.File,
                defaultValue=default_value,
                optional=optional,
            )

        if spec.input_type == InputType.FOLDER_PATH:
            return QgsProcessingParameterFile(
                spec.key,
                spec.label,
                behavior=QgsProcessingParameterFile.Folder,
                defaultValue=default_value,
                optional=optional,
            )

        if spec.input_type == InputType.VECTOR_LAYER:
            return QgsProcessingParameterVectorLayer(
                spec.key,
                spec.label,
                defaultValue=default_value,
                optional=optional,
            )

        if spec.input_type == InputType.RASTER_LAYER:
            return QgsProcessingParameterRasterLayer(
                spec.key,
                spec.label,
                defaultValue=default_value,
                optional=optional,
            )

        if spec.input_type == InputType.ANY_LAYER:
            return QgsProcessingParameterMapLayer(
                spec.key,
                spec.label,
                defaultValue=default_value,
                optional=optional,
            )

        if spec.input_type == InputType.FIELD:
            return QgsProcessingParameterField(
                spec.key,
                spec.label,
                defaultValue=default_value,
                parentLayerParameterName=spec.linked_layer_key or None,
                type=QgsProcessingParameterField.Any,
                optional=optional,
            )

        if spec.input_type == InputType.CRS:
            return QgsProcessingParameterCrs(
                spec.key,
                spec.label,
                defaultValue=default_value,
                optional=optional,
            )

        return QgsProcessingParameterString(
            spec.key,
            spec.label,
            defaultValue=default_value,
            optional=optional,
        )

    def _parameter_value(self, spec: InputSpec, parameters: dict, context):
        if spec.input_type in (InputType.STRING, InputType.FILE_PATH, InputType.FOLDER_PATH):
            return self.parameterAsString(parameters, spec.key, context)

        if spec.input_type == InputType.TEXT_AREA:
            return self.parameterAsString(parameters, spec.key, context)

        if spec.input_type == InputType.INTEGER:
            return self.parameterAsInt(parameters, spec.key, context)

        if spec.input_type == InputType.FLOAT:
            return self.parameterAsDouble(parameters, spec.key, context)

        if spec.input_type == InputType.BOOLEAN:
            return self.parameterAsBool(parameters, spec.key, context)

        if spec.input_type == InputType.CHOICE:
            index = self.parameterAsEnum(parameters, spec.key, context)
            if 0 <= index < len(spec.choices):
                return spec.choices[index]
            return spec.default

        if spec.input_type == InputType.VECTOR_LAYER:
            return self.parameterAsVectorLayer(parameters, spec.key, context)

        if spec.input_type == InputType.RASTER_LAYER:
            return self.parameterAsRasterLayer(parameters, spec.key, context)

        if spec.input_type == InputType.ANY_LAYER:
            return self.parameterAsLayer(parameters, spec.key, context)

        if spec.input_type == InputType.FIELD:
            return self.parameterAsString(parameters, spec.key, context)

        if spec.input_type == InputType.CRS:
            return self.parameterAsCrs(parameters, spec.key, context)

        return parameters.get(spec.key)


class QGarageProcessingProvider(QgsProcessingProvider):
    def __init__(self, registry: AppRegistry):
        super().__init__()
        self._registry = registry

    def id(self) -> str:
        return "qgarage"

    def name(self) -> str:
        return "QGarage"

    def longName(self) -> str:
        return "QGarage"

    def loadAlgorithms(self) -> None:
        entries = sorted(
            self._registry.entries.values(),
            key=lambda entry: (
                self._group_sort_key(entry),
                entry.app_name.lower(),
            ),
        )
        for entry in entries:
            app = self._registry.load_app(entry.app_id)
            if app is None or type(app).execute_logic is BaseApp.execute_logic:
                continue
            self.addAlgorithm(QGarageProcessingAlgorithm(self._registry, entry))

    def _group_sort_key(self, entry: AppEntry) -> str:
        if entry.parent_toolbox_id:
            toolbox_entry = self._registry.toolbox_entries.get(entry.parent_toolbox_id)
            if toolbox_entry is not None:
                return toolbox_entry.toolbox_name.lower()
        return DEFAULT_GROUP_NAME.lower()