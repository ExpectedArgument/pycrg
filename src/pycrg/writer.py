"""Writing OpenCRG files.

:func:`write` creates CRG files in the four OpenCRG data formats. It follows
the conventions of the reference writer of the OpenCRG MATLAB tools
(``crg_write`` / ``ipl_write``) and checks the rules the C loader relies on, so
that the files load with OpenCRG (and therefore with :class:`pycrg.DataSet`).
Like ``crg_write``, which runs the consistency check ``crg_check`` first, it
also refuses a reference line and header data that this check rejects.

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

# defaults of the options check_eps, check_inc and check_tol, and the tolerance
# of WGS 84 distances (check_wgs) of the OpenCRG consistency check
_CHECK_EPS = 1e-6
_CHECK_INC = 1e-3
_CHECK_WGS = 10.0


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


def _keyword_values(
    name: str, entries: Mapping[str | int, float], keywords: Mapping[str, int | None]
) -> dict[str, float]:
    by_id = {value: key for key, value in keywords.items() if value is not None}
    values: dict[str, float] = {}
    for key, value in entries.items():
        if isinstance(key, int) and not isinstance(key, bool):
            if key not in by_id:
                raise ValueError(f"unknown {name} id {key}")
            keyword = by_id[key]
        elif isinstance(key, str) and key.lower() in keywords:
            keyword = key.lower()
        else:
            raise ValueError(f"unknown {name} {key!r}; expected one of {sorted(keywords)}")
        if keyword in values:
            raise ValueError(f"{name} {keyword!r} given twice")
        number = _finite_float(f"{name} {keyword!r}", value)
        if keyword in _INTEGER_OPTIONS and number != int(number):
            raise ValueError(f"{name} {keyword!r} must be an integer, not {number!r}")
        values[keyword] = number
    return values


def _keyword_lines(values: Mapping[str, float]) -> list[str]:
    return [_header_line(keyword, number, keyword in _INTEGER_OPTIONS) for keyword, number in values.items()]


def _wgs84_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in m of two WGS 84 positions (in degrees) on the ellipsoid.

    A port of ``crg_wgs84_dist`` of the OpenCRG MATLAB tools, the inverse
    solution of Vincenty after Rainsford (``INVERSE`` of the NGS).
    """
    a = 6378137.0
    f = 1.0 / 298.257223563
    lat1, lon1, lat2, lon2 = (math.radians(value) for value in (lat1, lon1, lat2, lon2))
    if abs(lat1 - lat2) < 2.220446049250313e-16 and abs(lon1 - lon2) < 2.220446049250313e-16:
        return 0.0
    r = 1.0 - f
    tu1 = r * math.sin(lat1) / math.cos(lat1)
    tu2 = r * math.sin(lat2) / math.cos(lat2)
    cu1 = 1.0 / math.sqrt(tu1 * tu1 + 1.0)
    su1 = cu1 * tu1
    cu2 = 1.0 / math.sqrt(tu2 * tu2 + 1.0)
    s = cu1 * cu2
    baz = s * tu2
    faz = baz * tu1
    x = lon2 - lon1
    for _ in range(100):  # converges in a few iterations except near antipodes
        sx = math.sin(x)
        cx = math.cos(x)
        tu1 = cu2 * sx
        tu2 = baz - su1 * cu2 * cx
        sy = math.sqrt(tu1 * tu1 + tu2 * tu2)
        cy = s * cx + faz
        y = math.atan2(sy, cy)
        sa = s * sx / sy
        c2a = 1.0 - sa * sa
        cz = faz + faz
        if c2a > 0:
            cz = cy - cz / c2a
        e = 2.0 * cz * cz - 1.0
        c = ((4.0 - 3.0 * c2a) * f + 4.0) * c2a * f / 16.0
        d = x
        x = ((e * cy * c + cz) * sy * c + y) * sa
        x = (1.0 - c) * x * f + lon2 - lon1
        if abs(d - x) <= 0.5e-13:
            break
    x = math.sqrt((1.0 / r / r - 1.0) * c2a + 1.0) + 1.0
    x = (x - 2.0) / x
    c = (x * x / 4.0 + 1.0) / (1.0 - x)
    d = (0.375 * x * x - 1.0) * x
    s = 1.0 - 2.0 * e
    return ((((sy * sy * 4.0 - 3.0) * s * cz * d / 6.0 - e * cy) * d / 4.0 + cz) * sy * d + y) * c * a * r


