from __future__ import annotations

"""Protocol defining the shared interface for environment bridges (uv, pixi)."""
import subprocess
from pathlib import Path
from typing import Protocol

from .constants import PIXI_TOML_FILENAME, REQUIREMENTS_FILENAME, TOOLBOX_META_FILENAME


class EnvBridge(Protocol):
    """Structural protocol satisfied by both UvBridge and PixiBridge."""

    def ensure_env(self, app_dir: Path) -> None: ...

    def get_site_packages(self, app_dir: Path) -> str | None: ...

    def launch_app_isolated(
        self,
        runner_path: Path,
        config_path: Path,
        requirements_path: Path | None = None,
        venv_site_packages: str | None = None,
        show_window: bool = True,
        manifest_path: Path | None = None,
    ) -> subprocess.Popen: ...


def _has_local_env_config(app_dir: Path) -> bool:
    return (app_dir / PIXI_TOML_FILENAME).exists() or (
        app_dir / REQUIREMENTS_FILENAME
    ).exists()


def _find_parent_toolbox_dir(app_dir: Path) -> Path | None:
    toolbox_dir = app_dir.parent
    if (toolbox_dir / TOOLBOX_META_FILENAME).exists():
        return toolbox_dir
    return None


def resolve_env_dir_for_app(app_dir: Path) -> Path:
    """Return the directory that owns the effective environment for *app_dir*.

    Resolution order:
    1. App-local env config (`pixi.toml` or `requirements.txt`)
    2. Parent toolbox env config (if app sits in a toolbox)
    3. App directory (default uv behavior)
    """
    if _has_local_env_config(app_dir):
        return app_dir

    toolbox_dir = _find_parent_toolbox_dir(app_dir)
    if toolbox_dir is not None and (
        (toolbox_dir / PIXI_TOML_FILENAME).exists()
        or (toolbox_dir / REQUIREMENTS_FILENAME).exists()
    ):
        return toolbox_dir

    return app_dir


def resolve_backend_for_app(app_dir: Path) -> str:
    """Return the effective backend name (`pixi` or `uv`) for an app."""
    env_dir = resolve_env_dir_for_app(app_dir)
    if (env_dir / PIXI_TOML_FILENAME).exists():
        return "pixi"
    return "uv"


def resolve_bridge_for_app(
    app_dir: Path,
    pixi_bridge: EnvBridge | None,
    uv_bridge: EnvBridge | None,
) -> EnvBridge:
    """Return the appropriate bridge for an app directory.

    Apps resolve backend from their effective env directory, where app-local
    config overrides toolbox-level shared config.
    """
    if resolve_backend_for_app(app_dir) == "pixi" and pixi_bridge is not None:
        return pixi_bridge
    if uv_bridge is not None:
        return uv_bridge
    raise RuntimeError(
        f"No environment backend available for {app_dir.name}. Install uv or pixi."
    )
