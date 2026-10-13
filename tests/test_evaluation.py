"""Evaluation, transforms, vectorised evaluation and grid access (findings 5, 10, 11)."""

import math

import pytest

import pycrg
from pycrg import (
    BORDER_MODE_NONE,
    CP_OPTION_BORDER_MODE_U,
    CP_OPTION_BORDER_MODE_V,
    DataSet,
    OpenCRGError,
    OpenCRGEvaluationError,
    RoadSurface,
)


@pytest.fixture
def curved(crg_txt):
    with RoadSurface.open(crg_txt / "handmade_curved_banked_sloped.crg") as road:
        yield road


def test_evaluation_error_type(straight):
    with RoadSurface.open(straight) as road:
        road.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_NONE)
        with pytest.raises(OpenCRGEvaluationError, match=r"\(u, v\) = \(-1000.0, 0.0\)") as info:
            road.uv_to_z(-1000.0, 0.0)
        assert isinstance(info.value, OpenCRGError)
        assert isinstance(info.value, RuntimeError)
        assert road.try_uv_to_z(-1000.0, 0.0) is None
        assert pycrg.OpenCRGEvaluationError is pycrg.errors.OpenCRGEvaluationError


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_input_is_refused(straight, value):
    with RoadSurface.open(straight) as road:
        for function in (road.uv_to_z, road.xy_to_z, road.uv_to_xy, road.xy_to_uv, road.uv_to_pk, road.xy_to_pk):
            with pytest.raises(OpenCRGEvaluationError):
                function(value, 0.0)
            with pytest.raises(OpenCRGEvaluationError):
                function(0.0, value)


def test_argument_types(straight):
    with RoadSurface.open(straight) as road:
        assert road.uv_to_z(1, 0) == road.uv_to_z(1.0, 0.0)
        with pytest.raises(TypeError):
            road.uv_to_z("1", 0.0)  # type: ignore[arg-type]


def test_round_trip(curved):
    for u in (0.5, 7.25, 15.0):
        for v in (-1.0, 0.0, 1.25):
            x, y = curved.uv_to_xy(u, v)
            assert curved.xy_to_uv(x, y) == pytest.approx((u, v), abs=1e-9)
            assert curved.xy_to_z(x, y) == pytest.approx(curved.uv_to_z(u, v), abs=1e-9)


def test_many_matches_scalar(curved, numpy):
    np = numpy
    u = np.linspace(-5.0, 30.0, 37)
    v = np.linspace(-3.0, 3.0, 13)
    uu, vv = np.meshgrid(u, v, indexing="ij")
    z = curved.uv_to_z_many(uu, vv)
    assert z.shape == uu.shape
    for (i, j), value in np.ndenumerate(z):
        assert value == curved.uv_to_z(uu[i, j], vv[i, j])

    x, y = curved.uv_to_xy_many(u, 0.5)  # broadcasting
    assert x.shape == y.shape == u.shape
    for index in range(len(u)):
        assert (x[index], y[index]) == curved.uv_to_xy(u[index], 0.5)

    uu2, vv2 = curved.xy_to_uv_many(x, y)
    assert np.allclose(uu2, u) and np.allclose(vv2, 0.5)
    assert np.array_equal(curved.xy_to_z_many(x, y), [curved.xy_to_z(a, b) for a, b in zip(x, y, strict=True)])
    phi, _ = curved.uv_to_pk_many(u, 0.0)
    assert np.array_equal(phi, [curved.uv_to_pk(a, 0.0)[0] for a in u])
    phi2, _ = curved.xy_to_pk_many(x, y)
    assert phi2.shape == u.shape


def test_many_failures_are_nan(straight, numpy):
    np = numpy
    with RoadSurface.open(straight) as road:
        road.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_NONE)
        z = road.uv_to_z_many([1.0, -100.0, np.nan, 2.0], 0.0)
        assert np.isnan(z).tolist() == [False, True, True, False]
        assert z[0] == road.uv_to_z(1.0, 0.0)
        x, y = road.uv_to_xy_many([np.inf, 1.0], [0.0, 0.0])
        assert np.isnan(x[0]) and np.isnan(y[0]) and not np.isnan(x[1])


def test_many_accepts_any_layout(straight, numpy):
    np = numpy
    with RoadSurface.open(straight) as road:
        u = np.arange(20.0, dtype=">f8")[::2]  # big-endian, strided
        v = np.float32(0.25)
        expected = [road.uv_to_z(a, 0.25) for a in u]
        assert road.uv_to_z_many(u, v).tolist() == expected
        assert road.uv_to_z_many(3.0, 0.25).shape == ()
        assert road.uv_to_z_many([], []).shape == (0,)
        with pytest.raises(ValueError):
            road.uv_to_z_many([1.0, 2.0], [1.0, 2.0, 3.0])


def test_grid(curved, numpy):
    np = numpy
    grid = curved.grid()
    nu, nv = grid.z.shape
    assert grid.u.shape == (nu,) and grid.v.shape == (nv,)
    assert (grid.u[0], grid.u[-1]) == curved.u_range()
    assert (grid.v[0], grid.v[-1]) == curved.v_range()
    for name in ("x", "y", "phi", "slope", "bank", "ref_z"):
        assert getattr(grid, name).shape == (nu,)
    # the elevation at the nodes is what uv_to_z returns
    expected = curved.uv_to_z_many(grid.u[:, None], grid.v[None, :])
    assert np.allclose(grid.elevation, expected, atol=1e-9, rtol=0)
    x, y = curved.uv_to_xy_many(grid.u, 0.0)
    assert np.allclose(grid.x, x) and np.allclose(grid.y, y)
    assert np.any(grid.bank != 0.0) and np.any(grid.ref_z != grid.ref_z[0])


def test_grid_of_closed_data_set(straight, numpy):
    dataset = DataSet.open(straight)
    dataset.close()
    with pytest.raises(pycrg.OpenCRGClosedError):
        dataset.grid()


def test_heading_is_the_heading_of_the_segment(crg_txt, numpy):
    # between two cross sections, the reference line is straight with the
    # heading stored for its end (OpenCRG 2.0.1 returned the previous one)
    with RoadSurface.open(crg_txt / "handmade_arc.crg") as road:
        grid = road.grid()
        middles = (grid.u[:-1] + grid.u[1:]) / 2
        phi, _ = road.uv_to_pk_many(middles, 0.0)
        assert numpy.allclose(phi, grid.phi[1:])
        assert numpy.ptp(grid.phi) > 0.1


@pytest.mark.parametrize("name", ["handmade_banked.crg", "handmade_circle.crg", "handmade_vtest.crg"])
def test_samples_load_and_check(crg_txt, name):
    with DataSet.open(crg_txt / name, check=True) as dataset:
        cp = dataset.create_contact_point()
        u_min, u_max = dataset.u_range()
        assert math.isfinite(cp.uv_to_z((u_min + u_max) / 2, 0.0))


def test_reflect_far_away(straight):
    with RoadSurface.open(straight) as road:
        road.option_set_int(CP_OPTION_BORDER_MODE_U, pycrg.BORDER_MODE_REFLECT)
        road.option_set_int(CP_OPTION_BORDER_MODE_V, pycrg.BORDER_MODE_REFLECT)
        assert math.isfinite(road.uv_to_z(1e15, -1e15))
        assert road.uv_to_z(22.0 + 3.0, 0.0) == pytest.approx(road.uv_to_z(22.0 - 3.0, 0.0))


def test_vendored_library_version():
    assert "2.0.1" in pycrg.get_release_info()
