"""Opening files: paths, errors and modifiers (findings 1, 2, 5, 14 and A, B)."""

import os
import shutil
import sys

import pytest

from pycrg import (
    MOD_REF_LINE_OFFSET_Z,
    MOD_SCALE_LENGTH,
    MOD_SCALE_Z,
    DataSet,
    OpenCRGCheckError,
    OpenCRGError,
    OpenCRGLoadError,
    RoadSurface,
)

# --- paths -------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["str", "path", "bytes"])
def test_path_types(straight, kind):
    path = {"str": str(straight), "path": straight, "bytes": os.fsencode(straight)}[kind]
    with DataSet.open(path) as dataset:
        assert dataset.u_range() == (0.0, 22.0)
        assert dataset.path == str(straight)


@pytest.mark.parametrize("directory", ["with space", "yol ölçümü şğı", "日本語"])
def test_non_ascii_paths(tmp_path, straight, directory):
    target = tmp_path / directory / "straight ölçüm.crg"
    target.parent.mkdir()
    shutil.copy(straight, target)
    with DataSet.open(target) as dataset:
        assert dataset.u_range() == (0.0, 22.0)
        assert dataset.header.data_format == "LRFI"


@pytest.mark.skipif(sys.platform != "linux", reason="needs a file system accepting any bytes")
def test_undecodable_path(tmp_path, straight):
    target = os.path.join(os.fsencode(tmp_path), b"road-\xff.crg")
    shutil.copy(straight, target)
    for path in (target, os.fsdecode(target)):
        with DataSet.open(path) as dataset:
            assert dataset.u_range() == (0.0, 22.0)


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError) as info:
        DataSet.open(tmp_path / "missing.crg")
    assert info.value.filename.endswith("missing.crg")


def test_directory(tmp_path):
    with pytest.raises(IsADirectoryError):
        DataSet.open(tmp_path)


def test_wrong_type():
    with pytest.raises(TypeError):
        DataSet.open(1)  # type: ignore[arg-type]


def test_load_error_tells_why(tmp_path):
    garbage = tmp_path / "garbage.crg"
    garbage.write_text("this is not a CRG file\n")
    with pytest.raises(OpenCRGLoadError) as info:
        DataSet.open(garbage)
    error = info.value
    assert isinstance(error, OpenCRGError) and isinstance(error, RuntimeError)
    assert "garbage.crg" in str(error)
    assert "no data section" in str(error)
    assert any("no data section" in text for _, text in error.messages)


def test_truncated_binary_file(tmp_path, write_road):
    path = write_road("full.crg", fmt="KRBI")
    data = path.read_bytes()
    truncated = tmp_path / "truncated.crg"
    truncated.write_bytes(data[: data.index(b"$$$$") + 200])
    with pytest.raises(OpenCRGLoadError, match="does not contain enough records"):
        DataSet.open(truncated)


def test_failed_load_is_not_logged_but_attached(tmp_path, caplog):
    garbage = tmp_path / "garbage.crg"
    garbage.write_text("$ROAD_CRG\n$\n")
    with pytest.raises(OpenCRGLoadError) as info:
        DataSet.open(garbage)
    assert info.value.messages
    assert not [record for record in caplog.records if record.name == "pycrg"]


# --- file references ($ROAD_CRG_FILE) -----------------------------------------


