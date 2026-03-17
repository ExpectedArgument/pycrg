from __future__ import annotations

import os

from pycrg import experimental


if __name__ == "__main__":
    if os.getenv("PYCRG_ENABLE_UNSAFE_CALLBACKS") != "1":
        raise SystemExit(
            "Set PYCRG_ENABLE_UNSAFE_CALLBACKS=1 before running this demo."
        )

    def calloc_cb(nmemb: int, size: int):
        print(f"calloc callback nmemb={nmemb}, size={size}")
        return None

    def realloc_cb(ptr: int, size: int):
        print(f"realloc callback ptr={ptr}, size={size}")
        return None

    def free_cb(ptr: int):
        print(f"free callback ptr={ptr}")

    experimental.set_calloc_callback(calloc_cb)
    experimental.set_realloc_callback(realloc_cb)
    experimental.set_free_callback(free_cb)
    experimental.clear_unsafe_callbacks()

    print("Unsafe allocator callbacks were registered and cleared.")
    print("See experimental_allocator_api_demo.py for direct calloc/realloc/free usage.")
