"""Header metadata (finding 10)."""

import pytest

import pycrg
from pycrg import read_header


def test_header_of_sample(crg_txt):
    header = read_header(crg_txt / "handmade_straight.crg")
    assert header.data_format == "LRFI"
    assert header.road["reference_line_start_u"] == 0.0
    assert header.road["reference_line_end_u"] == 22.0
    assert header.road["reference_line_increment"] == 1.0
    assert header.road["long_section_v_right"] == -1.5
    assert header.modifiers is None
    assert header.file_reference is None
    assert header.long_section_count == 7
    assert header.channels[0].kind == "U"
    assert header.channels[0].name == "reference line u"
    assert "Licensed under the Apache License" in header.comment


def test_header_sections(crg_txt):
    header = read_header(crg_txt / "fileref.crg")
    assert header.file_reference == "../crg-txt/handmade_curved_banked_sloped.crg"
    assert header.modifiers == {}  # an empty section: no modifiers at all
    assert header.options == {}
    assert header.data_format is None
    assert header.channels == ()


def test_header_numbers_like_the_c_loader(crg_txt):
    # the file writes "2.000000000+e00", which OpenCRG reads as 2
    assert read_header(crg_txt / "handmade_platform.crg").modifiers == {"grid_nan_mode": 2.0}


def test_header_options(crg_txt):
    options = read_header(crg_txt / "handmade_sloped_opts.crg").options
    assert options is not None
    assert options["border_mode_u"] == 2.0


def test_header_of_written_file(write_road):
    path = write_road(
        x0=10.0,
        y0=20.0,
        comment="first line\nsecond line",
        mods={"refline_offset_z": 1.5},
        road={"reference_line_start_lat": 48.1, "reference_line_start_lon": 11.5},
    )
    header = read_header(path)
    assert header.comment == "first line\nsecond line"
    assert header.data_format == "KRBI"
    assert header.modifiers == {"refline_offset_z": 1.5}
    assert header.options is None
    assert header.road["reference_line_start_x"] == 10.0
    assert header.road["reference_line_start_lat"] == 48.1
    assert header.remarks == (f"* written by pycrg {pycrg.__version__}",)
    with pycrg.DataSet.open(path) as dataset:
        assert dataset.header.road == header.road


def test_header_of_binary_file_stops_at_data(write_road):
    header = read_header(write_road(nu=2000))
    assert header.long_section_count == 7


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_header(tmp_path / "missing.crg")
