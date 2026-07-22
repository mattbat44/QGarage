from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SOURCE_PLUGIN_DIR = REPO_ROOT / "qgarage"
DIST_DIR = REPO_ROOT / "dist"
TEST_PLUGIN_DIRNAME = "qgarage_test"
TEST_PLUGIN_NAME = "QGarage Test"
TEST_VERSION_SUFFIX = "-test"


def update_metadata_text(raw: str) -> str:
    lines = raw.splitlines()
    updated: list[str] = []
    for line in lines:
        if line.startswith("name="):
            updated.append(f"name={TEST_PLUGIN_NAME}")
        elif line.startswith("version="):
            version = line.split("=", 1)[1].strip()
            updated.append(f"version={version}{TEST_VERSION_SUFFIX}")
        elif line.startswith("description="):
            updated.append(
                "description=Test-installable QGarage build for side-by-side validation without replacing the official repository plugin."
            )
        elif line.startswith("about="):
            updated.append(
                "about=This is a side-by-side QGarage test build packaged under the qgarage_test plugin folder so it can be installed directly from ZIP for fresh validation without colliding with an existing official QGarage install."
            )
        elif line.startswith("experimental="):
            updated.append("experimental=True")
        else:
            updated.append(line)
    return "\n".join(updated) + "\n"


def update_init_text(raw: str) -> str:
    return raw.replace(
        "    from .plugin import QGaragePlugin\n\n    return QGaragePlugin(iface)\n",
        "    from .plugin import QGaragePlugin, get_managed_apps_dir\n\n"
        "    import os\n"
        "    plugin = QGaragePlugin(iface)\n"
        "    plugin.PLUGIN_DIR = os.path.dirname(__file__)\n"
        "    plugin.APPS_DIR = get_managed_apps_dir()\n"
        "    return plugin\n",
    )


def prepare_test_plugin_tree(build_root: Path) -> Path:
    target_plugin_dir = build_root / TEST_PLUGIN_DIRNAME
    shutil.copytree(SOURCE_PLUGIN_DIR, target_plugin_dir, dirs_exist_ok=True)

    metadata_path = target_plugin_dir / "metadata.txt"
    metadata_path.write_text(
        update_metadata_text(metadata_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    init_path = target_plugin_dir / "__init__.py"
    init_path.write_text(
        update_init_text(init_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    return target_plugin_dir


def zip_tree(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_dir():
                continue
            if "__pycache__" in file_path.parts or file_path.suffix in {".pyc", ".pyo"}:
                continue
            zf.write(file_path, file_path.relative_to(source_dir.parent).as_posix())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DIST_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    build_root = output_dir / "_build_test_plugin"
    if build_root.exists():
        shutil.rmtree(build_root)
    build_root.mkdir(parents=True)

    test_plugin_dir = prepare_test_plugin_tree(build_root)
    metadata_text = (test_plugin_dir / "metadata.txt").read_text(encoding="utf-8")
    version_line = next(
        line for line in metadata_text.splitlines() if line.startswith("version=")
    )
    version = version_line.split("=", 1)[1].strip()

    zip_path = output_dir / f"{TEST_PLUGIN_DIRNAME}_v{version}.zip"
    metadata_copy_path = output_dir / f"{TEST_PLUGIN_DIRNAME}_metadata.txt"

    if zip_path.exists():
        zip_path.unlink()
    shutil.copy2(test_plugin_dir / "metadata.txt", metadata_copy_path)
    zip_tree(test_plugin_dir, zip_path)
    print(f"Created {zip_path}")
    print(f"Created {metadata_copy_path}")


if __name__ == "__main__":
    main()
