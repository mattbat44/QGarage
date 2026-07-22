from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from qgarage.plugin import QGaragePlugin


class DummySignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


def test_dummy_signal_tracks_multiple_callbacks():
    signal = DummySignal()
    called = []

    assert signal.callbacks == []
    signal.connect(lambda: called.append("first"))
    signal.connect(lambda: called.append("second"))

    assert len(signal.callbacks) == 2
    for callback in signal.callbacks:
        callback()
    assert called == ["first", "second"]


class DummyAction:
    def __init__(self, *args, **kwargs):
        self.triggered = DummySignal()

    def setCheckable(self, value):
        self.checkable = value

    def setChecked(self, value):
        self.checked = value

    def deleteLater(self):
        pass


class DummyStatusBar:
    """Minimal stand-in for StatusBarWidget used in plugin tests."""

    def __init__(self):
        self.uv_install_requested = DummySignal()
        self.pixi_install_requested = DummySignal()

    def set_uv_connected(self, value):
        pass

    def set_pixi_connected(self, value):
        pass


class DummyDock:
    def __init__(self, iface):
        self.iface = iface
        self.install_requested = DummySignal()
        self.new_app_requested = DummySignal()
        self.refresh_app_requested = DummySignal()
        self.check_updates_requested = DummySignal()
        self.update_app_requested = DummySignal()
        self.global_refresh_requested = DummySignal()
        self.visibilityChanged = DummySignal()
        self.status_bar = DummyStatusBar()
        self.registry = None
        self._current_app_id = None

    def set_registry(self, registry):
        self.registry = registry

    def setVisible(self, value):
        self.visible = value

    def update_card_state(self, app_id):
        self.updated_app_id = app_id

    @property
    def current_app_id(self):
        return self._current_app_id

    def close_current_app(self):
        self._current_app_id = None

    def deleteLater(self):
        pass


class DummyIface:
    def __init__(self):
        self._main_window = object()

    def mainWindow(self):
        return self._main_window

    def addToolBarIcon(self, action):
        pass

    def addPluginToMenu(self, menu, action):
        pass

    def addDockWidget(self, area, dock):
        pass

    def removeDockWidget(self, dock):
        pass

    def removeToolBarIcon(self, action):
        pass

    def removePluginMenu(self, menu, action):
        pass


def test_init_gui_prepares_environments_for_discovered_apps(monkeypatch):
    iface = DummyIface()
    plugin = QGaragePlugin(iface)

    entry_a = SimpleNamespace(app_id="app_a")
    entry_b = SimpleNamespace(app_id="app_b")
    registry = MagicMock()
    registry.iter_entries.return_value = [entry_a, entry_b]

    monkeypatch.setattr("qgarage.plugin.QAction", DummyAction)
    monkeypatch.setattr("qgarage.plugin.QIcon", lambda path: path)
    monkeypatch.setattr("qgarage.plugin.DashboardDock", DummyDock)
    monkeypatch.setattr(
        "qgarage.plugin.UvBridge", lambda exe: MagicMock(name="uv_bridge")
    )
    monkeypatch.setattr("qgarage.plugin.get_uv_executable", lambda: "uv")
    monkeypatch.setattr("qgarage.plugin.get_pixi_executable", lambda: "pixi")
    monkeypatch.setattr(
        "qgarage.plugin.QGaragePlugin._register_processing_provider",
        lambda self, icon_path=None: None,
    )
    monkeypatch.setattr(
        "qgarage.plugin.QGaragePlugin._check_for_app_updates",
        lambda self, force=False: None,
    )

    class DummyPixiBridge:
        def __init__(self, exe):
            self.exe = exe

    monkeypatch.setattr("qgarage.plugin.PixiBridge", DummyPixiBridge, raising=False)
    monkeypatch.setattr("qgarage.plugin.AppRegistry", lambda *args, **kwargs: registry)

    prepared = []
    monkeypatch.setattr(
        plugin,
        "_prepare_app_environment_async",
        lambda entry: prepared.append(entry.app_id),
    )

    plugin.initGui()

    registry.discover.assert_called_once()
    assert prepared == ["app_a", "app_b"]