# --- consistency check ----------------------------------------------------------
# The checks of the OpenCRG consistency check (crg_check of the MATLAB tools,
# crgCheck of the C library) that concern the data write() computes the header
# from; the options and modifiers are written as given.


def _check_tolerances(options: Mapping[str, float]) -> tuple[float, float]:
    """``check_eps`` and ``check_tol`` of the options; the defaults replace values
    outside their range, which the check of the options reports."""
    eps = options.get("check_eps", _CHECK_EPS)
    if not 1e-6 <= eps <= 1e-2:
        eps = _CHECK_EPS
    inc = options.get("check_inc", _CHECK_INC)
    if inc < _CHECK_INC * (1 - eps) or abs(round(inc / _CHECK_INC) * _CHECK_INC - inc) > eps * inc:
        inc = _CHECK_INC
    tol = options.get("check_tol", 0.1 * inc)
    if not eps * inc <= tol <= 0.5 * inc:
        tol = 0.1 * inc
    return eps, tol


def _check_end_point(end: tuple[float, float], computed: tuple[float, float], length: float, straight: bool) -> None:
    # the C loader warns about a larger deviation (0.5 mm for a straight line);
    # the MATLAB tools allow at least as much
    tolerance = 1e-6 * length
    explanation = " (1e-6 of its length)"
    if straight and tolerance > 5e-4:
        tolerance, explanation = 5e-4, ""
    deviation = math.hypot(end[0] - computed[0], end[1] - computed[1])
    if deviation > tolerance:
        raise ValueError(
            f"end_xy is {deviation:.3g} m away from the end of the reference line that phi and du give, "
            f"({computed[0]:.6f}, {computed[1]:.6f}); OpenCRG accepts {tolerance:.3g} m{explanation}. "
            "Leave end_xy out, or give headings that lead to it: the points of a reference line must be du apart"
        )


def _check_road(
    road: Mapping[str, float],
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    eps: float,
    tol: float,
) -> None:
    """The ``road`` entries as checked by OpenCRG (``crg_check_head``, ``crg_check_wgs84``)."""
    for first, second in (
        ("reference_line_offset_x", "reference_line_offset_y"),
        ("reference_line_start_lon", "reference_line_start_lat"),
        ("reference_line_end_lon", "reference_line_end_lat"),
    ):
        if (first in road) != (second in road):
            raise ValueError(f"road entries {first!r} and {second!r} must be given together")
    for end_key, start_key in (
        ("reference_line_end_lon", "reference_line_start_lon"),
        ("reference_line_end_alt", "reference_line_start_alt"),
    ):
        if end_key in road and start_key not in road:
            raise ValueError(f"road entry {end_key!r} needs {start_key!r}")
    limits = {
        "reference_line_start_lon": 180.0,
        "reference_line_start_lat": 90.0,
        "reference_line_end_lon": 180.0,
        "reference_line_end_lat": 90.0,
        "reference_line_offset_phi": math.pi,
    }
    for key, limit in limits.items():
        value = road.get(key)
        if value is not None and abs(value) > limit * (1 + eps):
            raise ValueError(f"road entry {key!r} must be from {-limit:g} to {limit:g}, not {value!r}")

    # start and end in WGS 84 must match those in x/y/z (crg_check_wgs84)
    if "reference_line_end_lon" in road:
        dxy = math.hypot(end[0] - start[0], end[1] - start[1])
        dll = _wgs84_distance(
            road["reference_line_start_lat"],
            road["reference_line_start_lon"],
            road["reference_line_end_lat"],
            road["reference_line_end_lon"],
        )
        allowed = max(eps * (dxy + dll) / 2, _CHECK_WGS)
        if abs(dxy - dll) > allowed:
            raise ValueError(
                f"the start and end of the reference line are {dll:.6g} m apart in lon/lat but {dxy:.6g} m in x/y; "
                f"OpenCRG accepts a difference of {allowed:.3g} m (lon is the longitude, lat the latitude)"
            )
    if "reference_line_end_alt" in road:
        dz = end[2] - start[2]
        dalt = road["reference_line_end_alt"] - road["reference_line_start_alt"]
        allowed = max(eps * abs(dz + dalt) / 2, tol)
        if dz * dalt < -tol * tol or abs(dz - dalt) > allowed:
            raise ValueError(
                f"reference_line_end_alt - reference_line_start_alt = {dalt:.6g} m differs from the elevation change "
                f"of the reference line, {dz:.6g} m (from z0 and slope); OpenCRG accepts a difference of "
                f"{allowed:.3g} m. Leave reference_line_end_alt out (OpenCRG derives it from the start altitude), "
                "or give a slope that leads to it"
            )


