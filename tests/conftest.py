from __future__ import annotations

import os
from pathlib import Path

import pytest

import pycrg

# draw without a display; set before any test imports matplotlib
os.environ["MPLBACKEND"] = "Agg"

DATA = Path(__file__).parent / "data"
CRG_TXT = DATA / "crg-txt"
SAMPLE = DATA / "sample.crg"  # large binary sample; not part of the sdist


@pytest.fixture(autouse=True)
def isolated_opencrg():
    """Reset the global OpenCRG state that a test may change."""
    yield
    pycrg.clear_callbacks()
    pycrg.set_message_level(pycrg.MSG_LEVEL_NOTICE)
    pycrg.set_max_warn_messages(-1)
    pycrg.mem_release()


@pytest.fixture
def crg_txt() -> Path:
    return CRG_TXT


@pytest.fixture
def straight() -> Path:
    """A straight 22 m long, 3 m wide road (LRFI)."""
    return CRG_TXT / "handmade_straight.crg"


@pytest.fixture
def numpy():
    return pytest.importorskip("numpy")


@pytest.fixture
def plt():
    """matplotlib.pyplot (tests are skipped without matplotlib); closes all
    figures afterwards."""
    pyplot = pytest.importorskip("matplotlib.pyplot")
    yield pyplot
    pyplot.close("all")


@pytest.fixture
def write_road(tmp_path, numpy):
    """Write a small synthetic road with pycrg.write and return its path."""

    def write(name: str = "road.crg", **kwargs) -> Path:
        np = numpy
        nu = kwargs.pop("nu", 41)
        nv = kwargs.pop("nv", 7)
        du = kwargs.pop("du", 0.5)
        v = kwargs.pop("v", np.linspace(-1.5, 1.5, nv))
        rng = np.random.default_rng(7)
        z = kwargs.pop("z", 0.01 * rng.standard_normal((nu, nv)))
        path = tmp_path / name
        pycrg.write(path, z, du, v, **kwargs)
        return path

    return write
