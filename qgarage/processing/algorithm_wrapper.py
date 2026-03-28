"""QgsProcessingAlgorithm wrapper for QGarage BaseApp instances."""

import logging
from pathlib import Path
from typing import Any, Dict

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
)

from ..core.base_app import BaseApp
from ..core.settings import get_uv_executable
from ..core.subprocess_runner import (
    launch_isolated_app_run,
    wait_for_isolated_app_result,
)
from ..core.uv_bridge import UvBridge
from .parameter_mapper import create_processing_parameter, extract_parameter_value

logger = logging.getLogger("qgarage.processing")


class BaseAppAlgorithm(QgsProcessingAlgorithm):
    """Wraps a QGarage BaseApp as a QgsProcessingAlgorithm.

    This allows declarative BaseApp apps to be exposed in the QGIS Processing
    Toolbox while maintaining full backward compatibility with the QGarage
    dashboard UI.
    """

    def __init__(self, app_meta: dict, app_dir: Path, app_class: type):
        """Initialize the algorithm wrapper.

        Args:
            app_meta: App metadata dict from app_meta.json
            app_dir: Path to the app directory
            app_class: BaseApp subclass (not instance)
        """
        super().__init__()
        self.app_meta = app_meta
        self.app_dir = app_dir
        self.app_class = app_class
        self._app_instance: BaseApp | None = None
        self._uv_bridge: UvBridge | None = None

    def _get_app_instance(self) -> BaseApp:
        """Get or create the BaseApp instance.

        We create a fresh instance each time to ensure clean state.
        """
        return self.app_class(app_meta=self.app_meta, app_dir=self.app_dir)

    def _get_uv_bridge(self) -> UvBridge:
        if self._uv_bridge is None:
            self._uv_bridge = UvBridge(get_uv_executable())
        return self._uv_bridge

    def tr(self, string: str) -> str:
        """Translate a string using Qt translation functions."""
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        """Return a new instance of this algorithm."""
        return BaseAppAlgorithm(self.app_meta, self.app_dir, self.app_class)

    def name(self) -> str:
        """Algorithm ID (must be lowercase alphanumeric + underscores)."""
        return self.app_meta["id"]

    def displayName(self) -> str:
        """Human-readable algorithm name."""
        return self.tr(self.app_meta["name"])

    def group(self) -> str:
        """Algorithm group for organization in the toolbox."""
        # Use first tag as group, or "QGarage Apps" as default
        tags = self.app_meta.get("tags", [])
        if tags:
            return self.tr(tags[0].capitalize())
        return self.tr("QGarage Apps")

    def groupId(self) -> str:
        """Machine-readable group ID."""
        tags = self.app_meta.get("tags", [])
        if tags:
            return tags[0].lower()
        return "qgarage_apps"

    def shortHelpString(self) -> str:
        """Help text displayed in the algorithm dialog."""
        description = self.app_meta.get("description", "")
        author = self.app_meta.get("author", "")
        version = self.app_meta.get("version", "")

        help_text = description
        if author or version:
            help_text += f"\n\nAuthor: {author}" if author else ""
            help_text += f"\nVersion: {version}" if version else ""

        return self.tr(help_text)

    def initAlgorithm(self, config: dict | None = None):
        """Define input parameters for the algorithm.

        This reads the InputSpec list from the BaseApp instance and creates
        corresponding QgsProcessingParameter objects.
        """
        # Create a temporary app instance to read its input specs
        app = self._get_app_instance()

        # Convert each InputSpec to a QgsProcessingParameter
        for spec in app._input_specs:
            try:
                param = create_processing_parameter(spec)
                self.addParameter(param)
            except Exception as e:
                logger.warning(
                    f"Failed to create parameter '{spec.key}' for app '{self.name()}': {e}",
                    exc_info=True,
                )

    def processAlgorithm(
        self,
        parameters: Dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> Dict[str, Any]:
        """Execute the algorithm.

        This creates a BaseApp instance, collects parameter values, and calls
        execute_logic() - the same method used by the QGarage dashboard.

        Args:
            parameters: Input parameters from the Processing framework
            context: Processing context
            feedback: Feedback object for progress reporting

        Returns:
            Dict of output values
        """
        # Create fresh app instance
        app = self._get_app_instance()

        # Build inputs dict by extracting values from parameters
        inputs = {}
        for spec in app._input_specs:
            try:
                value = extract_parameter_value(spec, parameters, spec.key, context, self)
                inputs[spec.key] = value
            except Exception as e:
                logger.warning(
                    f"Failed to extract parameter '{spec.key}': {e}",
                    exc_info=True,
                )
                inputs[spec.key] = None

        # Validate inputs
        error = app.validate_inputs(inputs)
        if error:
            feedback.reportError(f"Validation error: {error}")
            raise ValueError(error)

        # Report progress
        feedback.pushInfo(f"Running {self.displayName()}...")

        # Execute the app's logic in the app's isolated uv environment
        try:
            launch = launch_isolated_app_run(
                app_dir=self.app_dir,
                app_meta=self.app_meta,
                inputs=inputs,
                uv_bridge=self._get_uv_bridge(),
                keep_open=False,
            )
            try:
                result = wait_for_isolated_app_result(
                    process=launch["process"],
                    output_path=launch["output_path"],
                    stderr_log_path=launch["stderr_log_path"],
                    feedback=feedback,
                )
            finally:
                launch["tmp_dir"].cleanup()
        except Exception as e:
            feedback.reportError(f"Execution failed: {e}")
            logger.exception(f"App '{self.name()}' failed during execute_logic")
            raise

        for layer_info in result.get("__added_layers__", []):
            app._add_layer_to_project(layer_info)

        # Check result status
        status = result.get("status", "unknown")
        message = result.get("message", "")

        if status == "error":
            feedback.reportError(f"App returned error: {message}")
            raise ValueError(message)
        elif status == "success":
            feedback.pushInfo(f"Success: {message}")
        else:
            feedback.pushInfo(f"Status: {status} - {message}")

        # Return outputs (Processing framework expects a dict)
        # For now, we don't have explicit outputs defined, but apps might
        # return data in the result dict that we can pass through
        return result