def test_unload_disconnects_registry_and_clears_workers(monkeypatch):
    iface = DummyIface()
    plugin = QGaragePlugin(iface)

    worker = MagicMock()
    worker.setup_finished = MagicMock()
    worker.finished = MagicMock()
    plugin._env_workers = {"app_a": worker}
    plugin.registry = MagicMock()
    plugin.processing_provider = None
    plugin.uv_bridge = MagicMock()
    plugin.pixi_bridge = MagicMock()

    dock = DummyDock(iface)
    plugin.dock = dock
    plugin.action = DummyAction()

    monkeypatch.setattr("qgarage.plugin.sip.isdeleted", lambda obj: False)

    plugin.unload()

    assert dock.registry is None
    worker.wait.assert_called_once()
    assert plugin._env_workers == {}
    assert plugin.registry is None
    assert plugin.dock is None
    assert plugin.action is None


def test_init_gui_creates_managed_apps_dir(monkeypatch, tmp_path):
    iface = DummyIface()
    plugin = QGaragePlugin(iface)
    managed_apps_dir = tmp_path / ".garage"
    monkeypatch.setattr("qgarage.plugin.APPS_DIR", managed_apps_dir)
    assert not managed_apps_dir.exists()

    registry = MagicMock()
    registry.iter_entries.return_value = []

    monkeypatch.setattr("qgarage.plugin.QAction", DummyAction)
    monkeypatch.setattr("qgarage.plugin.QIcon", lambda path: path)
    monkeypatch.setattr("qgarage.plugin.DashboardDock", DummyDock)
    monkeypatch.setattr(
        "qgarage.plugin.UvBridge", lambda exe: MagicMock(name="uv_bridge")
    )
    monkeypatch.setattr("qgarage.plugin.get_uv_executable", lambda: "uv")
    monkeypatch.setattr("qgarage.plugin.get_pixi_executable", lambda: "pixi")
    monkeypatch.setattr(
        "qgarage.plugin.QGaragePlugin._register_processing_provider",
        lambda self, icon_path=None: None,
    )
    monkeypatch.setattr(
        "qgarage.plugin.QGaragePlugin._check_for_app_updates",
        lambda self, force=False: None,
    )
    monkeypatch.setattr(
        "qgarage.plugin.PixiBridge", lambda exe: MagicMock(), raising=False
    )
    monkeypatch.setattr("qgarage.plugin.AppRegistry", lambda *args, **kwargs: registry)

    plugin.initGui()

    assert managed_apps_dir.exists()
    assert managed_apps_dir.is_dir()


def test_install_dialog_uses_managed_apps_dir(monkeypatch, tmp_path):
    iface = DummyIface()
    plugin = QGaragePlugin(iface)
    managed_apps_dir = tmp_path / ".garage"
    monkeypatch.setattr("qgarage.plugin.APPS_DIR", managed_apps_dir)

    captured: dict[str, object] = {}

    class DummyInstallDialog:
        def __init__(self, apps_dir, parent=None):
            captured["apps_dir"] = apps_dir
            self.app_installed = DummySignal()

        def exec(self):
            captured["executed"] = True

    monkeypatch.setattr("qgarage.plugin.InstallDialog", DummyInstallDialog)

    plugin._on_install_requested()

    assert captured["apps_dir"] == managed_apps_dir
    assert captured["executed"] is True


def test_init_gui_triggers_update_checks(monkeypatch):
    iface = DummyIface()
    plugin = QGaragePlugin(iface)

    registry = MagicMock()
    registry.iter_entries.return_value = []

    monkeypatch.setattr("qgarage.plugin.QAction", DummyAction)
    monkeypatch.setattr("qgarage.plugin.QIcon", lambda path: path)
    monkeypatch.setattr("qgarage.plugin.DashboardDock", DummyDock)
    monkeypatch.setattr(
        "qgarage.plugin.UvBridge", lambda exe: MagicMock(name="uv_bridge")
    )
    monkeypatch.setattr("qgarage.plugin.get_uv_executable", lambda: "uv")
    monkeypatch.setattr("qgarage.plugin.get_pixi_executable", lambda: "pixi")
    monkeypatch.setattr(
        "qgarage.plugin.QGaragePlugin._register_processing_provider",
        lambda self, icon_path=None: None,
    )
    monkeypatch.setattr(
        "qgarage.plugin.PixiBridge", lambda exe: MagicMock(), raising=False
    )
    monkeypatch.setattr("qgarage.plugin.AppRegistry", lambda *args, **kwargs: registry)

    update_check_calls = []
    monkeypatch.setattr(
        plugin,
        "_check_for_app_updates",
        lambda force=False: update_check_calls.append(force),
    )

    plugin.initGui()

    assert update_check_calls == [False]
