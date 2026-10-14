"""Figures, the counterparts of ``crg_show`` and the ``crg_show_*`` functions.

Each figure combines several plots of :mod:`pycrg.plot._plots` in the layout
of the OpenCRG MATLAB tools and is returned without being displayed: call
``matplotlib.pyplot.show()`` to display the figures, or save them with
``Figure.savefig``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any, TypeVar

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D

from ..analysis import CrgComparison, CrgPeaks, IndexRange, Source, _index_range
from ..writer import _INTEGER_OPTIONS, MODIFIER_KEYWORDS, OPTION_KEYWORDS
from ._core import (
    FigureOptions,
    _Data,
    _data,
    _draw,
    _frame,
    _image,
    _options,
    _overlay,
    _pyplot,
    _surface,
    _thin,
)
from ._plots import (
    _elgrid_cross_sect,
    _elgrid_limits,
    _elgrid_long_sect,
    _elgrid_uvz_map,
    _elgrid_xyz_map,
    _points,
    _positions,
    _refline_curvature,
    _refline_elevation,
    _refline_heading,
    _refline_slope_bank,
    _refline_xy_map_and_curv,
    _refline_xy_overview_map,
    _refline_xyz_map,
    _refpnt_distances,
    _road_uv2uvz_map,
    _road_uv2xyz_map,
    _road_uvz_map,
    _road_xyz_map,
)

if TYPE_CHECKING:
    import numpy.typing as npt

    FloatArray = np.ndarray[Any, np.dtype[np.float64]]

__all__ = [
    "show",
    "show_elgrid_cuts_and_limits",
    "show_elgrid_surface",
    "show_info",
    "show_isequal",
    "show_peaks",
    "show_refline_elevation",
    "show_refline_map",
    "show_refpnts_and_refline",
    "show_road_surface",
    "show_road_uv2surface",
]

# crg_show shows three windows of this many cross sections of longer data
_LONG_DATA = 3000
_WINDOW = 1001

_T = TypeVar("_T")


def _building(fig: Figure, build: Callable[[], _T]) -> _T:
    """Run ``build``; close ``fig`` if it fails, so that no half-drawn figure stays open."""
    try:
        return build()
    except BaseException:
        _pyplot().close(fig)
        raise


# ---------------------------------------------------------------------------
# reference line
# ---------------------------------------------------------------------------


def _show_refline_map(data: _Data, iu: IndexRange | None, opts: FigureOptions) -> Figure:
    data.range_u(iu)
    fig = _frame(data.path, "CRG reference line map", opts)

    def build() -> Figure:
        a1 = fig.add_subplot(2, 2, 1)
        a2 = fig.add_subplot(2, 2, 2)
        a3 = fig.add_subplot(2, 2, 3, sharex=a1, sharey=a1)
        a4 = fig.add_subplot(2, 2, 4, sharex=a2)
        _refline_xy_overview_map(data, iu, a1, opts)
        _refline_heading(data, iu, a2, opts)
        _refline_xy_map_and_curv(data, iu, a3, opts)
        _refline_curvature(data, iu, a4, opts)
        return fig

    return _building(fig, build)


def show_refline_map(source: Source, iu: IndexRange | None = None, *, options: FigureOptions | None = None) -> Figure:
    """Show the reference line: x/y map, heading, curvature drawn along the
    line and curvature over u, like ``crg_show_refline_map``."""
    with _data(source) as data:
        return _show_refline_map(data, iu, _options(options))


def _show_refline_elevation(data: _Data, iu: IndexRange | None, opts: FigureOptions) -> Figure:
    data.range_u(iu)
    fig = _frame(data.path, "CRG reference line elevation", opts)

    def build() -> Figure:
        a1 = fig.add_subplot(2, 2, 1)
        a2 = fig.add_subplot(2, 2, 2)
        a3 = fig.add_subplot(2, 2, 3, projection="3d")
        a4 = fig.add_subplot(2, 2, 4, sharex=a2)
        _refline_xy_overview_map(data, iu, a1, opts)
        _refline_slope_bank(data, iu, a2, opts)
        _refline_xyz_map(data, iu, a3, opts)
        _refline_elevation(data, iu, a4, opts)
        return fig

    return _building(fig, build)


def show_refline_elevation(
    source: Source, iu: IndexRange | None = None, *, options: FigureOptions | None = None
) -> Figure:
    """Show the elevation of the reference line: x/y map, slope and banking,
    3D line and elevation over u, like ``crg_show_refline_elevation``."""
    with _data(source) as data:
        return _show_refline_elevation(data, iu, _options(options))


def _show_refpnts_and_refline(data: _Data, pxy: npt.ArrayLike, opts: FigureOptions) -> Figure:
    points = _points(pxy)
    fig = _frame(data.path, "CRG reference points and resulting reference line map", opts)

    def build() -> Figure:
        axes = [fig.add_subplot(3, 2, i) for i in range(1, 7)]
        _refline_xy_overview_map(
            data, None, axes[0], opts, points=points, title="CRG reference points in reference line XY overview map"
        )
        _refpnt_distances(data, np.column_stack(points), axes[1], opts)
        _refline_xy_overview_map(data, None, axes[2], opts)
        _refline_heading(data, None, axes[3], opts)
        _refline_xy_map_and_curv(data, None, axes[4], opts)
        _refline_curvature(data, None, axes[5], opts)
        return fig

    return _building(fig, build)


def show_refpnts_and_refline(source: Source, pxy: npt.ArrayLike, *, options: FigureOptions | None = None) -> Figure:
    """Show the points ``pxy`` (shape ``(n, 2)``, x and y) together with the
    reference line and their distances from it, like
    ``crg_show_refpnts_and_refline``. Useful to check a reference line
    generated from measured points."""
    with _data(source) as data:
        return _show_refpnts_and_refline(data, pxy, _options(options))


# ---------------------------------------------------------------------------
# elevation grid and road surface
# ---------------------------------------------------------------------------


def _show_elgrid_cuts_and_limits(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, opts: FigureOptions
) -> Figure:
    data.range_u(iu)
    data.range_v(iv)
    fig = _frame(data.path, "CRG elevation grid cuts and limits", opts)

    def build() -> Figure:
        a1 = fig.add_subplot(2, 2, 1)
        a2 = fig.add_subplot(2, 2, 2)
        a3 = fig.add_subplot(2, 2, 3)
        a4 = fig.add_subplot(2, 2, 4, sharex=a2)
        _refline_xy_overview_map(data, iu, a1, opts)
        _elgrid_limits(data, iu, iv, a2, opts)
        _elgrid_cross_sect(data, iu, iv, a3, opts)
        _elgrid_long_sect(data, iu, iv, a4, opts)
        return fig

    return _building(fig, build)


def show_elgrid_cuts_and_limits(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    options: FigureOptions | None = None,
) -> Figure:
    """Show the elevation grid as cross and long sections and its valid
    limits, like ``crg_show_elgrid_cuts_and_limits``."""
    with _data(source) as data:
        return _show_elgrid_cuts_and_limits(data, iu, iv, _options(options))


def _show_surface(
    data: _Data,
    iu: IndexRange | None,
    iv: IndexRange | None,
    opts: FigureOptions,
    title: str,
    xyz_map: Callable[[_Data, IndexRange | None, IndexRange | None, Axes | None, FigureOptions], Axes],
    uvz_map: Callable[[_Data, IndexRange | None, IndexRange | None, Axes | None, FigureOptions], Axes],
) -> Figure:
    data.range_u(iu)
    data.range_v(iv)
    fig = _frame(data.path, title, opts)

    def build() -> Figure:
        a1 = fig.add_subplot(2, 2, 1)
        a2 = fig.add_subplot(2, 2, 2, projection="3d")
        a3 = fig.add_subplot(2, 2, (3, 4))
        _refline_xy_overview_map(data, iu, a1, opts)
        xyz_map(data, iu, iv, a2, opts)
        uvz_map(data, iu, iv, a3, opts)
        return fig

    return _building(fig, build)


def _show_elgrid_surface(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, opts: FigureOptions, suffix: str = ""
) -> Figure:
    title = "CRG elevation grid surface - w/o slope and banking" + suffix
    return _show_surface(data, iu, iv, opts, title, _elgrid_xyz_map, _elgrid_uvz_map)


def show_elgrid_surface(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    options: FigureOptions | None = None,
) -> Figure:
    """Show the elevation grid (without slope and banking) as a 3D surface
    over x/y and as a map over u/v, like ``crg_show_elgrid_surface``."""
    with _data(source) as data:
        return _show_elgrid_surface(data, iu, iv, _options(options))


def _show_road_surface(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, opts: FigureOptions, suffix: str = ""
) -> Figure:
    return _show_surface(data, iu, iv, opts, "CRG road surface" + suffix, _road_xyz_map, _road_uvz_map)


def show_road_surface(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    options: FigureOptions | None = None,
) -> Figure:
    """Show the road surface (with slope, banking and reference line elevation)
    as a 3D surface over x/y and as a map over u/v, like ``crg_show_road_surface``."""
    with _data(source) as data:
        return _show_road_surface(data, iu, iv, _options(options))


def _show_road_uv2surface(data: _Data, u: npt.ArrayLike, v: npt.ArrayLike, opts: FigureOptions) -> Figure:
    uu, vv = _positions(u, "u"), _positions(v, "v")
    # outline of the u/v area in x/y
    outline_u = np.concatenate((uu, np.full(len(vv), uu[-1]), uu[::-1], np.full(len(vv), uu[0])))
    outline_v = np.concatenate((np.full(len(uu), vv[0]), vv, np.full(len(uu), vv[-1]), vv[::-1]))
    outline = data.uv_to_xy(outline_u, outline_v)
    fig = _frame(data.path, "CRG road surface", opts)

    def build() -> Figure:
        a1 = fig.add_subplot(2, 2, 1)
        a2 = fig.add_subplot(2, 2, 2, projection="3d")
        a3 = fig.add_subplot(2, 2, (3, 4))
        _refline_xy_overview_map(data, None, a1, opts, outline=outline)
        _road_uv2xyz_map(data, uu, vv, a2, opts)
        _road_uv2uvz_map(data, uu, vv, a3, opts)
        return fig

    return _building(fig, build)


def show_road_uv2surface(
    source: Source, u: npt.ArrayLike, v: npt.ArrayLike, *, options: FigureOptions | None = None
) -> Figure:
    """Show the road surface on the grid given by the positions ``u`` and ``v``
    (1D arrays), with its outline in the x/y map, like ``crg_show_road_uv2surface``.
    The grid may extend beyond the data."""
    with _data(source) as data:
        return _show_road_uv2surface(data, u, v, _options(options))


# ---------------------------------------------------------------------------
# information
# ---------------------------------------------------------------------------

# the order and names of crg_show_info
_INFO_MODIFIERS = (
    "scale_z_grid",
    "scale_slope",
    "scale_banking",
    "scale_length",
    "scale_width",
    "scale_curvature",
    "grid_nan_mode",
    "grid_nan_offset",
    "refline_offset_x",
    "refline_offset_y",
    "refline_offset_z",
    "refline_offset_phi",
    "refline_rotcenter_x",
    "refline_rotcenter_y",
    "refpoint_u",
    "refpoint_u_fraction",
    "refpoint_u_offset",
    "refpoint_v",
    "refpoint_v_fraction",
    "refpoint_v_offset",
    "refpoint_x",
    "refpoint_y",
    "refpoint_z",
    "refpoint_phi",
)
_INFO_OPTIONS = (
    "border_mode_u",
    "border_mode_v",
    "border_offset_u",
    "border_offset_v",
    "border_smooth_ubeg",
    "border_smooth_uend",
    "refline_continuation",
    "refline_search_far",
    "refline_search_close",
    "warn_curv_local",
    "warn_curv_global",
    "check_eps",
    "check_inc",
    "check_tol",
)
_INFO_GEO = (
    "reference_line_start_lon",
    "reference_line_end_lon",
    "reference_line_start_lat",
    "reference_line_end_lat",
    "reference_line_start_alt",
    "reference_line_end_alt",
)


def _entry(name: str, value: float) -> str:
    return f"{name:<25s} = {value:20.12g}"


def _info_lines(data: _Data) -> tuple[list[str], list[str]]:
    road = data.header.road if data.header is not None else {}
    lines = ["CRG elevation grid size:", _entry("length", data.nu), _entry("width", data.nv), ""]

    lines.append("CRG header data:")
    values: list[tuple[str, float | None]] = [
        ("reference_line_start_u", data.u[0]),
        ("reference_line_end_u", data.u[-1]),
        ("reference_line_increment", data.uinc),
        ("long_section_v_right", data.v[0]),
        ("long_section_v_left", data.v[-1]),
        ("long_section_v_increment", data.vinc if data.vinc else None),
    ]
    for axis, array in (("x", data.rx), ("y", data.ry), ("z", data.rz), ("phi", data.phi)):
        offset = road.get(f"reference_line_offset_{axis}")
        values += [
            (f"reference_line_start_{axis}", array[0]),
            (f"reference_line_end_{axis}", array[-1]),
            (f"reference_line_offset_{axis}", offset if isinstance(offset, (int, float)) else None),
        ]
    values += [
        ("reference_line_start_s", data.slope[0]),
        ("reference_line_end_s", data.slope[-1]),
        ("reference_line_start_b", data.bank[0]),
        ("reference_line_end_b", data.bank[-1]),
    ]
    for name in _INFO_GEO:
        geo = road.get(name)
        values.append((name, geo if isinstance(geo, (int, float)) else None))
    lines += [_entry(name, float(value)) for name, value in values if value is not None]
    lines.append("")

    # the modifiers still to be applied, as the MATLAB tools show DATA.mods
    lines.append("CRG modifier data:")
    dataset = data.dataset
    modifiers = []
    for name in _INFO_MODIFIERS:
        mod_id = MODIFIER_KEYWORDS[name]
        mod_value = (
            dataset.modifier_get_int(mod_id) if name in _INTEGER_OPTIONS else dataset.modifier_get_double(mod_id)
        )
        if mod_value is not None:
            modifiers.append(_entry(name, mod_value))
    lines += modifiers or ["(none pending: applied or not set)"]
    lines.append("")

    lines.append("CRG option data:")
    cp = data.cp
    for name in _INFO_OPTIONS:
        option_id = OPTION_KEYWORDS[name]
        assert option_id is not None
        option_value = cp.option_get_int(option_id) if name in _INTEGER_OPTIONS else cp.option_get_double(option_id)
        if option_value is not None:
            lines.append(_entry(name, option_value))
    lines.append("")

    lines.append("CRG derived data:")
    _, closed, u_min, u_max = dataset.closed_track_data()
    if closed:
        lines += [_entry("crossing_ubeg", u_min), _entry("crossing_uend", u_max)]
    lines.append(_entry("crossing_ulen", u_max - u_min if closed else 0.0))

    comment = ["CRG comment data:", ""]
    if data.header is not None:
        comment += data.header.comment.splitlines()
    return lines, comment


# font sizes of the information text: shrunk to fit as in crg_show_info, but
# not below the minimum, where long text is cut instead
_TEXT_SIZE = 10.0
_TEXT_MIN_SIZE = 6.0
# line height and (monospace) character width relative to the font size
_LINE_HEIGHT = 1.3
_CHAR_WIDTH = 0.62


def _text_block(fig: Figure, x: float, lines: Sequence[str]) -> None:
    """A text box at ``x`` of 46 % of the figure width and 86 % of its height."""
    width = fig.get_figwidth() * 72 * 0.46
    height = fig.get_figheight() * 72 * 0.86
    chars = max((len(line) for line in lines), default=1)
    size = min(_TEXT_SIZE, height / (max(len(lines), 1) * _LINE_HEIGHT), width / (max(chars, 1) * _CHAR_WIDTH))
    if size < _TEXT_MIN_SIZE:
        size = _TEXT_MIN_SIZE
        max_lines = int(height / (size * _LINE_HEIGHT))
        max_chars = int(width / (size * _CHAR_WIDTH))
        lines = [line if len(line) <= max_chars else line[: max_chars - 3] + "..." for line in lines]
        if len(lines) > max_lines:
            lines = [*lines[: max_lines - 1], f"... ({len(lines) - max_lines + 1} more lines)"]
    fig.text(x, 0.93, "\n".join(lines), ha="left", va="top", family="monospace", fontsize=size)


def _show_info(data: _Data, opts: FigureOptions) -> Figure:
    left, right = _info_lines(data)
    fig = _frame(data.path, "CRG information", opts)
    _text_block(fig, 0.02, left)
    _text_block(fig, 0.52, right)
    return fig


def show_info(source: Source, *, options: FigureOptions | None = None) -> Figure:
    """Show the grid size, reference line, pending modifiers, options and
    comment text of a data set as text, like ``crg_show_info``.

    The values are those of the loaded data set, after any applied
    modifiers; modifiers are listed only while they are not applied yet.
    """
    with _data(source) as data:
        return _show_info(data, _options(options))


# ---------------------------------------------------------------------------
# peaks and comparison
# ---------------------------------------------------------------------------


def _peak_indices(data: _Data, peaks: CrgPeaks | npt.ArrayLike) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]]:
    if isinstance(peaks, CrgPeaks):
        return peaks.iu, peaks.iv
    array = np.asarray(peaks)
    if array.size == 0:
        return np.zeros(0, dtype=np.intp), np.zeros(0, dtype=np.intp)
    if array.ndim != 2 or array.shape[1] != 2 or not np.issubdtype(array.dtype, np.integer):
        raise ValueError("peaks must be a CrgPeaks or an integer array of (iu, iv) indices, shape (n, 2)")
    iu, iv = array[:, 0].astype(np.intp), array[:, 1].astype(np.intp)
    if np.min(iu) < 0 or np.max(iu) >= data.nu or np.min(iv) < 0 or np.max(iv) >= data.nv:
        raise ValueError("peak indices outside the grid")
    return iu, iv


def _show_peaks(
    data: _Data,
    peaks: CrgPeaks | npt.ArrayLike,
    su: IndexRange | None,
    sv: IndexRange | None,
    iu: IndexRange | None,
    iv: IndexRange | None,
    opts: FigureOptions,
) -> Figure:
    plot_u = data.range_u(iu)
    plot_v = data.range_v(iv)
    index_u, index_v = _peak_indices(data, peaks)
    default_u = peaks.search_iu if isinstance(peaks, CrgPeaks) else plot_u
    default_v = peaks.search_iv if isinstance(peaks, CrgPeaks) else plot_v
    s0, s1 = _index_range(su if su is not None else default_u, data.nu, "su")
    t0, t1 = _index_range(sv if sv is not None else default_v, data.nv, "sv")

    pu, pv = data.u[index_u], data.v[index_v]
    px, py = data.uv_to_xy(pu, pv)
    pz = data.uv_to_z(pu, pv)
    box_u = [data.u[s0], data.u[s1 - 1], data.u[s1 - 1], data.u[s0], data.u[s0]]
    box_v = [data.v[t0], data.v[t0], data.v[t1 - 1], data.v[t1 - 1], data.v[t0]]
    marker: dict[str, Any] = {"marker": "o", "linestyle": "none", "markersize": 10, "markeredgewidth": 2}
    marker |= {"markeredgecolor": "k", "markerfacecolor": "w"}

    def mark_xyz(ax: Axes) -> None:
        assert isinstance(ax, Axes3D)
        ax.computed_zorder = False  # keep the markers in front of the surface
        ax.plot(px, py, pz, zorder=10, **marker)

    def mark_uv(ax: Axes) -> None:
        ax.plot(pu, pv, zorder=10, **marker)
        ax.plot(box_u, box_v, "--m", linewidth=2, zorder=10)

    fig = _frame(data.path, "CRG peak visualizer", opts)

    def build() -> Figure:
        a1 = fig.add_subplot(2, 2, 1)
        a2 = fig.add_subplot(2, 2, 2, projection="3d")
        a3 = fig.add_subplot(2, 2, (3, 4))
        _refline_xy_overview_map(data, plot_u, a1, opts)
        _overlay(_road_xyz_map(data, plot_u, plot_v, a2, opts), mark_xyz)
        _overlay(_road_uvz_map(data, plot_u, plot_v, a3, opts), mark_uv)
        return fig

    return _building(fig, build)


def show_peaks(
    source: Source,
    peaks: CrgPeaks | npt.ArrayLike,
    su: IndexRange | None = None,
    sv: IndexRange | None = None,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    options: FigureOptions | None = None,
) -> Figure:
    """Show peaks on the road surface, like ``crg_show_peaks``.

    Args:
        source: the data set the peaks were found in.
        peaks: the result of :func:`pycrg.find_peaks`, or an integer array of
            ``(iu, iv)`` grid indices, shape ``(n, 2)``.
        su, sv: the searched index ranges, drawn as a dashed rectangle
            (default: those of ``peaks``, or the plotted ranges).
        iu, iv: the plotted index ranges (default: everything).
    """
    with _data(source) as data:
        return _show_peaks(data, peaks, su, sv, iu, iv, _options(options))


def show_isequal(comparison: CrgComparison, *, options: FigureOptions | None = None) -> Figure:
    """Show the result of :func:`pycrg.compare`, like ``crg_show_isequal``:
    a histogram of the elevation differences, a map and 3D surfaces of the
    absolute and relative differences, and the errors and warnings."""
    if not isinstance(comparison, CrgComparison):
        raise TypeError(f"expected a pycrg.analysis.CrgComparison, not {type(comparison).__name__}")
    opts = _options(options)
    rows = _thin(len(comparison.u), opts.max_surface[0])
    columns = _thin(len(comparison.v), opts.max_surface[1])
    u, v = comparison.u, comparison.v
    difference = comparison.difference
    relative = np.where(np.isfinite(comparison.relative), comparison.relative, np.nan)
    image_rows = _thin(len(u), opts.max_image[0])
    image_columns = _thin(len(v), opts.max_image[1])
    grid_u, grid_v = np.meshgrid(u[rows], v[columns], indexing="ij")
    finite = difference[np.isfinite(difference)]

    status = ["identical" if comparison.identical else "different"]
    if finite.size:
        status.append(f"max |dz| = {np.max(finite):.6g} m (tolerance {comparison.tolerance:g})")
    status += [f"error: {message}" for message in comparison.errors]
    status += [f"warning: {message}" for message in comparison.warnings]
    text = "\n".join(status)

    def histogram(ax: Axes) -> None:
        ylabel = "Count [#]"
        if finite.size:
            counts = np.asarray(ax.hist(finite, bins="auto")[0])
            nonzero = counts[counts > 0]
            if nonzero.size and nonzero.max() > 100 * nonzero.min():
                ax.set_yscale("log")  # keep rare large differences visible
                ylabel = "Count [#] (log)"
        ax.set_xlabel("Diff [m]")
        ax.set_ylabel(ylabel)
        ax.set_title("CRG histogram of the absolute elevation differences")
        ax.text(
            0.98,
            0.95,
            text,
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize="small",
            bbox={"facecolor": "w", "alpha": 0.8},
        )

    def difference_map(ax: Axes) -> None:
        _image(ax, u[image_rows], v[image_columns], difference[np.ix_(image_rows, image_columns)], opts, "|dz| [m]")
        ax.set_title("CRG absolute elevation differences")

    def absolute_surface(ax: Axes) -> None:
        assert isinstance(ax, Axes3D)
        _surface(ax, grid_u, grid_v, difference[np.ix_(rows, columns)], opts, "|dz| [m]", elevation=False)
        ax.set_title("CRG absolute elevation differences")
        ax.set_xlabel("U [m]")
        ax.set_ylabel("V [m]")
        ax.set_zlabel("|dz| [m]")

    def relative_surface(ax: Axes) -> None:
        assert isinstance(ax, Axes3D)
        _surface(ax, grid_u, grid_v, relative[np.ix_(rows, columns)], opts, "dz/z [%]", elevation=False)
        ax.set_title("CRG relative elevation differences")
        ax.set_xlabel("U [m]")
        ax.set_ylabel("V [m]")
        ax.set_zlabel("dz/z [%]")

    label = opts.file_label
    if label is None and comparison.paths is not None:
        label = "  vs.  ".join(os.path.basename(path) for path in comparison.paths)
    fig = _frame(None, "CRG comparison", replace(opts, file_label=label))

    def build() -> Figure:
        _draw(fig.add_subplot(2, 2, 1), histogram)
        _draw(fig.add_subplot(2, 2, 2), difference_map)
        _draw(fig.add_subplot(2, 2, 3, projection="3d"), absolute_surface, three_d=True)
        _draw(fig.add_subplot(2, 2, 4, projection="3d"), relative_surface, three_d=True)
        return fig

    return _building(fig, build)


# ---------------------------------------------------------------------------
# all figures
# ---------------------------------------------------------------------------


def _windows(data: _Data, start: int, stop: int) -> list[tuple[tuple[int, int], str]]:
    """The u ranges of the surface figures: everything, or for more than 3000
    cross sections, 1001 at the start, in the middle and at the end."""
    count = stop - start
    if count <= _LONG_DATA:
        return [((start, stop), "")]
    middle = start + int(count / 2 + 0.5) - _WINDOW // 2
    ranges = [(start, start + _WINDOW), (middle, middle + _WINDOW), (stop - _WINDOW, stop)]
    return [((a, b), f" (u = {data.u[a]:g} ... {data.u[b - 1]:g} m)") for a, b in ranges]


def _show(data: _Data, iu: IndexRange | None, iv: IndexRange | None, opts: FigureOptions) -> list[Figure]:
    start, stop = data.range_u(iu)
    data.range_v(iv)
    figures: list[Figure] = []
    try:
        if data.curved:
            figures.append(_show_refline_map(data, iu, opts))
        if data.elevated:
            figures.append(_show_refline_elevation(data, iu, opts))
        figures.append(_show_elgrid_cuts_and_limits(data, iu, iv, opts))
        windows = _windows(data, start, stop)
        if data.elevated:
            figures += [_show_elgrid_surface(data, window, iv, opts, suffix) for window, suffix in windows]
        figures += [_show_road_surface(data, window, iv, opts, suffix) for window, suffix in windows]
        figures.append(_show_info(data, opts))
    except BaseException:
        for fig in figures:
            _pyplot().close(fig)
        raise
    return figures


def show(
    source: Source, iu: IndexRange | None = None, iv: IndexRange | None = None, *, options: FigureOptions | None = None
) -> list[Figure]:
    """Show a data set in several figures, like ``crg_show`` of the OpenCRG tools.

    The figures are:

    * the reference line map (for a curved reference line),
    * the reference line elevation (with slope or banking),
    * the elevation grid cuts and limits,
    * the elevation grid surface (with slope or banking),
    * the road surface,
    * the information text.

    For more than 3000 cross sections, the surface figures show 1001 cross
    sections at the start, in the middle and at the end of the selection.

    Args:
        source: a :class:`~pycrg.DataSet` or :class:`~pycrg.RoadSurface`.
        iu, iv: index ranges ``(start, stop)`` of the cross and long sections
            to show, as Python slices (default: everything).
        options: :class:`FigureOptions` of all figures.

    Returns:
        The figures, not yet displayed: call ``matplotlib.pyplot.show()`` to
        display them (in Jupyter they are displayed automatically).
    """
    with _data(source) as data:
        return _show(data, iu, iv, _options(options))
