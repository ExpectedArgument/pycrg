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
    parser = argparse.ArgumentParser(description="Python port of OpenCRG C demo: Simple")
    parser.add_argument("filename", nargs="?", default=str(default_input_file()), help="Input .crg file")
    args = parser.parse_args()

    dataset = DataSet.open(args.filename)
    if not dataset.check():
        raise RuntimeError("could not validate crg data")

    dataset.modifiers_print()
    dataset.modifiers_apply()

    cp = dataset.create_contact_point()
    print("performing tests...")

    x = 0.0
    while x < 22.0:
        y = -1.5
        while y <= 1.5:
            z = cp.try_xy_to_z(x, y)
            if z is None:
                print(f"warning: error converting x/y = {x:+10.4f} / {y:+10.4f} to z")
                y += 0.5
                continue
            print(f"x/y = {x:+10.4f} / {y:+10.4f} -> z = {z:+10.4f}")
            y += 0.5
        x += 2.0

    cp.close()
    dataset.close()
    mem_release()
    print("normal termination")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
