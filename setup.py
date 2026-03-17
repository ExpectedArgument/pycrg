from pathlib import Path
import os

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


def _compile_args() -> list[str]:
    if os.name == "nt":
        return ["/O2"]
    return ["-O3", "-std=c11"]


extension = Extension(
    name="pycrg._native",
    sources=[_rel(SRC / "_native.c"), *map(_rel, opencrg_sources)],
    include_dirs=[_rel(VENDOR_BASE / "inc")],
    extra_compile_args=_compile_args(),
)

setup(
    ext_modules=[extension],
)
