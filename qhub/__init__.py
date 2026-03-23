def classFactory(iface):
    """QGIS plugin entry point."""
    from .plugin import QHubPlugin

    return QHubPlugin(iface)
