"""Basic use of the public API (the original smoke tests, on a small sample)."""

import pytest
from conftest import SAMPLE

from pycrg import (
    BORDER_MODE_NONE,
    CP_OPTION_BORDER_MODE_U,
    CP_OPTION_BORDER_MODE_V,
    MOD_SCALE_Z,
    DataSet,
    RoadSurface,
    clear_message_callback,
    experimental,
    get_release_info,
    msg_print,
    set_message_callback,
)


def test_open_ranges_eval_and_close(straight):
    road = RoadSurface.open(straight)

    umin, umax = road.u_range()
    vmin, vmax = road.v_range()
    assert (umin, umax) == (0.0, 22.0)
    assert (vmin, vmax) == (-1.5, 1.5)

    u_mid = (umin + umax) / 2.0
    v_mid = (vmin + vmax) / 2.0

    z_uv = road.uv_to_z(u_mid, v_mid)
    x, y = road.uv_to_xy(u_mid, v_mid)
    z_xy = road.xy_to_z(x, y)
    u2, v2 = road.xy_to_uv(x, y)

    assert isinstance(z_uv, float)
    assert z_xy == pytest.approx(z_uv, abs=1e-9)
    assert u2 == pytest.approx(u_mid, abs=1e-9)
    assert v2 == pytest.approx(v_mid, abs=1e-9)

    phi, curv = road.uv_to_pk(u_mid, v_mid)
    assert isinstance(phi, float)
    assert isinstance(curv, float)

    road.close()
    assert road.closed


def test_dataset_and_contact_point_full_surface(straight):
    assert "OpenCRG" in get_release_info()

    dataset = DataSet.open(straight)
    assert dataset.check() is True

    umin, umax = dataset.u_range()
    vmin, vmax = dataset.v_range()
    uinc, vinc = dataset.increments()
    assert umax >= umin
    assert vmax >= vmin
    assert uinc > 0.0
    assert vinc >= 0.0

    ok, is_closed, u_close_min, u_close_max = dataset.closed_track_data()
    assert ok is True
    assert is_closed == 0
    assert u_close_min != u_close_min  # NaN for a track that cannot be closed
    assert u_close_max != u_close_max

    assert dataset.modifier_set_double(MOD_SCALE_Z, 1.0)
    value = dataset.modifier_get_double(MOD_SCALE_Z)
    assert value == 1.0
    assert dataset.modifier_remove(MOD_SCALE_Z)
    assert dataset.modifier_get_double(MOD_SCALE_Z) is None

    cp = dataset.create_contact_point()
    assert cp.option_set_int(CP_OPTION_BORDER_MODE_U, 2)
    assert cp.option_get_int(CP_OPTION_BORDER_MODE_U) == 2

    u_mid = (umin + umax) / 2.0
    v_mid = (vmin + vmax) / 2.0
    x, y = cp.uv_to_xy(u_mid, v_mid)
    assert isinstance(cp.xy_to_z(x, y), float)
    phi, curv = cp.xy_to_pk(x, y)
    assert isinstance(phi, float)
    assert isinstance(curv, float)

    cp.close()
    dataset.close()


def test_try_eval_helpers_return_none_on_failure_and_values_on_success(straight):
    with DataSet.open(straight) as dataset:
        cp = dataset.create_contact_point()

        umin, umax = dataset.u_range()
        vmin, vmax = dataset.v_range()
        u_mid = (umin + umax) / 2.0
        v_mid = (vmin + vmax) / 2.0

        assert cp.try_uv_to_z(u_mid, v_mid) is not None
        assert cp.try_uv_to_xy(u_mid, v_mid) is not None
        assert cp.try_uv_to_pk(u_mid, v_mid) is not None

        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_NONE)
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_NONE)

        assert cp.try_uv_to_z(umin - 100000.0, vmax + 100000.0) is None


def test_message_callback_receives_messages():
    received = []

    def msg_cb(level: int, message: str) -> int:
        received.append((level, message))
        return 0

    set_message_callback(msg_cb)
    msg_print(3, "pycrg-callback-test")
    assert received[-1] == (3, "pycrg-callback-test")
    clear_message_callback()


def test_unsafe_allocator_callbacks_require_explicit_enable_flag(monkeypatch):
    monkeypatch.delenv("PYCRG_ENABLE_UNSAFE_CALLBACKS", raising=False)
    with pytest.raises(RuntimeError):
        experimental.set_calloc_callback(None)
    with pytest.raises(RuntimeError):
        experimental.calloc(1, 8)


@pytest.mark.skipif(not SAMPLE.exists(), reason="large sample data not available")
def test_large_binary_sample():
    with RoadSurface.open(SAMPLE, check=True) as road:
        umin, umax = road.u_range()
        assert umax - umin > 500.0
        # the file has no modifiers, so OpenCRG's defaults move its start to the origin
        assert road.uv_to_xy(umin, 0.0) == pytest.approx((0.0, 0.0), abs=1e-9)
        assert road.uv_to_z(umin, 0.0) == pytest.approx(0.0, abs=1e-6)
