from pathlib import Path

from pycrg import (
    BORDER_MODE_NONE,
    CP_OPTION_BORDER_MODE_U,
    CP_OPTION_BORDER_MODE_V,
    MOD_SCALE_Z,
    DataSet,
    RoadSurface,
    clear_message_callback,
    get_release_info,
    msg_print,
    set_message_callback,
)
from pycrg import experimental


def test_open_ranges_eval_and_close():
    sample = Path(__file__).parent / "data" / "sample.crg"

    road = RoadSurface.open(str(sample))

    umin, umax = road.u_range()
    vmin, vmax = road.v_range()
    assert umax >= umin
    assert vmax >= vmin

    u_mid = (umin + umax) / 2.0
    v_mid = (vmin + vmax) / 2.0

    z_uv = road.uv_to_z(u_mid, v_mid)
    x, y = road.uv_to_xy(u_mid, v_mid)
    z_xy = road.xy_to_z(x, y)
    u2, v2 = road.xy_to_uv(x, y)

    assert isinstance(z_uv, float)
    assert isinstance(z_xy, float)
    assert abs(u2 - u_mid) < 1.0
    assert abs(v2 - v_mid) < 1.0

    phi, curv = road.uv_to_pk(u_mid, v_mid)
    assert isinstance(phi, float)
    assert isinstance(curv, float)

    road.close()


def test_dataset_and_contact_point_full_surface():
    sample = Path(__file__).parent / "data" / "sample.crg"
    assert get_release_info()

    dataset = DataSet.open(str(sample))
    assert dataset.check() is True

    umin, umax = dataset.u_range()
    vmin, vmax = dataset.v_range()
    uinc, vinc = dataset.increments()
    assert umax >= umin
    assert vmax >= vmin
    assert uinc > 0.0
    assert vinc >= 0.0

    ok, is_closed, u_close_min, u_close_max = dataset.closed_track_data()
    assert isinstance(ok, bool)
    assert isinstance(is_closed, int)
    assert isinstance(u_close_min, float)
    assert isinstance(u_close_max, float)

    assert dataset.modifier_set_double(MOD_SCALE_Z, 1.0)
    value = dataset.modifier_get_double(MOD_SCALE_Z)
    assert value is not None
    assert abs(value - 1.0) < 1e-12
    assert dataset.modifier_remove(MOD_SCALE_Z)

    cp = dataset.create_contact_point()
    assert cp.option_set_int(CP_OPTION_BORDER_MODE_U, 2)
    cp_value = cp.option_get_int(CP_OPTION_BORDER_MODE_U)
    assert cp_value == 2

    u_mid = (umin + umax) / 2.0
    v_mid = (vmin + vmax) / 2.0
    x, y = cp.uv_to_xy(u_mid, v_mid)
    assert isinstance(cp.xy_to_z(x, y), float)
    phi, curv = cp.xy_to_pk(x, y)
    assert isinstance(phi, float)
    assert isinstance(curv, float)

    cp.close()
    dataset.close()


def test_try_eval_helpers_return_none_on_failure_and_values_on_success():
    sample = Path(__file__).parent / "data" / "sample.crg"

    dataset = DataSet.open(str(sample))
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

    far_u = umin - 100000.0
    far_v = vmax + 100000.0

    assert cp.try_uv_to_z(far_u, far_v) is None
    xy_far = cp.try_uv_to_xy(far_u, far_v)
    assert xy_far is None or (isinstance(xy_far[0], float) and isinstance(xy_far[1], float))

    pk_far = cp.try_uv_to_pk(far_u, far_v)
    assert pk_far is None or (isinstance(pk_far[0], float) and isinstance(pk_far[1], float))

    cp.close()
    dataset.close()


def test_advanced_callbacks_registration_and_message_callback():
    received = []

    def msg_cb(level: int, message: str) -> int:
        received.append((level, message))
        return 0

    set_message_callback(msg_cb)
    msg_print(3, "pycrg-callback-test")
    assert received
    assert received[-1][0] == 3
    assert "pycrg-callback-test" in received[-1][1]

    clear_message_callback()


def test_unsafe_allocator_callbacks_require_explicit_enable_flag():
    try:
        experimental.set_calloc_callback(None)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected RuntimeError when unsafe callbacks are not enabled")

    try:
        experimental.calloc(1, 8)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected RuntimeError when unsafe allocator API is not enabled")
