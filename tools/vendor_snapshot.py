from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create vendor snapshot from an OpenCRG clone.")
    parser.add_argument(
        "--source",
        required=True,
        help="Path to local OpenCRG repository clone",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    source_root = Path(args.source).resolve()
    dest_root = project_root / "src" / "pycrg" / "vendor" / "opencrg"

    required = [
        source_root / "LICENSE",
        source_root / "NOTICE",
        source_root / "c-api" / "baselib" / "inc" / "crgBaseLib.h",
        source_root / "c-api" / "baselib" / "inc" / "crgBaseLibPrivate.h",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Required OpenCRG files missing:\n" + "\n".join(missing))

    src_dir = source_root / "c-api" / "baselib" / "src"
    c_files = sorted(src_dir.glob("*.c"))
    if not c_files:
        raise FileNotFoundError(f"No C sources found under {src_dir}")

    if dest_root.exists():
        shutil.rmtree(dest_root)

    copy_file(source_root / "LICENSE", dest_root / "LICENSE")
    copy_file(source_root / "NOTICE", dest_root / "NOTICE")
    inc_dir = source_root / "c-api" / "baselib" / "inc"
    for header in sorted(inc_dir.glob("*.h")):
        copy_file(header, dest_root / "c-api" / "baselib" / "inc" / header.name)
    for src in c_files:
        copy_file(src, dest_root / "c-api" / "baselib" / "src" / src.name)

    print(f"Vendor snapshot updated from: {source_root}")


if __name__ == "__main__":
    main()
