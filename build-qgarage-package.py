from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PLUGIN_DIR = REPO_ROOT / "qgarage"
DIST_DIR = REPO_ROOT / "dist"


def metadata_version(metadata_path: Path) -> str:
    for line in metadata_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("version="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"No version= found in {metadata_path}")


def build_zip(plugin_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in plugin_dir.rglob("*"):
            if file_path.is_dir():
                continue
            if "__pycache__" in file_path.parts or file_path.suffix in {".pyc", ".pyo"}:
                continue
            zf.write(file_path, file_path.relative_to(plugin_dir.parent).as_posix())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DIST_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    version = metadata_version(PLUGIN_DIR / "metadata.txt")
    zip_path = output_dir / f"qgarage_v{version}.zip"

    if zip_path.exists():
        zip_path.unlink()
    build_zip(PLUGIN_DIR, zip_path)
    print(f"Created {zip_path}")


if __name__ == "__main__":
    main()