def _check_curvature(
    np: Any, headings: Any, du: float, u0: float, v: Any, z: Any, options: Mapping[str, float]
) -> None:
    """The curvature tests of OpenCRG (``crg_check_curvature``, ``crgCheck``).

    The global test fails if a centre of curvature of the reference line lies
    on the road, between its right and left border, where the road surface
    overlaps itself; the local test then only counts centres on data (not NaN)
    of their cross section.
    """
    if options.get("warn_curv_global", 1) == 0:
        return
    # curvature at the inner cross sections, as OpenCRG computes it from the
    # points of the reference line (the cross product of adjacent segments)
    curvature = np.sin(np.diff(headings)) / du
    # the centre of curvature is on the road where curvature * v reaches 1
    critical = np.maximum(curvature * v[0], curvature * v[-1]) >= 1.0
    if not critical.any():
        return
    local = options.get("warn_curv_local", 0) > 0
    if local:
        with np.errstate(divide="ignore"):
            centre = 1.0 / curvature
        sections = np.flatnonzero((centre >= v[0]) & (centre <= v[-1]))
        column = np.clip(np.searchsorted(v, centre[sections], side="right") - 1, 0, v.size - 2)
        valid = ~np.isnan(z[sections + 1])
        rows = np.arange(sections.size)
        critical = np.zeros_like(critical)
        critical[sections[valid[rows, column] & valid[rows, column + 1]]] = True
        if not critical.any():
            return
    worst = int(np.argmax(np.where(critical, np.abs(curvature), 0.0)))
    turn = math.degrees(math.asin(min(1.0, abs(float(curvature[worst])) * du)))
    advice = "" if local else ", or if the road has no data (NaN) there, set the option warn_curv_local to 1"
    raise ValueError(
        f"the reference line curves too sharply for the width of the road at {int(critical.sum())} cross sections, "
        f"the sharpest at u = {u0 + (worst + 1) * du:.6g} m: a curvature of {float(curvature[worst]):.4g} 1/m (radius "
        f"{1.0 / abs(float(curvature[worst])):.4g} m, the heading turns by {turn:.3g} degrees within du = {du:g} m) "
        f"puts the centre of curvature on the road (v from {float(v[0]):g} to {float(v[-1]):g} m). OpenCRG's "
        "consistency check rejects this (curvature test): smooth the reference line, for example its x/y points "
        f"before computing phi{advice}"
    )


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


