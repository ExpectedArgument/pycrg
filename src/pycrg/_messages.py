"""Routing of OpenCRG messages.

The C library reports everything (statistics, warnings, errors) through
``crgMsgPrint``, which writes to C ``stderr`` by default. pycrg installs a
message callback instead and routes each message:

1. to every active capture on the current thread, which collects the messages
   of one operation (to attach them to an exception, or to build a text);
2. unless an exclusive capture is active, and while the message limit set by
   ``set_max_warn_messages`` allows it, to the user callback set by
   ``set_message_callback``, or else to the ``pycrg`` logger.
"""

from __future__ import annotations

import atexit
import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from . import _native

logger = logging.getLogger("pycrg")

#: OpenCRG message level -> logging level
LOGGING_LEVELS = {
    1: logging.ERROR,  # FATAL: the operation failed
    2: logging.WARNING,  # WARN
    3: logging.INFO,  # NOTICE: data set statistics etc.
    4: logging.DEBUG,  # INFO
    5: logging.DEBUG,  # DEBUG
}

MessageList = list[tuple[int, str]]

_callback: Callable[[int, str], object] | None = None
_local = threading.local()


class _Capture:
    __slots__ = ("messages", "exclusive")

    def __init__(self, exclusive: bool) -> None:
        self.messages: MessageList = []
        self.exclusive = exclusive


def _dispatch(level: int, text: str) -> None:
    captures: list[_Capture] | None = getattr(_local, "captures", None)
    if captures:
        for capture in captures:
            capture.messages.append((level, text))
        if any(capture.exclusive for capture in captures):
            return
    _forward(level, text)


def _forward(level: int, text: str) -> None:
    if not _native.msg_consume_quota():
        return
    callback = _callback
    if callback is not None:
        # an exception is reported through sys.unraisablehook, so that the
        # OpenCRG operation emitting the message is not interrupted
        _native.invoke_callback(callback, level, text)
        return
    logging_level = LOGGING_LEVELS.get(level, logging.INFO)
    if logger.isEnabledFor(logging_level):
        logger.log(logging_level, "%s", text.rstrip("\r\n"))


def set_callback(callback: Callable[[int, str], object] | None) -> None:
    global _callback
    if callback is not None and not callable(callback):
        raise TypeError("callback must be callable or None")
    _callback = callback


@contextmanager
def capture(exclusive: bool = False) -> Iterator[MessageList]:
    """Collect the messages emitted on this thread inside the ``with`` block.

    With ``exclusive=True`` the messages are not passed on to the callback or
    the logger.
    """
    captures: list[_Capture] | None = getattr(_local, "captures", None)
    if captures is None:
        captures = _local.captures = []
    entry = _Capture(exclusive)
    captures.append(entry)
    try:
        yield entry.messages
    finally:
        captures.remove(entry)


def replay(messages: MessageList) -> None:
    """Pass messages collected by an exclusive capture on to the callback or logger.

    Operations that raise an exception on failure capture their messages
    exclusively: on failure they are attached to the exception, on success
    they are replayed here, so that warnings are not lost.
    """
    for level, text in messages:
        _forward(level, text)


@contextmanager
def collect_text(min_level: int = 3) -> Iterator[MessageList]:
    """Exclusively capture messages, raising the message level to ``min_level``."""
    old_level = _native.msg_get_level()
    with capture(exclusive=True) as messages:
        if old_level < min_level:
            _native.msg_set_level(min_level)
        try:
            yield messages
        finally:
            if old_level < min_level:
                _native.msg_set_level(old_level)


def join_text(messages: MessageList) -> str:
    """Join captured messages to a text with one message per line."""
    return "".join(text if text.endswith("\n") else text + "\n" for _, text in messages)


def summarize(messages: MessageList, limit: int = 3, max_length: int = 200) -> str:
    """Describe a failure by the captured messages, in one line.

    Uses the FATAL messages if there are any, otherwise the last messages up to
    NOTICE level, since OpenCRG reports some failures only as notices.
    """
    # the loader releases the data set of a failed load, which it reports, too
    texts = [
        (level, text.strip()) for level, text in messages if text.strip() and not text.startswith("crgDataSetRelease:")
    ]
    chosen = [text for level, text in texts if level <= 1][-limit:]
    if not chosen:
        chosen = [text for level, text in texts if level <= 3][-2:]
    return "; ".join(text if len(text) <= max_length else text[: max_length - 3] + "..." for text in chosen)


_native.msg_set_handler(_dispatch)
# Drop messages emitted during interpreter shutdown, when logging may be gone.
atexit.register(_native.msg_set_handler, None)
