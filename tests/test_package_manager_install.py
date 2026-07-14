from __future__ import annotations

import pytest

from qgarage.core.package_manager_install import (
    build_install_command,
    normalized_platform_name,
)


def test_normalized_platform_name_maps_supported_systems():
    assert normalized_platform_name("Windows") == "windows"
    assert normalized_platform_name("Darwin") == "mac"
    assert normalized_platform_name("Linux") == "linux"


def test_normalized_platform_name_rejects_unknown_system():
    with pytest.raises(ValueError, match="Unsupported platform"):
        normalized_platform_name("FreeBSD")


def test_build_install_command_for_windows_multiple_managers():
    command = build_install_command(["uv", "pixi"], system_name="Windows")

    assert command[:5] == [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
    ]
    assert command[5] == "-Command"
    assert "https://astral.sh/uv/install.ps1" in command[6]
    assert "https://pixi.sh/install.ps1" in command[6]


def test_build_install_command_for_unix_uses_shell_script():
    command = build_install_command(["pixi"], system_name="Linux")

    assert command[:2] == ["sh", "-c"]
    assert command[2].startswith("set -e\n")
    assert "https://pixi.sh/install.sh" in command[2]


def test_build_install_command_rejects_unknown_manager():
    with pytest.raises(ValueError, match="Unsupported package manager"):
        build_install_command(["poetry"], system_name="Linux")


def test_build_install_command_requires_at_least_one_manager():
    with pytest.raises(ValueError, match="At least one package manager"):
        build_install_command([], system_name="Linux")