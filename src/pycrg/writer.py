"""Writing OpenCRG files.

:func:`write` creates CRG files in the four OpenCRG data formats. It follows
the conventions of the reference writer of the OpenCRG MATLAB tools
(``crg_write`` / ``ipl_write``) and checks the rules the C loader relies on, so
that the files load with OpenCRG (and therefore with :class:`pycrg.DataSet`).

Data formats (the ``#:`` line of ``$KD_DEFINITION``):

========  ==============================================================
``KRBI``  binary, single precision (big-endian float32), the default
``KDBI``  binary, double precision (big-endian float64)
``LRFI``  text, 10 characters per value, 8 values per line
``LDFI``  text, 20 characters per value, 4 values per line
========  ==============================================================

Note that OpenCRG keeps the elevation grid in single precision when loading,
whatever the format; the double precision formats only matter for the
reference line channels and for other readers.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, Union

from . import constants as c
from ._version import __version__

if TYPE_CHECKING:
    import numpy.typing as npt

__all__ = ["write", "FORMATS", "OPTION_KEYWORDS", "MODIFIER_KEYWORDS", "ROAD_KEYWORDS"]

PathType = Union[str, bytes, "os.PathLike[str]", "os.PathLike[bytes]"]

FORMATS = ("KRBI", "KDBI", "LRFI", "LDFI")

#: option keywords of ``$ROAD_CRG_OPTS``; values are the ``CP_OPTION_*`` ids
#: (``None`` for keywords the C library ignores)
OPTION_KEYWORDS: dict[str, int | None] = {
    "border_mode_u": c.CP_OPTION_BORDER_MODE_U,
    "border_mode_v": c.CP_OPTION_BORDER_MODE_V,
    "border_offset_u": c.CP_OPTION_BORDER_OFFSET_U,
    "border_offset_v": c.CP_OPTION_BORDER_OFFSET_V,
    "border_smooth_ubeg": c.CP_OPTION_SMOOTH_U_BEGIN,
    "border_smooth_uend": c.CP_OPTION_SMOOTH_U_END,
    "refline_continuation": c.CP_OPTION_REF_LINE_CONTINUE,
    "refline_search_far": c.CP_OPTION_REF_LINE_FAR,
    "refline_search_close": c.CP_OPTION_REF_LINE_CLOSE,
    "refline_search_u": c.CP_OPTION_REF_LINE_SEARCH_U,
    "refline_search_ufrac": c.CP_OPTION_REF_LINE_SEARCH_U_FRAC,
    "warn_msgs": c.CP_OPTION_WARN_MSGS,
    "warn_curv_local": c.CP_OPTION_WARN_CURV_LOCAL,
    "warn_curv_global": c.CP_OPTION_WARN_CURV_GLOBAL,
    "log_msgs": None,
    "log_eval": None,
    "log_eval_freq": None,
    "log_hist": None,
    "log_hist_freq": None,
    "log_stat": None,
    "log_stat_freq": None,
    "check_eps": c.CP_OPTION_CHECK_EPS,
    "check_inc": c.CP_OPTION_CHECK_INC,
    "check_tol": c.CP_OPTION_CHECK_TOL,
}

#: modifier keywords of ``$ROAD_CRG_MODS``; values are the ``MOD_*`` ids
MODIFIER_KEYWORDS: dict[str, int] = {
    "scale_z_grid": c.MOD_SCALE_Z,
    "scale_slope": c.MOD_SCALE_SLOPE,
    "scale_banking": c.MOD_SCALE_BANK,
    "scale_length": c.MOD_SCALE_LENGTH,
    "scale_width": c.MOD_SCALE_WIDTH,
    "scale_curvature": c.MOD_SCALE_CURVATURE,
    "grid_nan_mode": c.MOD_GRID_NAN_MODE,
    "grid_nan_offset": c.MOD_GRID_NAN_OFFSET,
    "refline_rotcenter_x": c.MOD_REF_LINE_ROT_CENTER_X,
    "refline_rotcenter_y": c.MOD_REF_LINE_ROT_CENTER_Y,
    "refline_offset_phi": c.MOD_REF_LINE_OFFSET_PHI,
    "refline_offset_x": c.MOD_REF_LINE_OFFSET_X,
    "refline_offset_y": c.MOD_REF_LINE_OFFSET_Y,
    "refline_offset_z": c.MOD_REF_LINE_OFFSET_Z,
    "refpoint_u_fraction": c.MOD_REF_POINT_U_FRAC,
    "refpoint_u_offset": c.MOD_REF_POINT_U_OFFSET,
    "refpoint_u": c.MOD_REF_POINT_U,
    "refpoint_v_fraction": c.MOD_REF_POINT_V_FRAC,
    "refpoint_v_offset": c.MOD_REF_POINT_V_OFFSET,
    "refpoint_v": c.MOD_REF_POINT_V,
    "refpoint_x": c.MOD_REF_POINT_X,
    "refpoint_y": c.MOD_REF_POINT_Y,
    "refpoint_z": c.MOD_REF_POINT_Z,
    "refpoint_phi": c.MOD_REF_POINT_PHI,
}

#: ``$ROAD_CRG`` keywords that can be given with ``road=``; the others are
#: computed from the data
ROAD_KEYWORDS = (
    "reference_line_offset_x",
    "reference_line_offset_y",
    "reference_line_offset_z",
    "reference_line_offset_phi",
    "reference_line_start_lon",
    "reference_line_start_lat",
    "reference_line_start_alt",
    "reference_line_end_lon",
    "reference_line_end_lat",
    "reference_line_end_alt",
)

# integer valued options and modifiers, written without decimals
_INTEGER_OPTIONS = {
    "border_mode_u",
    "border_mode_v",
    "refline_continuation",
    "warn_msgs",
    "warn_curv_local",
    "warn_curv_global",
    "grid_nan_mode",
}

_MAX_LINE = 72  # header record length of the IPL format


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError("pycrg.write requires numpy (pip install pycrg[numpy])") from exc
    return numpy


def _round_half_away(value: float) -> int:
    return math.floor(abs(value) + 0.5) * (1 if value >= 0 else -1)


def _exponent_text(exponent: int, digits: int) -> str:
    return ("-" if exponent < 0 else "") + f"{abs(exponent):0{digits}d}"


def format_number(value: float, width: int) -> str:
    """Format ``value`` in exactly ``width`` characters with maximal accuracy.

    A port of ``str_num2strn`` of the OpenCRG MATLAB tools, which uses fixed
    point or scientific notation, whichever keeps more digits. NaN gives
    ``width`` asterisks, which OpenCRG reads as NaN.
    """
    if math.isnan(value):
        return "*" * width
    if math.isinf(value):
        raise ValueError(f"cannot write {value!r}")
    if value == 0:
        return "0" * width

    current = value
    while True:
        exponent = math.floor(math.log10(abs(current))) + 1
        minus = current < 0
        mantissa_digits = width - minus

        if exponent < -2:  # scientific notation with negative exponent
            mantissa_digits -= 3
            exponent -= mantissa_digits
            exponent_digits = 1
            if exponent <= -10:
                mantissa_digits -= 1
                exponent += 1
                exponent_digits = 2
            if exponent <= -100:
                mantissa_digits -= 1
                exponent += 1
                exponent_digits = 3
            mantissa = _round_half_away(current / 10.0**exponent)
            text = f"{mantissa:>{mantissa_digits + minus}d}e{_exponent_text(exponent, exponent_digits)}"
        elif exponent < 1:  # fixed point with leading "."
            mantissa_digits -= 1
            text = f"{current:{width}.{mantissa_digits}f}".replace("0.", ".", 1)
        elif exponent < mantissa_digits + 1:  # fixed point with leading digits
            mantissa_digits -= 1
            text = f"{current:{width}.{max(0, mantissa_digits - exponent)}f}"
        else:  # scientific notation with positive exponent
            mantissa_digits -= 2
            exponent -= mantissa_digits
            exponent_digits = 1
            if exponent >= 10:
                mantissa_digits -= 1
                exponent += 1
                exponent_digits = 2
            if exponent >= 100:
                mantissa_digits -= 1
                exponent += 1
                exponent_digits = 3
            mantissa = _round_half_away(current / 10.0**exponent)
            text = f"{mantissa:>{mantissa_digits + minus}d}e{_exponent_text(exponent, exponent_digits)}"

        if mantissa_digits < 1:
            raise ValueError(f"cannot write {value!r} in {width} characters")
        if len(text) == width:
            return text
        if len(text) < width:  # pragma: no cover - cannot happen
            raise AssertionError(f"internal error formatting {value!r}")
        # rounding produced an extra digit: repeat with the rounded value
        current = float(text)


def _header_line(key: str, value: float, integer: bool = False) -> str:
    if integer:
        return f"{key:<25} = {int(value)}"
    return f"{key:<25} = {float(value):24.16e}"


def _finite_float(name: str, value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise TypeError(f"{name} must be a number, not {type(value).__name__}") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite, not {result!r}")
    return result


def _keyword_entries(name: str, entries: Mapping[str | int, float], keywords: Mapping[str, int | None]) -> list[str]:
    by_id = {value: key for key, value in keywords.items() if value is not None}
    lines = []
    seen = set()
    for key, value in entries.items():
        if isinstance(key, int) and not isinstance(key, bool):
            if key not in by_id:
                raise ValueError(f"unknown {name} id {key}")
            keyword = by_id[key]
        elif isinstance(key, str) and key.lower() in keywords:
            keyword = key.lower()
        else:
            raise ValueError(f"unknown {name} {key!r}; expected one of {sorted(keywords)}")
        if keyword in seen:
            raise ValueError(f"{name} {keyword!r} given twice")
        seen.add(keyword)
        number = _finite_float(f"{name} {keyword!r}", value)
        integer = keyword in _INTEGER_OPTIONS
        if integer and number != int(number):
            raise ValueError(f"{name} {keyword!r} must be an integer, not {number!r}")
        lines.append(_header_line(keyword, number, integer))
    return lines


def _segment_values(np: Any, name: str, values: Any, nu: int) -> Any:
    """Per-segment values (``nu - 1``), given with ``nu - 1`` or ``nu`` entries."""
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.shape[0] not in (nu - 1, nu):
        raise ValueError(f"{name} must be a number or have {nu - 1} (one per segment) or {nu} entries")
    if array.shape[0] == nu:
        array = array[1:]
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite")
    return array


def write(
    path: PathType,
    z: npt.ArrayLike,
    du: float,
    v: npt.ArrayLike,
    phi: npt.ArrayLike | float | None = None,
    *,
    u0: float = 0.0,
    x0: float = 0.0,
    y0: float = 0.0,
    z0: float = 0.0,
    end_xy: tuple[float, float] | None = None,
    slope: npt.ArrayLike | float | None = None,
    banking: npt.ArrayLike | float | None = None,
    fmt: str = "KRBI",
    comment: str | Iterable[str] = (),
    opts: Mapping[str | int, float] | None = None,
    mods: Mapping[str | int, float] | None = None,
    road: Mapping[str, float] | None = None,
) -> None:
    """Write an OpenCRG file (requires numpy).

    The road surface is a grid of ``nu`` cross sections (along the reference
    line, ``du`` apart, starting at ``u0``) by ``nv`` long sections (across the
    road, at the lateral positions ``v``, positive to the left).

    Args:
        path: the file to write (it is overwritten).
        z: elevations relative to the reference line, shape ``(nu, nv)``. NaN is
            allowed only at the left and right border of a cross section (for
            roads of varying width); each cross section needs a value.
        du: distance of the cross sections along the reference line, ``> 0``.
        v: lateral positions of the long sections, strictly increasing,
            shape ``(nv,)``. Equidistant positions are written in compact form.
        phi: heading of the reference line in radians. A number (or ``None``
            for 0) gives a straight line. An array gives the heading of each of
            the ``nu - 1`` segments between consecutive cross sections; an array
            with ``nu`` entries is accepted as stored in CRG files, where the
            first entry is not used.
        u0: u of the first cross section.
        x0, y0: position of the start of the reference line.
        z0: elevation of the start of the reference line.
        end_xy: position of the end of the reference line. OpenCRG then
            integrates the headings from both ends, which removes the drift of
            the single precision headings. By default it is computed from the
            headings as stored, which gives the same result as integrating from
            the start.
        slope: slope of the reference line (dz/du): a number, or one value per
            segment as for ``phi``. The reference line elevation is integrated
            from ``z0``.
        banking: cross slope (dz/dv, positive when the left side is higher): a
            number or one value per cross section.
        fmt: data format, one of ``"KRBI"`` (default), ``"KDBI"``, ``"LRFI"``,
            ``"LDFI"``.
        comment: text of the ``$CT`` section, as a string or a list of lines.
        opts: options for ``$ROAD_CRG_OPTS``, keyed by keyword (for example
            ``"border_mode_u"``, see :data:`OPTION_KEYWORDS`) or ``CP_OPTION_*``
            id. ``None`` (the default) writes no options section.
        mods: modifiers for ``$ROAD_CRG_MODS``, keyed by keyword (for example
            ``"refline_offset_z"``, see :data:`MODIFIER_KEYWORDS`) or ``MOD_*``
            id. ``None`` (the default) writes no modifiers section, so readers
            apply OpenCRG's default modifiers, which move the start of the
            reference line to the origin. Pass ``{}`` to write an empty section,
            which keeps the data where it is.
        road: further ``$ROAD_CRG`` entries, for example geographic
            coordinates of the start (see :data:`ROAD_KEYWORDS`).

    Raises:
        ValueError: the data breaks a rule of the CRG format.
    """
    np = _numpy()

    fmt = str(fmt).upper()
    if fmt not in FORMATS:
        raise ValueError(f"fmt must be one of {FORMATS}, not {fmt!r}")
    single = fmt[1] == "R"
    binary = fmt[2] == "B"

    # --- grid -----------------------------------------------------------------
    z_array = np.array(z, dtype=np.float64)
    if z_array.ndim != 2:
        raise ValueError(f"z must be two-dimensional (nu, nv), not of shape {z_array.shape}")
    nu, nv = z_array.shape
    if nu < 2 or nv < 2:
        raise ValueError(f"z needs at least 2 cross sections and 2 long sections, not {z_array.shape}")
    if np.isinf(z_array).any():
        raise ValueError("z must not contain infinite values")
    if single:
        with np.errstate(over="ignore"):
            z_array = z_array.astype(np.float32).astype(np.float64)
        if np.isinf(z_array).any():
            raise ValueError(f"z exceeds the single precision range of {fmt}")
    valid = ~np.isnan(z_array)
    if not valid.any(axis=1).all():
        rows = np.flatnonzero(~valid.any(axis=1))
        raise ValueError(f"cross section {int(rows[0])} of z has no value (only NaN)")
    # NaN only at the borders: the valid values of each row are contiguous
    first_valid = valid.argmax(axis=1)
    last_valid = nv - 1 - valid[:, ::-1].argmax(axis=1)
    inner = np.arange(nv)[None, :]
    interior_nan = (~valid) & (inner > first_valid[:, None]) & (inner < last_valid[:, None])
    if interior_nan.any():
        row, col = (int(index) for index in np.argwhere(interior_nan)[0])
        raise ValueError(f"z[{row}, {col}] is NaN between valid values; NaN is only allowed at the borders")

    du = _finite_float("du", du)
    if du <= 0:
        raise ValueError(f"du must be positive, not {du!r}")
    u0 = _finite_float("u0", u0)
    x0 = _finite_float("x0", x0)
    y0 = _finite_float("y0", y0)
    z0 = _finite_float("z0", z0)

    v_array = np.asarray(v, dtype=np.float64)
    if v_array.shape != (nv,):
        raise ValueError(f"v must have {nv} entries (one per column of z), not shape {v_array.shape}")
    if not np.all(np.isfinite(v_array)):
        raise ValueError("v must be finite")
    v_steps = np.diff(v_array)
    if (v_steps < 1e-6).any():
        raise ValueError("v must be strictly increasing, with steps of at least 1e-6 m")
    v_increment = (v_array[-1] - v_array[0]) / (nv - 1)
    v_deviation = np.max(np.abs(v_array - (v_array[0] + v_increment * np.arange(nv))))
    equidistant = bool(v_deviation <= 1e-9 * max(1.0, abs(v_array[-1] - v_array[0])))

    def stored(values: Any) -> Any:
        """The values as OpenCRG will read them back."""
        if fmt == "KRBI":
            return values.astype(np.float32).astype(np.float64)
        if fmt == "LRFI":
            return np.array([float(format_number(value, 9)) for value in values])
        if fmt == "LDFI":
            return np.array([float(format_number(value, 19)) for value in values])
        return values

    columns: list[tuple[str, Any]] = []
    road_lines: list[str] = []

    # --- reference line ---------------------------------------------------------
    if phi is None or np.ndim(phi) == 0:
        heading = 0.0 if phi is None else _finite_float("phi", phi)
        start_phi = end_phi = heading
        length = du * (nu - 1)
        end_x = x0 + length * math.cos(heading)
        end_y = y0 + length * math.sin(heading)
    else:
        headings = stored(_segment_values(np, "phi", phi, nu))
        start_phi = float(headings[0])
        end_phi = float(headings[-1])
        # the forward integration of the OpenCRG loader
        end_x = float(np.cumsum(np.concatenate(([x0], du * np.cos(headings))))[-1])
        end_y = float(np.cumsum(np.concatenate(([y0], du * np.sin(headings))))[-1])
        columns.append(("reference line phi,rad", np.concatenate(([np.nan], headings))))
    if end_xy is not None:
        if len(end_xy) != 2:
            raise ValueError("end_xy must be a pair (x, y)")
        end_x = _finite_float("end_xy[0]", end_xy[0])
        end_y = _finite_float("end_xy[1]", end_xy[1])

    slope_lines: list[str] = []
    end_z = z0
    if slope is not None:
        if np.ndim(slope) == 0:
            constant_slope = _finite_float("slope", slope)
            if constant_slope != 0.0:
                end_z = z0 + du * (nu - 1) * constant_slope
                slope_lines = [
                    _header_line("reference_line_start_s", constant_slope),
                    _header_line("reference_line_end_s", constant_slope),
                ]
        else:
            slopes = stored(_segment_values(np, "slope", slope, nu))
            end_z = float(np.cumsum(np.concatenate(([z0], du * slopes)))[-1])
            slope_lines = [
                _header_line("reference_line_start_s", float(slopes[0])),
                _header_line("reference_line_end_s", float(slopes[-1])),
            ]
            columns.append(("reference line slope,m/m", np.concatenate(([np.nan], slopes))))

    bank_lines: list[str] = []
    if banking is not None:
        if np.ndim(banking) == 0:
            constant_bank = _finite_float("banking", banking)
            bank_lines = [
                _header_line("reference_line_start_b", constant_bank),
                _header_line("reference_line_end_b", constant_bank),
            ]
        else:
            banks = np.asarray(banking, dtype=np.float64)
            if banks.shape != (nu,):
                raise ValueError(f"banking must be a number or have {nu} entries (one per cross section)")
            if not np.all(np.isfinite(banks)):
                raise ValueError("banking must be finite")
            banks = stored(banks)
            bank_lines = [
                _header_line("reference_line_start_b", float(banks[0])),
                _header_line("reference_line_end_b", float(banks[-1])),
            ]
            columns.append(("reference line banking,m/m", banks))

    road_lines += [
        _header_line("reference_line_start_u", u0),
        _header_line("reference_line_end_u", u0 + du * (nu - 1)),
        _header_line("reference_line_increment", du),
        _header_line("long_section_v_right", float(v_array[0])),
        _header_line("long_section_v_left", float(v_array[-1])),
    ]
    if equidistant:
        road_lines.append(_header_line("long_section_v_increment", v_increment))
    road_lines += slope_lines + bank_lines
    road_lines += [
        _header_line("reference_line_start_x", x0),
        _header_line("reference_line_start_y", y0),
        _header_line("reference_line_end_x", end_x),
        _header_line("reference_line_end_y", end_y),
        _header_line("reference_line_start_phi", start_phi),
        _header_line("reference_line_end_phi", end_phi),
        _header_line("reference_line_start_z", z0),
        _header_line("reference_line_end_z", end_z),
    ]
    for key, value in (road or {}).items():
        keyword = str(key).lower()
        if keyword not in ROAD_KEYWORDS:
            raise ValueError(f"road entry {key!r} cannot be set; expected one of {ROAD_KEYWORDS}")
        road_lines.append(_header_line(keyword, _finite_float(f"road entry {keyword!r}", value)))

    # --- header ---------------------------------------------------------------------
    if isinstance(comment, str):
        comment_lines = comment.splitlines()
    else:
        comment_lines = []
        for item in comment:
            comment_lines.extend(str(item).splitlines() or [""])
    if not comment_lines:
        comment_lines = [f"CRG file written by pycrg {__version__}"]
    for line in comment_lines:
        if line.startswith("$"):
            raise ValueError(f"comment lines must not start with '$': {line!r}")

    header = ["$CT", *comment_lines, "$"]
    if opts is not None:
        header += ["$ROAD_CRG_OPTS", *_keyword_entries("option", opts, OPTION_KEYWORDS), "$"]
    if mods is not None:
        header += ["$ROAD_CRG_MODS", *_keyword_entries("modifier", mods, MODIFIER_KEYWORDS), "$"]
    header += ["$ROAD_CRG", *road_lines, "$"]
    header.append(f"* written by pycrg {__version__}")
    header += ["$KD_DEFINITION", f"#:{fmt}", f"U:reference line u,m,{u0!r},{du!r}"]
    header += [f"D:{name}" for name, _ in columns]
    if equidistant:
        header += [f"D:long section {index},m" for index in range(1, nv + 1)]
    else:
        header += [f"D:long section at v = {float(position)!r},m" for position in v_array]
    header += ["$", "$" * _MAX_LINE]

    encoded = []
    for line in header:
        data = line.encode("utf-8")
        if len(data) > _MAX_LINE:
            raise ValueError(f"header line longer than {_MAX_LINE} characters: {line!r}")
        encoded.append(data + b"\n")

    # --- data -------------------------------------------------------------------------
    table = np.column_stack([values for _, values in columns] + [z_array]) if columns else z_array
    if binary:
        # big-endian values, padded with NaN to full 80 byte blocks
        dtype = np.dtype(">f4" if single else ">f8")
        per_block = 80 // dtype.itemsize
        values = np.full(-(-table.size // per_block) * per_block, np.nan, dtype=dtype)
        values[: table.size] = table.reshape(-1)
        payload = values.tobytes()
        if payload[:1] in (b"\n", b"\r"):
            # the loader skips line breaks after the "$$$$" line
            raise ValueError("the first data value is a tiny number OpenCRG would misread; change it slightly")
    else:
        width = 9 if single else 19
        per_line = 8 if single else 4
        lines = []
        for row in table:
            fields = [
                "*" * (width + 1) if math.isnan(value) else " " + format_number(float(value), width)
                for value in row.tolist()
            ]
            for start in range(0, len(fields), per_line):
                lines.append("".join(fields[start : start + per_line]))
        payload = ("\n".join(lines) + "\n").encode("ascii")

    with open(os.fspath(path), "wb") as stream:
        stream.writelines(encoded)
        stream.write(payload)
