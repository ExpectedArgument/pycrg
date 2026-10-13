"""OpenCRG messages: logging, callbacks, text output (findings 7 and 8)."""

import io
import logging
import sys

import pytest

import pycrg
from pycrg import (
    MSG_LEVEL_DEBUG,
    MSG_LEVEL_FATAL,
    MSG_LEVEL_NOTICE,
    MSG_LEVEL_WARN,
    DataSet,
    RoadSurface,
)


def test_loading_is_quiet_by_default(straight, capfd):
    with DataSet.open(straight) as dataset:
        dataset.check()
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_messages_go_to_logging(straight, caplog):
    with caplog.at_level(logging.DEBUG, logger="pycrg"), DataSet.open(straight):
        pass
    records = [record for record in caplog.records if record.name == "pycrg"]
    assert records
    assert all(record.levelno == logging.INFO for record in records)  # NOTICE
    assert any("finished reading file" in record.getMessage() for record in records)
    assert not any(record.getMessage().endswith("\n") for record in records)


def test_logging_levels(caplog):
    with caplog.at_level(logging.DEBUG, logger="pycrg"):
        pycrg.msg_print(MSG_LEVEL_FATAL, "fatal")
        pycrg.msg_print(MSG_LEVEL_WARN, "warn")
        pycrg.msg_print(MSG_LEVEL_NOTICE, "notice")
        pycrg.msg_print(MSG_LEVEL_DEBUG, "debug")  # not generated at the default level
    levels = {record.getMessage(): record.levelno for record in caplog.records if record.name == "pycrg"}
    assert levels == {"fatal": logging.ERROR, "warn": logging.WARNING, "notice": logging.INFO}


def test_message_level():
    assert pycrg.get_message_level() == MSG_LEVEL_NOTICE
    assert pycrg.is_message_printable(MSG_LEVEL_FATAL)
    assert pycrg.is_message_printable(MSG_LEVEL_NOTICE)
    assert not pycrg.is_message_printable(MSG_LEVEL_DEBUG)
    pycrg.set_message_level(MSG_LEVEL_DEBUG)
    assert pycrg.get_message_level() == MSG_LEVEL_DEBUG
    assert pycrg.is_message_printable(MSG_LEVEL_DEBUG)


def test_message_callback_replaces_logging(caplog):
    received = []
    pycrg.set_message_callback(lambda level, text: received.append((level, text)))
    with caplog.at_level(logging.DEBUG, logger="pycrg"):
        pycrg.msg_print(MSG_LEVEL_WARN, "to the callback\n")
    assert received == [(MSG_LEVEL_WARN, "to the callback\n")]
    assert not [record for record in caplog.records if record.name == "pycrg"]
    pycrg.clear_message_callback()
    with caplog.at_level(logging.DEBUG, logger="pycrg"):
        pycrg.msg_print(MSG_LEVEL_WARN, "to logging")
    assert received == [(MSG_LEVEL_WARN, "to the callback\n")]
    assert [record.getMessage() for record in caplog.records if record.name == "pycrg"] == ["to logging"]


def test_message_callback_must_be_callable():
    with pytest.raises(TypeError):
        pycrg.set_message_callback(42)  # type: ignore[arg-type]


def test_exception_in_callback_is_reported(straight, monkeypatch):
    reported = []
    monkeypatch.setattr(sys, "unraisablehook", lambda unraisable: reported.append(unraisable.exc_value))

    def callback(level: int, text: str) -> None:
        raise ValueError("callback failed")

    pycrg.set_message_callback(callback)
    with DataSet.open(straight) as dataset:  # loading continues
        assert dataset.u_range() == (0.0, 22.0)
    assert reported
    assert all(isinstance(error, ValueError) for error in reported)


def test_message_limit(caplog):
    pycrg.set_max_warn_messages(2)
    with caplog.at_level(logging.DEBUG, logger="pycrg"):
        for index in range(5):
            pycrg.msg_print(MSG_LEVEL_WARN, f"message {index}")
    messages = [record.getMessage() for record in caplog.records if record.name == "pycrg"]
    assert messages == ["message 0", "message 1"]
    assert not pycrg.is_message_printable(MSG_LEVEL_WARN)


def test_message_limit_does_not_hide_failure_reasons(tmp_path):
    pycrg.set_max_warn_messages(0)
    garbage = tmp_path / "garbage.crg"
    garbage.write_text("nothing\n")
    with pytest.raises(pycrg.OpenCRGLoadError) as info:
        DataSet.open(garbage)
    assert "no data section" in str(info.value)


def test_format_and_print_functions(straight, capsys):
    with RoadSurface.open(straight) as road:
        header = road.format_header()
        assert "crgDataPrintHeader: uMax     =    22.0000" in header
        assert "number of v channels" in road.format_road_info()
        assert "overview of channel information" in road.format_channel_info()
        assert "modifier" in road.format_modifiers()
        assert "border mode u" in road.format_options()

        road.print_header()
        assert capsys.readouterr().out == header
        buffer = io.StringIO()
        road.dataset.print_road_info(file=buffer)
        assert buffer.getvalue() == road.format_road_info()
        road.contact_point.options_print()
        assert "border mode u" in capsys.readouterr().out


def test_format_functions_work_at_any_message_level(straight, capfd):
    pycrg.set_message_level(MSG_LEVEL_FATAL)
    with DataSet.open(straight) as dataset:
        assert "uMax" in dataset.format_header()
    assert pycrg.get_message_level() == MSG_LEVEL_FATAL
    assert capfd.readouterr().err == ""


def test_check_failure_reasons(write_road, caplog):
    path = write_road(opts={"check_eps": 1.0})
    with DataSet.open(path) as dataset:
        with caplog.at_level(logging.WARNING, logger="pycrg"):
            assert dataset.check() is False
        assert any("check_eps" in record.getMessage() for record in caplog.records)
        caplog.clear()
        with pytest.raises(pycrg.OpenCRGCheckError, match="check_eps") as info:
            dataset.check(raise_on_error=True)
        assert info.value.messages
        assert not caplog.records
