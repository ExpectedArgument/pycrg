from __future__ import annotations

from pycrg import clear_message_callback, msg_print, set_message_callback


def handler(level: int, message: str) -> int:
    print(f"[OpenCRG level={level}] {message}")
    return 0


if __name__ == "__main__":
    set_message_callback(handler)
    msg_print(3, "Hello from pycrg message callback")
    clear_message_callback()
