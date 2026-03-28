def classFactory(iface):
    """QGIS plugin entry point."""
    from .plugin import QGaragePlugin

    return QGaragePlugin(iface)
