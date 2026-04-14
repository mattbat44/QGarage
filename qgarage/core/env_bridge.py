"""Protocol defining the shared interface for environment bridges (uv, pixi)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Protocol

from .constants import PIXI_TOML_FILENAME


class EnvBridge(Protocol):
    """Structural protocol satisfied by both UvBridge and PixiBridge."""

    def ensure_env(self, app_dir: Path) -> None: ...

    def get_site_packages(self, app_dir: Path) -> Optional[str]: ...

    def launch_app_isolated(
        self,
        runner_path: Path,
        config_path: Path,
        requirements_path: Optional[Path] = None,
        venv_site_packages: Optional[str] = None,
        show_window: bool = True,
    ) -> subprocess.Popen: ...


def resolve_bridge_for_app(
    app_dir: Path,
    pixi_bridge: Optional[EnvBridge],
    uv_bridge: Optional[EnvBridge],
) -> EnvBridge:
    """Return the appropriate bridge for an app directory.

    Apps with ``pixi.toml`` use pixi; all others fall back to uv.
    """
    if pixi_bridge is not None and (app_dir / PIXI_TOML_FILENAME).exists():
        return pixi_bridge
    if uv_bridge is not None:
        return uv_bridge
    raise RuntimeError(
        f"No environment backend available for {app_dir.name}. Install uv or pixi."
    )
