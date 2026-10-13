"""The experimental allocator callbacks."""

import os
import subprocess
import sys
import textwrap

import pytest

ALLOCATOR_SCRIPT = textwrap.dedent(
    """
    import ctypes, ctypes.util, sys, warnings
    import pycrg
    from pycrg import experimental

    libc = ctypes.CDLL(ctypes.util.find_library("c") if sys.platform == "darwin" else None)
    libc.calloc.restype = ctypes.c_void_p
    libc.calloc.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
    libc.realloc.restype = ctypes.c_void_p
    libc.realloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    libc.free.argtypes = [ctypes.c_void_p]

    live = set()

    def calloc(count, size):
        pointer = libc.calloc(count, size)
        live.add(pointer)
        return pointer

    def realloc(pointer, size):
        result = libc.realloc(pointer or None, size)
        live.discard(pointer)
        live.add(result)
        return result

    def free(pointer):
        if pointer:
            live.remove(pointer)  # fails for memory not allocated by calloc/realloc
            libc.free(pointer)

    warnings.simplefilter("ignore", RuntimeWarning)
    experimental.set_calloc_callback(calloc)
    experimental.set_realloc_callback(realloc)
    experimental.set_free_callback(free)

    for path in sys.argv[1:]:
        try:
            dataset = pycrg.DataSet.open(path, check=True)
        except pycrg.OpenCRGError:
            continue
        dataset.u_range()
        dataset.close()
    pycrg.mem_release()
    experimental.clear_unsafe_callbacks()
    print(len(live))
    """
)


@pytest.mark.skipif(sys.platform == "win32", reason="uses the C library through ctypes")
def test_allocator_callbacks_see_every_allocation(crg_txt, tmp_path):
    garbage = tmp_path / "garbage.crg"
    garbage.write_text("not a CRG file\n")
    files = [crg_txt / "handmade_straight.crg", crg_txt / "fileref.crg", garbage]
    result = subprocess.run(
        [sys.executable, "-c", ALLOCATOR_SCRIPT, *map(str, files)],
        capture_output=True,
        text=True,
        timeout=120,
        env=dict(os.environ, PYCRG_ENABLE_UNSAFE_CALLBACKS="1"),
        cwd=crg_txt,
    )
    assert result.returncode == 0, result.stderr
    assert "Exception ignored" not in result.stderr, result.stderr
    assert result.stdout.strip() == "0"


def test_allocator_api_requires_opt_in(monkeypatch):
    from pycrg import experimental

    monkeypatch.delenv("PYCRG_ENABLE_UNSAFE_CALLBACKS", raising=False)
    for function, args in (
        (experimental.set_calloc_callback, (None,)),
        (experimental.set_realloc_callback, (None,)),
        (experimental.set_free_callback, (None,)),
        (experimental.clear_unsafe_callbacks, ()),
        (experimental.calloc, (1, 8)),
        (experimental.realloc, (0, 8)),
        (experimental.free, (0,)),
    ):
        with pytest.raises(RuntimeError, match="PYCRG_ENABLE_UNSAFE_CALLBACKS"):
            function(*args)


def test_allocator_functions(monkeypatch):
    from pycrg import experimental

    monkeypatch.setenv("PYCRG_ENABLE_UNSAFE_CALLBACKS", "1")
    with pytest.warns(RuntimeWarning):
        pointer = experimental.calloc(4, 8)
    assert pointer != 0
    with pytest.warns(RuntimeWarning):
        pointer = experimental.realloc(pointer, 64)
    with pytest.warns(RuntimeWarning):
        experimental.free(pointer)
