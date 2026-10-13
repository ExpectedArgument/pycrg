from __future__ import annotations

import argparse
from pathlib import Path

from pycrg import DataSet, mem_release


def default_input_file() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "data" / "crg-txt" / "handmade_straight.crg"


def main() -> int:
    parser = argparse.ArgumentParser(description="Python port of OpenCRG C demo: Curvature")
    parser.add_argument("filename", nargs="?", default=str(default_input_file()), help="Input .crg file")
    args = parser.parse_args()

    dataset = DataSet.open(args.filename, apply_modifiers=False)
    if not dataset.check():
        raise RuntimeError("could not validate crg data")

    dataset.close()
    mem_release()
    print("normal termination")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