def _wrap_angles(np: Any, angles: Any) -> Any:
    """Headings outside -pi to pi mapped into this range, which the MATLAB tools require."""
    return np.where(np.abs(angles) > np.pi, np.remainder(angles + np.pi, 2 * np.pi) - np.pi, angles)


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
    check: bool = True,
) -> None:
    """Write an OpenCRG file (requires numpy).

    The road surface is a grid of ``nu`` cross sections (along the reference
    line, ``du`` apart, starting at ``u0``) by ``nv`` long sections (across the
    road, at the lateral positions ``v``, positive to the left).

    Like the reference writer of the OpenCRG MATLAB tools, ``write`` refuses
    data that the OpenCRG consistency check rejects (see ``check``): the
    reference line must not curve so sharply that a centre of curvature lies
    on the road, and ``end_xy`` and the WGS 84 entries of ``road`` must fit it.

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
            first entry is not used. Headings are written from -pi to pi. The
            heading must not change by more than about ``du`` divided by the
            width of the road (left or right of the reference line) from one
            segment to the next, see ``check``.
        u0: u of the first cross section.
        x0, y0: position of the start of the reference line.
        z0: elevation of the start of the reference line.
        end_xy: position of the end of the reference line. OpenCRG then
            integrates the headings from both ends, which removes the drift of
            the single precision headings. It must be the end the headings lead
            to, within 1e-6 of the length of the reference line; a measured end
            point usually is not. By default it is computed from the headings
            as stored, which gives the same result as integrating from the
            start.
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
            coordinates of the start (see :data:`ROAD_KEYWORDS`). Longitude and
            latitude come in pairs, and an end position needs the start
            position. The end altitude must differ from the start altitude by
            the elevation change of the reference line (from ``z0`` and
            ``slope``); leave it out to let OpenCRG derive it.
        check: refuse data that the OpenCRG consistency check rejects
            (``crg_check`` of the MATLAB tools, which their ``crg_write`` runs
            first, and :meth:`pycrg.DataSet.check`): an ``end_xy`` the headings
            do not lead to, ``road`` entries that do not fit the reference line,
            and a reference line with a centre of curvature on the road. The
            curvature test follows the options ``warn_curv_global`` (0 skips
            it) and ``warn_curv_local`` (1 accepts centres of curvature where
            the road has no data). ``False`` writes such data anyway.

    Raises:
        ValueError: the data breaks a rule of the CRG format or, with
            ``check``, fails the OpenCRG consistency check.
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
    length = du * (nu - 1)
    headings: Any = None
    if phi is None or np.ndim(phi) == 0:
        heading = 0.0 if phi is None else _finite_float("phi", phi)
        if abs(heading) > math.pi:
            heading = math.remainder(heading, 2 * math.pi)
        start_phi = end_phi = heading
        end_x = x0 + length * math.cos(heading)
        end_y = y0 + length * math.sin(heading)
    else:
        headings = stored(_wrap_angles(np, _segment_values(np, "phi", phi, nu)))
        start_phi = float(headings[0])
        end_phi = float(headings[-1])
        # the forward integration of the OpenCRG loader
        end_x = float(np.cumsum(np.concatenate(([x0], du * np.cos(headings))))[-1])
        end_y = float(np.cumsum(np.concatenate(([y0], du * np.sin(headings))))[-1])
        columns.append(("reference line phi,rad", np.concatenate(([np.nan], headings))))
    computed_end = (end_x, end_y)
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
    road_values: dict[str, float] = {}
    for key, value in (road or {}).items():
        keyword = str(key).lower()
        if keyword not in ROAD_KEYWORDS:
            raise ValueError(f"road entry {key!r} cannot be set; expected one of {ROAD_KEYWORDS}")
        if keyword in road_values:
            raise ValueError(f"road entry {keyword!r} given twice")
        road_values[keyword] = _finite_float(f"road entry {keyword!r}", value)
    road_lines += [_header_line(keyword, value) for keyword, value in road_values.items()]

    options = None if opts is None else _keyword_values("option", opts, OPTION_KEYWORDS)
    modifiers = None if mods is None else _keyword_values("modifier", mods, MODIFIER_KEYWORDS)

    # --- consistency check ------------------------------------------------------------
    if check:
        eps, tol = _check_tolerances(options or {})
        if end_xy is not None:
            _check_end_point((end_x, end_y), computed_end, length, straight=headings is None)
        _check_road(road_values, (x0, y0, z0), (end_x, end_y, end_z), eps, tol)
        if headings is not None:
            _check_curvature(np, headings, du, u0, v_array, z_array, options or {})

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
    if options is not None:
        header += ["$ROAD_CRG_OPTS", *_keyword_lines(options), "$"]
    if modifiers is not None:
        header += ["$ROAD_CRG_MODS", *_keyword_lines(modifiers), "$"]
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
