"""QgsProcessingProvider for QGarage apps."""

import logging

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon

from ..core.app_registry import AppRegistry
from .algorithm_wrapper import BaseAppAlgorithm

logger = logging.getLogger("qgarage.processing")


class QGarageProcessingProvider(QgsProcessingProvider):
    """Processing provider that exposes QGarage BaseApp instances as algorithms.

    This provider scans the app registry for declarative (non-dynamic) apps
    and registers each one as a Processing algorithm.
    """

    def __init__(self, registry: AppRegistry, icon_path: str | None = None):
        """Initialize the provider.

        Args:
            registry: QGarage app registry
            icon_path: Optional path to provider icon
        """
        super().__init__()
        self.registry = registry
        self.icon_path = icon_path

    def load(self) -> bool:
        """Load the provider.

        Returns:
            True if successful
        """
        self.refreshAlgorithms()
        return True

    def unload(self):
        """Unload the provider."""
        pass

    def loadAlgorithms(self):
        """Load all algorithms from the registry.

        This filters out dynamic apps (those with custom build_dynamic_widget)
        and only registers declarative apps with execute_logic().
        """
        # Ensure all apps are loaded
        self.registry.load_all()

        for app_id, entry in self.registry.entries.items():
            # Skip if app failed to load or has no instance
            if entry.instance is None:
                logger.debug(f"Skipping app '{app_id}' - no instance available")
                continue

            # Skip dynamic apps - they have custom UIs and don't fit the
            # Processing algorithm model
            if entry.instance.build_dynamic_widget() is not None:
                logger.debug(f"Skipping app '{app_id}' - dynamic mode app")
                continue

            # Skip apps with no input specs (nothing to expose)
            if not entry.instance._input_specs:
                logger.debug(f"Skipping app '{app_id}' - no input specs")
                continue

            # Create and register the algorithm
            try:
                algorithm = BaseAppAlgorithm(
                    app_meta=entry.app_meta,
                    app_dir=entry.app_dir,
                    app_class=type(entry.instance),
                )
                self.addAlgorithm(algorithm)
                logger.info(f"Registered Processing algorithm for app '{app_id}'")
            except Exception as e:
                logger.warning(
                    f"Failed to register algorithm for app '{app_id}': {e}",
                    exc_info=True,
                )

    def id(self) -> str:
        """Provider ID (must be unique)."""
        return "qgarage"

    def name(self) -> str:
        """Provider name shown in the Processing Toolbox."""
        return self.tr("QGarage")

    def longName(self) -> str:
        """Full provider name."""
        return self.tr("QGarage Apps")

    def icon(self) -> QIcon:
        """Provider icon."""
        if self.icon_path:
            return QIcon(self.icon_path)
        return super().icon()

    def tr(self, string: str) -> str:
        """Translate a string using Qt translation functions."""
        return QCoreApplication.translate("Processing", string)

    def supportsNonFileBasedOutput(self) -> bool:
        """Whether the provider supports non-file outputs.

        Returns False since QGarage apps primarily work with files.
        """
        return False
