from __future__ import annotations

import argparse
import logging
from pathlib import Path

from pycrg import MSG_LEVEL_DEBUG, DataSet, set_message_level


def default_input_file() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "data" / "crg-txt" / "handmade_straight.crg"


def main() -> int:
    parser = argparse.ArgumentParser(description="Python port of OpenCRG C demo: Reader")
    parser.add_argument("filename", nargs="?", default=str(default_input_file()), help="Input .crg file")
    args = parser.parse_args()

    # show the OpenCRG messages, as the C demos print them
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

    set_message_level(MSG_LEVEL_DEBUG)

    dataset = DataSet.open(args.filename, apply_modifiers=False)
    dataset.print_header()
    dataset.print_channel_info()
    dataset.print_road_info()

    if not dataset.check():
        raise RuntimeError("could not validate crg data")

    dataset.close()
    print("normal termination")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
