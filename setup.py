import os
import platform
import struct
from pathlib import Path

from setuptools import Extension, setup

ROOT = Path(__file__).parent.resolve()
SRC = ROOT / "src" / "pycrg"
VENDOR_BASE = SRC / "vendor" / "opencrg" / "c-api" / "baselib"

opencrg_sources = [
    VENDOR_BASE / "src" / "crgMgr.c",
    VENDOR_BASE / "src" / "crgMsg.c",
    VENDOR_BASE / "src" / "crgStatistics.c",
    VENDOR_BASE / "src" / "crgContactPoint.c",
    VENDOR_BASE / "src" / "crgEvalxy2uv.c",
    VENDOR_BASE / "src" / "crgEvaluv2xy.c",
    VENDOR_BASE / "src" / "crgEvalz.c",
    VENDOR_BASE / "src" / "crgEvalpk.c",
    VENDOR_BASE / "src" / "crgLoader.c",
    VENDOR_BASE / "src" / "crgOptionMgmt.c",
    VENDOR_BASE / "src" / "crgPortability.c",
]


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _is_32bit_x86() -> bool:
    # a 32-bit interpreter on a 64-bit kernel reports the kernel's machine
    machine = platform.machine().lower()
    return struct.calcsize("P") == 4 and machine in {"i386", "i486", "i586", "i686", "x86", "x86_64", "amd64"}


def _compile_args() -> list[str]:
    if os.name == "nt":
        return ["/O2"]
    args = ["-O3", "-std=c11"]
    if _is_32bit_x86():
        # Use SSE2 floating point, as on all other platforms. With the x87 FPU,
        # ISO C evaluates floating-point constants in extended precision, and
        # OpenCRG's check rejected its own default option check_eps (the double
        # 1e-6 compared less than the constant 1.0e-6).
        args += ["-msse2", "-mfpmath=sse"]
    return args


extension = Extension(
    name="pycrg._native",
    sources=[_rel(SRC / "_native.c"), *map(_rel, opencrg_sources)],
    include_dirs=[_rel(VENDOR_BASE / "inc")],
    extra_compile_args=_compile_args(),
)

setup(
    ext_modules=[extension],
)
