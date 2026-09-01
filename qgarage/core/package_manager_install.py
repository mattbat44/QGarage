from __future__ import annotations

import platform
from collections.abc import Iterable

SUPPORTED_PACKAGE_MANAGERS = ("pixi", "uv")

_WINDOWS_INSTALL_SNIPPETS = {
    "uv": "& { $ProgressPreference='SilentlyContinue'; Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression }",
    "pixi": (
        "& { "
        "$ErrorActionPreference='Stop'; "
        "$ProgressPreference='SilentlyContinue'; "
        "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; "
        "try { "
        "$installer=Invoke-RestMethod -Uri 'https://pixi.sh/install.ps1' -ErrorAction Stop; "
        "if ([string]::IsNullOrWhiteSpace($installer)) { throw 'Pixi installer download was empty.' }; "
        "& ([ScriptBlock]::Create($installer)); "
        "if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE } "
        "} catch { "
        "Write-Error ('Pixi installation failed: ' + $_.Exception.Message); "
        "Write-Error $_.ScriptStackTrace; "
        "exit 1 "
        "} "
        "}"
    ),
}

_UNIX_INSTALL_SNIPPETS = {
    "uv": "curl -LsSf https://astral.sh/uv/install.sh | sh",
    "pixi": "curl -fsSL https://pixi.sh/install.sh | bash",
}


def normalized_platform_name(system_name: str | None = None) -> str:
    """Return one of: windows, mac, linux."""
    detected = (system_name or platform.system()).strip().lower()
    if detected == "windows":
        return "windows"
    if detected == "darwin":
        return "mac"
    if detected == "linux":
        return "linux"
    raise ValueError(f"Unsupported platform: {system_name or platform.system()}")


def build_install_command(
    package_managers: Iterable[str],
    system_name: str | None = None,
) -> list[str]:
    """Return a subprocess command that installs the selected package managers."""
    requested = []
    for manager in package_managers:
        normalized = manager.strip().lower()
        if normalized not in SUPPORTED_PACKAGE_MANAGERS:
            raise ValueError(f"Unsupported package manager: {manager}")
        if normalized not in requested:
            requested.append(normalized)

    if not requested:
        raise ValueError("At least one package manager must be requested")

    platform_name = normalized_platform_name(system_name)
    if platform_name == "windows":
        script = "; ".join(_WINDOWS_INSTALL_SNIPPETS[manager] for manager in requested)
        return [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ]

    script = "set -e\n" + "\n".join(
        _UNIX_INSTALL_SNIPPETS[manager] for manager in requested
    )
    return ["sh", "-c", script]