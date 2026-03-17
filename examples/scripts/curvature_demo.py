from __future__ import annotations

import argparse
from pathlib import Path

from pycrg import DataSet, mem_release


def default_input_file() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "tests" / "data" / "sample.crg",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Python port of OpenCRG C demo: Curvature")
    parser.add_argument("filename", nargs="?", default=str(default_input_file()), help="Input .crg file")
    args = parser.parse_args()

    dataset = DataSet.open(args.filename)
    if not dataset.check():
        raise RuntimeError("could not validate crg data")

    dataset.close()
    mem_release()
    print("normal termination")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
