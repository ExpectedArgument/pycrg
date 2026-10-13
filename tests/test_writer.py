"""Writing CRG files (finding 9)."""

import math

import pytest

import pycrg
from pycrg import DataSet
from pycrg.writer import format_number

FORMATS = ["KRBI", "KDBI", "LRFI", "LDFI"]


@pytest.mark.parametrize(
    ("value", "text"),
    [
        # the examples of str_num2strn of the OpenCRG MATLAB tools
        (2e-4 / 3, "66667e-09"),
        (-2e-4 / 3, "-66667e-9"),
        (2e-3 / 3, "666667e-9"),
        (-2e-3 / 3, "-66667e-8"),
        (2e-2 / 3, ".00666667"),
        (-2e-2 / 3, "-.0066667"),
        (2 / 3, ".66666667"),
        (-2 / 3, "-.6666667"),
        (20 / 3, "6.6666667"),
        (-20 / 3, "-6.666667"),
        (2e8 / 3, " 66666667"),
        (-2e8 / 3, "-66666667"),
        (2e9 / 3, "666666667"),
        (-2e9 / 3, "-666667e3"),
        (2e10 / 3, "6666667e3"),
        (-2e10 / 3, "-666667e4"),
        (0.0, "000000000"),
        (math.nan, "*********"),
        (0.9999999999, "1.0000000"),
    ],
)
def test_format_number(value, text):
    assert format_number(value, 9) == text
    if not math.isnan(value):
        assert float(text) == pytest.approx(value, rel=1e-4, abs=1e-12)


def test_format_number_double_width():
    for value in (math.pi, -math.e * 1e-7, 123456.789, 1e-300, -1e300):
        text = format_number(value, 19)
        assert len(text) == 19
        assert float(text) == pytest.approx(value, rel=1e-13)


@pytest.mark.parametrize("fmt", FORMATS)
def test_round_trip(tmp_path, numpy, fmt):
    np = numpy
    rng = np.random.default_rng(3)
    nu, nv, du = 121, 9, 0.25
    v = np.linspace(-2.0, 2.0, nv)
    z = 0.02 * rng.standard_normal((nu, nv))
    z[:15, 0] = np.nan
    z[40:60, -2:] = np.nan
    phi = 0.3 + 0.004 * np.arange(nu - 1)
    slope = 0.01 * np.sin(np.arange(nu - 1) / 9.0)
    bank = 0.03 * np.cos(np.arange(nu) / 11.0)
    path = tmp_path / f"road_{fmt}.crg"
    pycrg.write(
        path,
        z,
        du,
        v,
        phi,
        u0=5.0,
        x0=100.0,
        y0=-50.0,
        z0=3.0,
        slope=slope,
        banking=bank,
        fmt=fmt,
        mods={},
        comment="round trip",
    )

    single = fmt[1] == "R"
    # OpenCRG keeps the grid in single precision, whatever the format
    precision = {"KRBI": 0.0, "KDBI": 0.0, "LRFI": 1e-7, "LDFI": 1e-8}[fmt]
    with DataSet.open(path, check=True) as dataset:
        assert dataset.u_range() == pytest.approx((5.0, 5.0 + du * (nu - 1)))
        grid = dataset.grid()
    expected = z.astype(np.float32).astype(np.float64)
    assert np.array_equal(np.isnan(grid.z), np.isnan(z))
    assert np.nanmax(np.abs(grid.z - expected)) <= precision
    assert np.allclose(grid.v, v)

    headings = phi.astype(np.float32).astype(np.float64) if single else phi
    x = np.concatenate(([100.0], 100.0 + np.cumsum(du * np.cos(headings))))
    y = np.concatenate(([-50.0], -50.0 + np.cumsum(du * np.sin(headings))))
    assert np.max(np.abs(grid.x - x)) < 1e-6
    assert np.max(np.abs(grid.y - y)) < 1e-6
    ref_z = np.concatenate(([3.0], 3.0 + np.cumsum(du * slope)))
    assert np.max(np.abs(grid.ref_z - ref_z)) < 1e-6
    assert np.max(np.abs(grid.bank - bank)) < 1e-6


def test_straight_line_and_explicit_positions(tmp_path, numpy):
    np = numpy
    v = np.array([-1.5, -0.4, 0.0, 0.25, 1.75])  # not equidistant
    z = np.tile(np.linspace(0.0, 0.1, 5), (11, 1))
    path = tmp_path / "straight.crg"
    pycrg.write(path, z, 1.0, v, math.pi / 2, x0=5.0, mods={})
    header = pycrg.read_header(path)
    names = [channel.name for channel in header.channels[1:3]]
    assert names == ["long section at v = -1.5", "long section at v = -0.4"]
    with DataSet.open(path) as dataset:
        cp = dataset.create_contact_point()
        assert cp.uv_to_xy(10.0, 0.0) == pytest.approx((5.0, 10.0))
        assert dataset.grid().v.tolist() == v.tolist()
        assert cp.uv_to_z(3.0, 0.25) == pytest.approx(0.075, abs=1e-7)


