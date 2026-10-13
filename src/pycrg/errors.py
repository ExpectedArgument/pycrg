"""Exceptions raised by pycrg."""

from __future__ import annotations

from collections.abc import Iterable

__all__ = [
    "OpenCRGError",
    "OpenCRGClosedError",
    "OpenCRGLoadError",
    "OpenCRGCheckError",
    "OpenCRGEvaluationError",
]


class OpenCRGError(RuntimeError):
    """Base class of all errors raised by pycrg.

    ``messages`` holds the OpenCRG messages ``(level, text)`` emitted while the
    failing operation ran, for example the reason why a file could not be
    loaded. It is empty when there were none.
    """

    def __init__(self, *args: object, messages: Iterable[tuple[int, str]] = ()) -> None:
        super().__init__(*args)
        self.messages: tuple[tuple[int, str], ...] = tuple(messages)


class OpenCRGClosedError(OpenCRGError):
    """A closed (or released) data set, contact point or road surface was used."""


class OpenCRGLoadError(OpenCRGError):
    """A CRG file could not be loaded."""


class OpenCRGCheckError(OpenCRGError):
    """A data set failed the OpenCRG consistency check, or its modifiers are invalid."""


class OpenCRGEvaluationError(OpenCRGError):
    """A position could not be evaluated or transformed, for example outside the
    data with ``BORDER_MODE_NONE`` or for a non-finite coordinate."""