def test_file_reference_from_any_working_directory(crg_txt, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with DataSet.open(crg_txt / "fileref.crg") as reference:
        cp = reference.create_contact_point()
        z_reference = cp.uv_to_z(10.0, 0.5)
    # fileref.crg defines empty modifiers and options: the data is used as is
    with DataSet.open(crg_txt / "handmade_curved_banked_sloped.crg", apply_modifiers=False) as target:
        z_target = target.create_contact_point().uv_to_z(10.0, 0.5)
    assert z_reference == pytest.approx(z_target, abs=1e-12)


def test_file_reference_relative_to_working_directory(crg_txt, monkeypatch):
    # the documented OpenCRG behaviour keeps working
    monkeypatch.chdir(crg_txt)
    with DataSet.open("fileref.crg") as dataset:
        assert dataset.u_range()[1] > 0


def test_failed_file_reference_is_not_sticky(crg_txt, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(OpenCRGLoadError, match=r"handmade_sloped_opt\.crg"):
        DataSet.open(crg_txt / "testOptionBorderMode.crg")
    with DataSet.open(crg_txt / "fileref.crg") as dataset:
        assert dataset.u_range()[1] > 0


def test_nested_file_references(crg_txt, tmp_path):
    shutil.copy(crg_txt / "handmade_straight.crg", tmp_path / "data.crg")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "middle.crg").write_text("$ROAD_CRG_FILE\n../data.crg\n$\n")
    (tmp_path / "top.crg").write_text("$ROAD_CRG_FILE\nsub/middle.crg\n$\n$ROAD_CRG_MODS\n$\n")
    with DataSet.open(tmp_path / "top.crg") as dataset:
        assert dataset.u_range() == (0.0, 22.0)
        assert dataset.header.file_reference == "sub/middle.crg"


def test_modifiers_of_referenced_file_apply_after_other_loads(crg_txt, tmp_path, write_road):
    # the modifier level of the C loader used to survive between loads
    data = write_road("data.crg", x0=100.0, mods={"refline_offset_z": 10.0})
    (tmp_path / "ref.crg").write_text(f"$ROAD_CRG_FILE\n{data.name}\n$\n")
    with DataSet.open(crg_txt / "handmade_platform.crg"):
        pass
    with DataSet.open(tmp_path / "ref.crg") as via_reference, DataSet.open(data) as direct:
        a = via_reference.create_contact_point().uv_to_z(5.0, 0.0)
        b = direct.create_contact_point().uv_to_z(5.0, 0.0)
    assert a == pytest.approx(b, abs=1e-12)
    assert a > 9.0


# --- modifiers -------------------------------------------------------------------


def test_open_applies_modifiers_of_the_file(write_road):
    path = write_road(mods={"refline_offset_z": 10.0})
    with DataSet.open(path, apply_modifiers=False) as raw:
        z_raw = raw.create_contact_point().uv_to_z(1.0, 0.0)
    with DataSet.open(path) as applied:
        z_applied = applied.create_contact_point().uv_to_z(1.0, 0.0)
    assert z_applied == pytest.approx(z_raw + 10.0, abs=1e-6)


def test_open_applies_default_modifiers_without_modifier_section(write_road):
    path = write_road(x0=1000.0, y0=2000.0, phi=0.5)
    with DataSet.open(path) as dataset:
        cp = dataset.create_contact_point()
        assert cp.uv_to_xy(0.0, 0.0) == pytest.approx((0.0, 0.0), abs=1e-9)
        assert cp.uv_to_pk(1.0, 0.0)[0] == pytest.approx(0.0, abs=1e-6)
    with DataSet.open(path, apply_modifiers=False) as dataset:
        assert dataset.create_contact_point().uv_to_xy(0.0, 0.0) == pytest.approx((1000.0, 2000.0))


def test_empty_modifier_section_keeps_position(write_road):
    path = write_road(x0=1000.0, y0=2000.0, mods={})
    with RoadSurface.open(path) as road:
        assert road.uv_to_xy(0.0, 0.0) == pytest.approx((1000.0, 2000.0))


def test_grid_nan_mode_modifier_is_applied(write_road, numpy):
    z = numpy.zeros((41, 7))
    z[:, 0] = numpy.nan
    z[10:20, -2:] = numpy.nan
    z[:, 1] = 0.5
    with DataSet.open(write_road(z=z, mods={"grid_nan_mode": 2})) as dataset:
        grid = dataset.grid()
    assert not numpy.isnan(grid.z).any()
    assert grid.z[:, 0] == pytest.approx(0.5)  # the last valid value
    with DataSet.open(write_road("zero.crg", z=z, mods={"grid_nan_mode": 1, "grid_nan_offset": 0.25})) as dataset:
        grid = dataset.grid()
    assert grid.z[:, 0] == pytest.approx(0.25)
    assert grid.z[10:20, -2:] == pytest.approx(0.25)
    with DataSet.open(write_road("keep.crg", z=z, mods={})) as dataset:
        assert numpy.isnan(dataset.grid().z).sum() == 41 + 20


def test_modifiers_are_applied_once(write_road):
    path = write_road(mods={"refline_offset_z": 10.0})
    with DataSet.open(path) as dataset:
        cp = dataset.create_contact_point()
        z = cp.uv_to_z(1.0, 0.0)
        assert dataset.modifier_get_double(MOD_REF_LINE_OFFSET_Z) is None
        dataset.modifiers_apply()
        assert cp.uv_to_z(1.0, 0.0) == z
        dataset.modifier_set_double(MOD_SCALE_Z, 2.0)
        dataset.modifiers_apply()
        assert cp.uv_to_z(1.0, 0.0) != z


def test_road_surface_modifiers(write_road):
    path = write_road(mods={})
    with RoadSurface.open(path) as road:
        z = road.uv_to_z(1.0, 0.0)
        road.modifier_set_double(MOD_REF_LINE_OFFSET_Z, 2.5)
        road.modifiers_apply()
        assert road.uv_to_z(1.0, 0.0) == pytest.approx(z + 2.5, abs=1e-6)


def test_invalid_modifiers_raise(write_road):
    path = write_road(mods={"scale_length": -1.0})
    with pytest.raises(OpenCRGCheckError, match="scale_length") as info:
        DataSet.open(path)
    assert info.value.messages
    with DataSet.open(path, apply_modifiers=False) as dataset:
        assert dataset.modifier_get_double(MOD_SCALE_LENGTH) == -1.0
        with pytest.raises(OpenCRGCheckError):
            dataset.modifiers_apply()


def test_check_on_open(write_road):
    path = write_road(opts={"check_eps": 1.0})  # outside the valid range
    with pytest.raises(OpenCRGCheckError, match="check_eps"):
        DataSet.open(path, check=True)
    with DataSet.open(path) as dataset:
        assert dataset.check() is False
        with pytest.raises(OpenCRGCheckError) as info:
            dataset.check(raise_on_error=True)
        assert any("check_eps" in text for _, text in info.value.messages)


# --- malformed files ---------------------------------------------------------------


def test_header_without_data_section(tmp_path, write_road):
    # used to crash the C loader: channels are defined, but there is no data
    text = write_road("text.crg", fmt="LRFI").read_text()
    truncated = tmp_path / "no_data.crg"
    truncated.write_text(text[: text.index("$$$$")])
    with pytest.raises(OpenCRGLoadError, match="no data section"):
        DataSet.open(truncated)


def test_single_cross_section(tmp_path, write_road):
    text = write_road("text.crg", fmt="LRFI", nv=5).read_text()
    header, data = text.split("$" * 72 + "\n")
    single = tmp_path / "single.crg"
    single.write_text(header + "$" * 72 + "\n" + data.splitlines()[0] + "\n")
    with pytest.raises(OpenCRGLoadError, match="less than two cross sections"):
        DataSet.open(single)


# --- curvature check ---------------------------------------------------------------


@pytest.mark.parametrize("nan_at_center", [True, False])
def test_local_curvature_check(write_road, numpy, nan_at_center):
    # a reference line with a radius of 2 m on a road reaching 3 m to the
    # left: the global check fails; the local check passes if the grid has
    # no data at the center of the curvature
    np = numpy
    z = np.zeros((41, 7))
    if nan_at_center:
        z[:, 5:] = np.nan
    path = write_road(
        z=z,
        du=0.1,
        v=np.linspace(-3.0, 3.0, 7),
        phi=0.05 * np.arange(40),
        opts={"warn_curv_global": 1, "warn_curv_local": 1},
        mods={},
        check=nan_at_center,  # pycrg.write refuses the reference line otherwise
    )
    with DataSet.open(path) as dataset:
        assert dataset.check() is nan_at_center
        if not nan_at_center:
            with pytest.raises(OpenCRGCheckError, match="Local curvature test failed"):
                dataset.check(raise_on_error=True)


def test_global_curvature_check_by_default(write_road, numpy):
    # the global test runs unless the file sets warn_curv_global to 0, as
    # specified and as in the OpenCRG MATLAB tools; the local test only when
    # warn_curv_local is positive
    np = numpy
    sharp = {"du": 0.1, "v": np.linspace(-3.0, 3.0, 7), "phi": 0.05 * np.arange(40), "mods": {}, "check": False}
    path = write_road("default.crg", **sharp)
    with pytest.raises(OpenCRGCheckError, match=r"Global curvature test failed.*curvature from 0 to 0\.4997"):
        DataSet.open(path, check=True)
    for name, opts, valid in [
        ("on.crg", {"warn_curv_global": 1}, False),
        ("off.crg", {"warn_curv_global": 0}, True),
        ("default_value.crg", {"warn_curv_global": -1}, False),
        ("no_local.crg", {"warn_curv_global": 1, "warn_curv_local": 0}, False),
        ("local_only.crg", {"warn_curv_global": 0, "warn_curv_local": 1}, True),
    ]:
        with DataSet.open(write_road(name, opts=opts, **sharp)) as dataset:
            assert dataset.check() is valid, name


def test_curvature_options_are_checked(write_road):
    path = write_road(opts={"warn_curv_local": -2})
    with DataSet.open(path) as dataset, pytest.raises(OpenCRGCheckError, match="warn_curv_local"):
        dataset.check(raise_on_error=True)


def test_increments(crg_txt, write_road, numpy):
    np = numpy
    # long sections by index (constant spacing)
    with DataSet.open(crg_txt / "handmade_straight.crg") as dataset:
        assert dataset.increments() == pytest.approx((1.0, 0.5))
    # long sections at variable positions: the v increment is 0 (OpenCRG keeps 0.01)
    with DataSet.open(crg_txt / "handmade_curved_banked_sloped.crg") as dataset:
        assert dataset.increments() == (1.0, 0.0)
    variable = write_road("variable.crg", v=np.array([-1.5, -1.0, -0.2, 0.0, 0.2, 1.0, 1.5]))
    with DataSet.open(variable) as dataset:
        assert dataset.increments() == (0.5, 0.0)
    # constant spacing (written as long sections by index)
    constant = write_road("constant.crg", v=np.linspace(-0.9, 0.9, 7))
    with DataSet.open(constant) as dataset:
        assert dataset.increments() == pytest.approx((0.5, 0.3))
