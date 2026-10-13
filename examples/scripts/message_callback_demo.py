from __future__ import annotations

import logging
from pathlib import Path

import pycrg

if __name__ == "__main__":
    sample = Path(__file__).resolve().parents[2] / "tests" / "data" / "crg-txt" / "handmade_straight.crg"

    # By default, OpenCRG messages go to the "pycrg" logger: warnings and
    # errors are shown, the notices of the loader are not.
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    with pycrg.DataSet.open(sample):
        pass

    # A callback receives the messages instead of the logger.
    def handler(level: int, message: str) -> None:
        print(f"[OpenCRG level={level}] {message.rstrip()}")

    pycrg.set_message_callback(handler)
    pycrg.msg_print(pycrg.MSG_LEVEL_NOTICE, "Hello from the pycrg message callback")
    pycrg.clear_message_callback()

    # Failures carry their messages in the exception.
    try:
        pycrg.DataSet.open(Path(__file__))
    except pycrg.OpenCRGLoadError as error:
        print("load failed:", error)
        print("messages:", len(error.messages))
