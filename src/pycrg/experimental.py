from __future__ import annotations

"""Experimental and unsafe APIs.

This module exposes low-level allocator hooks and direct allocator calls.
These functions can crash the process if used incorrectly.
"""

import os
import warnings
from typing import Protocol, TypeAlias

from . import _native

_UNSAFE_ENV = "PYCRG_ENABLE_UNSAFE_CALLBACKS"

Pointer: TypeAlias = int


class CallocCallback(Protocol):
    def __call__(self, nmemb: int, size: int) -> Pointer | None: ...


class ReallocCallback(Protocol):
    def __call__(self, ptr: Pointer, size: int) -> Pointer | None: ...


class FreeCallback(Protocol):
    def __call__(self, ptr: Pointer) -> None: ...


def _ensure_enabled() -> None:
    if os.getenv(_UNSAFE_ENV) != "1":
        raise RuntimeError(
            "Unsafe allocator callbacks are disabled. "
            f"Set {_UNSAFE_ENV}=1 to enable them."
        )


def _warn() -> None:
    warnings.warn(
        "Using allocator callbacks can crash the process if pointers are invalid. "
        "Use only if you fully control OpenCRG memory callback behavior.",
        RuntimeWarning,
        stacklevel=2,
    )


def set_calloc_callback(callback: CallocCallback | None) -> None:
    """Register callback for OpenCRG calloc hook.

    Callback should return an integer pointer value (or None).
    """
    _ensure_enabled()
    _warn()
    _native.calloc_set_callback(callback)


def set_realloc_callback(callback: ReallocCallback | None) -> None:
    """Register callback for OpenCRG realloc hook."""
    _ensure_enabled()
    _warn()
    _native.realloc_set_callback(callback)


def set_free_callback(callback: FreeCallback | None) -> None:
    """Register callback for OpenCRG free hook."""
    _ensure_enabled()
    _warn()
    _native.free_set_callback(callback)


def clear_unsafe_callbacks() -> None:
    """Clear all allocator callbacks in OpenCRG."""
    _ensure_enabled()
    _native.calloc_set_callback(None)
    _native.realloc_set_callback(None)
    _native.free_set_callback(None)


def calloc(nmemb: int, size: int) -> Pointer:
    """Call OpenCRG calloc and return pointer address as integer."""
    _ensure_enabled()
    _warn()
    return int(_native.calloc(int(nmemb), int(size)))


def realloc(ptr: Pointer, size: int) -> Pointer:
    """Call OpenCRG realloc and return new pointer address as integer."""
    _ensure_enabled()
    _warn()
    return int(_native.realloc(int(ptr), int(size)))


def free(ptr: Pointer) -> None:
    """Call OpenCRG free for a pointer address integer."""
    _ensure_enabled()
    _warn()
    _native.free(int(ptr))
