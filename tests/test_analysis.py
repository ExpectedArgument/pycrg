"""Peak detection and comparison, the crg_peakfinder and crg_isequal of the MATLAB tools."""

import math

import pytest

import pycrg
from pycrg import DataSet, RoadSurface

PEAKS = [(60, 10), (120, 30), (150, 20)]


@pytest.fixture
def spikes(numpy):
    """A gently undulating, curved 20 m x 4 m grid with three spikes: z, v, phi."""
    np = numpy
    v = np.linspace(-2.0, 2.0, 41)
    z = 0.002 * np.sin(np.arange(200)[:, None] / 7.0) * np.cos(v[None, :])
    z[60, 10] = 0.3
    z[120, 30] = 0.25
    z[150, 20] = -0.3
    return z, v, 0.002 * np.arange(199)


@pytest.fixture
def spiky_road(tmp_path, spikes):
    z, v, phi = spikes
    path = tmp_path / "spiky.crg"
    pycrg.write(path, z, 0.1, v, phi, mods={})
    return path


# ---------------------------------------------------------------------------
# find_peaks
# ---------------------------------------------------------------------------


def test_find_peaks(spiky_road):
    with DataSet.open(spiky_road) as dataset:
        peaks = pycrg.find_peaks(dataset)
    assert len(peaks) == 3
    assert list(zip(peaks.iu.tolist(), peaks.iv.tolist(), strict=True)) == PEAKS  # by cross, then long section
    assert peaks.u == pytest.approx([6.0, 12.0, 15.0])
    assert peaks.v == pytest.approx([-1.0, 1.0, 0.0])
    assert peaks.z == pytest.approx([0.3, 0.25, -0.3], rel=1e-6)
    assert peaks.search_iu == (0, 200)
    assert peaks.search_iv == (0, 41)


def test_find_peaks_in_ranges(spiky_road):
    with RoadSurface.open(spiky_road) as road:
        peaks = pycrg.find_peaks(road, iu=(100, 200), iv=(15, 41))
    assert list(zip(peaks.iu.tolist(), peaks.iv.tolist(), strict=True)) == PEAKS[1:]
    assert peaks.search_iu == (100, 200)
    assert peaks.search_iv == (15, 41)


def test_find_peaks_threshold_and_window(spiky_road):
    with DataSet.open(spiky_road) as dataset:
        assert len(pycrg.find_peaks(dataset, threshold=1e9)) == 0
        assert len(pycrg.find_peaks(dataset, window=5)) == 3


def test_no_peaks_on_a_smooth_road(write_road, numpy):
    np = numpy
    z = 0.002 * np.sin(np.arange(60)[:, None] / 5.0) * np.ones((1, 11))
    with DataSet.open(write_road(z=z, nu=60, nv=11, mods={})) as dataset:
        peaks = pycrg.find_peaks(dataset)
    assert len(peaks) == 0
    assert peaks.iu.shape == peaks.u.shape == peaks.z.shape == (0,)


def test_find_peaks_ignores_nan(write_road, numpy):
    np = numpy
    z = np.zeros((40, 15))
    z[:, :3] = np.nan  # no NaN handling without modifiers
    z[20, 8] = 0.4
    with DataSet.open(write_road(z=z, nu=40, nv=15, mods={})) as dataset:
        peaks = pycrg.find_peaks(dataset)
    assert list(zip(peaks.iu.tolist(), peaks.iv.tolist(), strict=True)) == [(20, 8)]


