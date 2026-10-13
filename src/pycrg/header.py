"""Reading the header of OpenCRG files.

The OpenCRG C library parses the header while loading, but keeps only what it
needs for evaluation. :func:`read_header` parses the text header of a file
(everything before the ``$$$$`` line that starts the data section) in Python,
following the rules of the C loader:

* a line starting with ``$`` starts or ends a section (names are matched
  case-insensitively by prefix);
* lines whose first non-blank character is ``*`` are comments, except inside
  ``$CT``, where every line is comment text;
* ``!`` starts an end-of-line comment;
* entries have the form ``key = value``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Union

__all__ = ["CrgChannel", "CrgHeader", "read_header"]

PathType = Union[str, bytes, "os.PathLike[str]", "os.PathLike[bytes]"]

# section keywords in the order the C loader matches them (by prefix)
_SECTIONS = (
    ("$ROAD_CRG_MODS", "mods"),
    ("$ROAD_CRG_OPTS", "opts"),
    ("$ROAD_CRG_FILE", "file"),
    ("$ROAD_CRG_MPRO", "mpro"),
    ("$ROAD_CRG", "road"),
    ("$CT", "comment"),
    ("$KD_DEFINITION", "definition"),
    ("$$$$", "data"),
)


@dataclass(frozen=True)
class CrgChannel:
    """One channel definition of the ``$KD_DEFINITION`` section.

    ``kind`` is ``"U"`` for the independent channel (the reference line u) and
    ``"D"`` for data channels, ``name`` is for example ``"reference line phi"``
    or ``"long section 3"``, and ``extra`` holds any further comma-separated
    fields (the u start and increment for the independent channel).
    """

    kind: str
    name: str
    unit: str
    extra: tuple[str, ...] = ()


@dataclass(frozen=True, eq=False)
class CrgHeader:
    """The parsed header of an OpenCRG file.

    The values describe the file as written, before any modifier is applied.
    Numbers are returned as ``float``; values that are not numbers (for example
    in ``$ROAD_CRG_MPRO``) are returned as the stripped text.

    Attributes:
        path: the file the header was read from.
        data_format: the data format of the ``#:`` line, for example ``"KRBI"``,
            or ``None`` for a file without data definition.
        comment: the text of the ``$CT`` sections, one line per line.
        road: the ``$ROAD_CRG`` entries with lower-case keys, for example
            ``road["reference_line_start_x"]``.
        options: the ``$ROAD_CRG_OPTS`` entries, or ``None`` without such a section.
        modifiers: the ``$ROAD_CRG_MODS`` entries, or ``None`` without such a
            section. An empty dict means an empty section, which tells readers
            to apply no modifiers at all (not even their defaults).
        file_reference: the file named in ``$ROAD_CRG_FILE``, or ``None``.
        map_projection: the ``$ROAD_CRG_MPRO`` entries, or ``None``.
        channels: the channel definitions of ``$KD_DEFINITION``.
        remarks: ``*`` comment lines outside ``$CT``, such as
            ``"* written by crg_write at ..."``.
    """

    path: str
    data_format: str | None
    comment: str
    road: dict[str, float | str] = field(default_factory=dict)
    options: dict[str, float | str] | None = None
    modifiers: dict[str, float | str] | None = None
    file_reference: str | None = None
    map_projection: dict[str, float | str] | None = None
    channels: tuple[CrgChannel, ...] = ()
    remarks: tuple[str, ...] = ()

    @property
    def long_section_count(self) -> int:
        """Number of long sections (z channels) defined in the file."""
        return sum(
            1 for channel in self.channels if channel.kind == "D" and channel.name.lower().startswith("long section")
        )


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _strip_comment(text: str) -> str:
    index = text.find("!")
    return text if index < 0 else text[:index]


# the numeric prefix that the C library's atof() reads
_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][+-]?\d+)?")


def _parse_value(text: str) -> float | str:
    value = _strip_comment(text).strip()
    match = _NUMBER.match(value)
    if match is None:
        return value.strip("'\"")
    return float(match.group(0).replace("d", "e").replace("D", "e"))


def _parse_entry(line: str) -> tuple[str, float | str] | None:
    content = _strip_comment(line)
    if "=" not in content:
        return None
    key, value = content.split("=", 1)
    key = key.strip().lower()
    if not key:
        return None
    return key, _parse_value(value)


def _section_of(line: str) -> str | None:
    """Section name for a line starting with ``$``; ``None`` ends a section."""
    upper = line.lstrip(" ").upper()
    for keyword, name in _SECTIONS:
        if upper.startswith(keyword):
            return name
    return None


def read_header(path: PathType) -> CrgHeader:
    """Parse the header of the OpenCRG file at ``path``.

    Only the text before the data section is read, so this is fast even for
    large files. Raises :class:`OSError` if the file cannot be read.
    """
    fspath = os.fspath(path)

    section: str | None = None
    data_format: str | None = None
    comment: list[str] = []
    road: dict[str, float | str] = {}
    options: dict[str, float | str] | None = None
    modifiers: dict[str, float | str] | None = None
    file_parts: list[str] = []
    has_file_section = False
    map_projection: dict[str, float | str] | None = None
    channels: list[CrgChannel] = []
    remarks: list[str] = []

    with open(fspath, "rb") as stream:
        for raw in stream:
            line = _decode(raw).rstrip("\r\n")

            if section is not None:
                # Any "$" line ends a section and is consumed. In $CT and
                # $ROAD_CRG_FILE the "$" must be the first character, since
                # file references may start with an environment variable.
                ends = line.startswith("$") if section in ("comment", "file") else line.lstrip(" ").startswith("$")
                if ends:
                    section = None
                    continue
                if section == "comment":
                    comment.append(line)
                    continue
            elif line.lstrip(" ").startswith("$"):
                section = _section_of(line)
                if section == "data":
                    break
                # like the C loader, an options or modifiers section replaces
                # everything defined before (including the defaults)
                if section == "opts":
                    options = {}
                elif section == "mods":
                    modifiers = {}
                elif section == "mpro" and map_projection is None:
                    map_projection = {}
                elif section == "file":
                    has_file_section = True
                continue

            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("*"):
                if section is None:
                    remarks.append(stripped)
                continue

            if section == "road":
                entry = _parse_entry(line)
                if entry is not None:
                    road[entry[0]] = entry[1]
            elif section == "opts":
                entry = _parse_entry(line)
                if entry is not None and options is not None:
                    options[entry[0]] = entry[1]
            elif section == "mods":
                entry = _parse_entry(line)
                if entry is not None and modifiers is not None:
                    modifiers[entry[0]] = entry[1]
            elif section == "mpro":
                entry = _parse_entry(line)
                if entry is not None and map_projection is not None:
                    map_projection[entry[0]] = entry[1]
            elif section == "file":
                # like the C loader: the name ends at a blank or "!"
                token = _strip_comment(stripped).split(" ", 1)[0]
                if token:
                    file_parts.append(token)
            elif section == "definition":
                if stripped.startswith("#:"):
                    data_format = stripped[2:6].strip().upper() or None
                elif stripped[:2].upper() in ("U:", "D:"):
                    fields = [part.strip() for part in _strip_comment(stripped[2:]).split(",")]
                    name = fields[0] if fields else ""
                    unit = fields[1] if len(fields) > 1 else ""
                    channels.append(CrgChannel(stripped[0].upper(), name, unit, tuple(fields[2:])))

    return CrgHeader(
        path=os.fsdecode(fspath),
        data_format=data_format,
        comment="\n".join(comment),
        road=road,
        options=options,
        modifiers=modifiers,
        file_reference="".join(file_parts) if has_file_section and file_parts else None,
        map_projection=map_projection,
        channels=tuple(channels),
        remarks=tuple(remarks),
    )