def test_headings_as_stored_in_files(tmp_path, numpy):
    np = numpy
    z = np.zeros((11, 3))
    segments = np.full(10, 0.25)
    pycrg.write(tmp_path / "a.crg", z, 1.0, [-1.0, 0.0, 1.0], segments, mods={})
    pycrg.write(tmp_path / "b.crg", z, 1.0, [-1.0, 0.0, 1.0], np.concatenate(([99.0], segments)), mods={})
    assert (tmp_path / "a.crg").read_bytes() == (tmp_path / "b.crg").read_bytes()


def test_end_point(tmp_path, numpy):
    np = numpy
    z = np.zeros((101, 3))
    headings = np.linspace(0.0, 0.5, 100)
    pycrg.write(tmp_path / "end.crg", z, 0.5, [-1.0, 0.0, 1.0], headings, end_xy=(49.0, 12.0), mods={})
    with DataSet.open(tmp_path / "end.crg") as dataset:
        x, y = dataset.create_contact_point().uv_to_xy(50.0, 0.0)
    assert (x, y) == pytest.approx((49.0, 12.0), abs=1e-6)


def test_options_and_modifiers_by_id(tmp_path, numpy):
    z = numpy.zeros((5, 3))
    path = tmp_path / "ids.crg"
    pycrg.write(
        path,
        z,
        1.0,
        [-1.0, 0.0, 1.0],
        opts={pycrg.CP_OPTION_BORDER_MODE_U: pycrg.BORDER_MODE_NONE, "border_offset_v": 0.5},
        mods={pycrg.MOD_REF_LINE_OFFSET_Z: 2.0},
    )
    header = pycrg.read_header(path)
    assert header.options == {"border_mode_u": 0.0, "border_offset_v": 0.5}
    assert header.modifiers == {"refline_offset_z": 2.0}
    with DataSet.open(path) as dataset:
        cp = dataset.create_contact_point()
        assert cp.option_get_int(pycrg.CP_OPTION_BORDER_MODE_U) == pycrg.BORDER_MODE_NONE
        assert cp.try_uv_to_z(-1.0, 0.0) is None
        assert cp.uv_to_z(1.0, 0.0) == pytest.approx(2.0)


def test_text_format_nan_and_layout(tmp_path, numpy):
    np = numpy
    z = np.arange(30.0).reshape(3, 10) / 100
    z[1, 0] = np.nan
    path = tmp_path / "text.crg"
    pycrg.write(path, z, 1.0, np.linspace(0.0, 0.9, 10), fmt="LRFI")
    data = path.read_text().split("$" * 72 + "\n", 1)[1].splitlines()
    assert len(data) == 6  # 10 values per record: 8 + 2 per line
    assert all(len(line) == 80 for line in data[0::2])
    assert data[2].startswith("*" * 10)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"z": [[0.0, 1.0]]}, "at least 2"),
        ({"z": [0.0, 1.0]}, "two-dimensional"),
        ({"z": [[0.0, float("nan"), 1.0], [0.0, 0.0, 0.0]]}, "between valid values"),
        ({"z": [[float("nan")] * 3, [0.0, 0.0, 0.0]]}, "no value"),
        ({"z": [[float("inf"), 0.0, 0.0], [0.0, 0.0, 0.0]]}, "infinite"),
        ({"v": [0.0, 0.0, 1.0]}, "strictly increasing"),
        ({"v": [0.0, 1.0]}, "3 entries"),
        ({"du": 0.0}, "positive"),
        ({"du": float("nan")}, "finite"),
        ({"phi": [0.1, 0.2, 0.3]}, "segment"),
        ({"fmt": "XYZW"}, "fmt"),
        ({"comment": "$CT"}, "must not start"),
        ({"comment": "x" * 80}, "longer than 72"),
        ({"opts": {"no_such_option": 1}}, "unknown option"),
        ({"mods": {999: 1.0}}, "unknown modifier id"),
        ({"mods": {"grid_nan_mode": 1.5}}, "integer"),
        ({"road": {"reference_line_start_x": 1.0}}, "cannot be set"),
        ({"banking": [0.1]}, "banking"),
    ],
)
def test_validation(tmp_path, numpy, change, message):
    arguments = {"z": numpy.zeros((2, 3)), "du": 1.0, "v": [-1.0, 0.0, 1.0]}
    arguments.update(change)
    with pytest.raises(ValueError, match=message):
        pycrg.write(tmp_path / "invalid.crg", **arguments)
    assert not (tmp_path / "invalid.crg").exists()


def test_single_precision_overflow(tmp_path, numpy):
    with pytest.raises(ValueError, match="single precision"):
        pycrg.write(tmp_path / "big.crg", numpy.full((2, 2), 1e39), 1.0, [0.0, 1.0])
    pycrg.write(tmp_path / "big.crg", numpy.full((2, 2), 1e39), 1.0, [0.0, 1.0], fmt="KDBI")


def test_default_comment(tmp_path, numpy):
    pycrg.write(tmp_path / "c.crg", numpy.zeros((2, 2)), 1.0, [0.0, 1.0])
    assert pycrg.read_header(tmp_path / "c.crg").comment == f"CRG file written by pycrg {pycrg.__version__}"