def test_find_peaks_arguments(spiky_road):
    with DataSet.open(spiky_road) as dataset:
        with pytest.raises(ValueError, match="window"):
            pycrg.find_peaks(dataset, window=0)
        with pytest.raises(ValueError, match="threshold"):
            pycrg.find_peaks(dataset, threshold=math.nan)
        with pytest.raises(ValueError, match="at least 2 \\* window \\+ 2 = 8"):
            pycrg.find_peaks(dataset, iu=(0, 7))
        with pytest.raises(ValueError, match="illegal iu index range"):
            pycrg.find_peaks(dataset, iu=(5, 3))
        with pytest.raises(ValueError, match="illegal iv index range"):
            pycrg.find_peaks(dataset, iv=(0, 42))
        with pytest.raises(TypeError, match="pair of integers"):
            pycrg.find_peaks(dataset, iu=(0.5, 10))
    with pytest.raises(TypeError, match=r"DataSet or pycrg\.RoadSurface"):
        pycrg.find_peaks(str(spiky_road))


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------


def test_compare_identical(spiky_road):
    with DataSet.open(spiky_road) as a, DataSet.open(spiky_road) as b:
        result = pycrg.compare(a, b)
    assert result.identical
    assert result
    assert result.errors == ()
    assert result.warnings == ()
    assert result.max_difference == 0.0
    assert result.difference.shape == result.relative.shape == (200, 41)
    assert result.u.shape == (200,)
    assert result.v.shape == (41,)
    assert result.tolerance == pytest.approx(1e-6)
    assert result.paths == (str(spiky_road), str(spiky_road))


def test_compare_changed_elevation(tmp_path, spiky_road, spikes, numpy):
    z, v, phi = spikes
    changed = z.copy()
    changed[100, 20] += 0.05
    other = tmp_path / "changed.crg"
    pycrg.write(other, changed, 0.1, v, phi, mods={})
    with DataSet.open(spiky_road) as a, RoadSurface.open(other) as b:
        result = pycrg.compare(a, b)
    assert not result.identical
    assert not result
    assert result.errors == ()
    assert result.max_difference == pytest.approx(0.05, rel=1e-6)
    assert numpy.unravel_index(numpy.nanargmax(result.difference), result.difference.shape) == (100, 20)
    expected = (changed[100, 20] / z[100, 20] - 1) * 100
    assert result.relative[100, 20] == pytest.approx(expected, rel=1e-4)


def test_compare_different_grids(write_road, numpy):
    np = numpy
    long = write_road("long.crg", z=np.zeros((41, 7)), mods={})
    short = write_road("short.crg", z=np.zeros((31, 7)), nu=31, mods={})
    wide = write_road("wide.crg", z=np.zeros((41, 7)), v=np.linspace(-2, 2, 7), mods={})
    moved = write_road("moved.crg", z=np.zeros((41, 7)), x0=1.0, mods={})
    with DataSet.open(long) as a:
        with DataSet.open(short) as b:
            result = pycrg.compare(a, b)
        assert not result.identical
        assert "different u-dimension" in result.errors
        assert "uend of CRG-files are not equal" in result.errors
        assert "different z-dimension" in result.errors
        assert result.max_difference == 0.0  # flat roads: the elevation agrees
        with DataSet.open(wide) as b:
            result = pycrg.compare(a, b)
        assert "cross cut positions are not equal" in result.errors
        assert "vmin of CRG-files are not equal" in result.errors
        assert "different u-dimension" not in result.errors
        with DataSet.open(moved) as b:
            result = pycrg.compare(a, b)
        assert result.errors == ("xbeg of CRG-files are not equal", "xend of CRG-files are not equal")
        assert not result.identical


def test_compare_header_warnings(write_road, numpy):
    z = numpy.zeros((41, 7))
    first = write_road("first.crg", z=z, comment="first", mods={})
    second = write_road("second.crg", z=z, comment="second", opts={"border_mode_u": 1})
    with DataSet.open(first) as a, DataSet.open(second, apply_modifiers=False) as b:
        result = pycrg.compare(a, b)
    assert result.identical  # warnings do not affect the result
    assert len(result.warnings) == 3
    assert any("comment" in message for message in result.warnings)
    assert any("ROAD_CRG_OPTS" in message for message in result.warnings)
    assert any("ROAD_CRG_MODS" in message for message in result.warnings)
