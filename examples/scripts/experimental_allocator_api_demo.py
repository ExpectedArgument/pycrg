from __future__ import annotations

import os

from pycrg import experimental


if __name__ == "__main__":
    if os.getenv("PYCRG_ENABLE_UNSAFE_CALLBACKS") != "1":
        raise SystemExit("Set PYCRG_ENABLE_UNSAFE_CALLBACKS=1 before running this demo.")

    ptr = experimental.calloc(1, 64)
    print(f"calloc ptr: {ptr}")

    ptr = experimental.realloc(ptr, 128)
    print(f"realloc ptr: {ptr}")

    experimental.free(ptr)
    print("free done")
