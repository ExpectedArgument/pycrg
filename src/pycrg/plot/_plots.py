"""Single plots, the counterparts of the ``crg_plot_*`` functions of the OpenCRG tools.

Each public function draws into ``ax`` (or a new figure) and returns the axes.
The ``_*`` functions do the work on extracted plot data, so that a figure can
share one extraction between its subplots.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np
from matplotlib.axes import Axes
from mpl_toolkits.mplot3d import Axes3D

from ..analysis import IndexRange, Source
from ._core import (
    FigureOptions,
    _Data,
    _data,
    _draw,
    _image,
    _options,
    _set_3d_aspect,
    _surface,
    _thin,
)

if TYPE_CHECKING:
    import numpy.typing as npt

    FloatArray = np.ndarray[Any, np.dtype[np.float64]]

__all__ = [
    "plot_elgrid_cross_sect",
    "plot_elgrid_limits",
    "plot_elgrid_long_sect",
    "plot_elgrid_uvz_map",
    "plot_elgrid_xyz_map",
    "plot_refline_curvature",
    "plot_refline_elevation",
    "plot_refline_heading",
    "plot_refline_slope_bank",
    "plot_refline_xy_map_and_curv",
    "plot_refline_xy_overview_map",
    "plot_refline_xyz_map",
    "plot_refpnt_distances",
    "plot_road_uv2uvz_map",
    "plot_road_uv2xyz_map",
    "plot_road_uvz_map",
    "plot_road_xyz_map",
]


def _equal_aspect(ax: Axes) -> None:
    """Equal x/y scales (MATLAB ``axis equal``); axes sharing both directions
    with others must adjust their box instead of their limits."""
    shared = len(ax.get_shared_x_axes().get_siblings(ax)) > 1 and len(ax.get_shared_y_axes().get_siblings(ax)) > 1
    ax.set_aspect("equal", adjustable="box" if shared else "datalim")


def _std(values: FloatArray) -> float:
    return float(np.std(values, ddof=1)) if values.size > 1 else 0.0


def _mean_std_lines(ax: Axes, start: float, end: float, mean: float, std: float) -> None:
    ax.plot([start, end], [mean, mean], "r-.", label=f"mean = {mean:.6g}")
    ax.plot([start, end, np.nan, start, end], [mean + std, mean + std, np.nan, mean - std, mean - std], "r--")
    ax.lines[-1].set_label(f"std = {std:.6g}")


def _points(pxy: npt.ArrayLike) -> tuple[FloatArray, FloatArray]:
    points = np.asarray(pxy, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) == 0:
        raise ValueError("pxy must be an array of (x, y) points, shape (n, 2)")
    return points[:, 0], points[:, 1]


def _positions(values: npt.ArrayLike, name: str) -> FloatArray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or len(array) < 2 or not np.isfinite(array).all():
        raise ValueError(f"{name} must be a 1D array of at least two finite positions")
    return array


# ---------------------------------------------------------------------------
# reference line
# ---------------------------------------------------------------------------


def _refline_xy_overview_map(
    data: _Data,
    iu: IndexRange | None,
    ax: Axes | None,
    opts: FigureOptions,
    *,
    points: tuple[FloatArray, FloatArray] | None = None,
    outline: tuple[FloatArray, FloatArray] | None = None,
    title: str = "CRG reference line XY overview map",
) -> Axes:
    start, stop = data.range_u(iu)
    rx, ry = data.rx, data.ry
    partial = start > 0 or stop < data.nu
    sx, sy = rx[start:stop], ry[start:stop]
    xlabel, ylabel = data.label_x(), data.label_y()

    def draw(ax: Axes) -> None:
        if points is not None:
            ax.plot(points[0], points[1], ".")
        if partial:
            ax.plot(rx, ry, ":")  # the whole reference line
        ax.plot(sx, sy, "-")  # the selected part
        ax.plot(sx[0], sy[0], ">")  # start of the selected part
        ax.plot(sx[-1], sy[-1], "s")  # end of the selected part
        if outline is not None:
            ax.plot(outline[0], outline[1], "-")
        _equal_aspect(ax)
        ax.grid(True)
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

    return _draw(ax, draw)


def plot_refline_xy_overview_map(
    source: Source, iu: IndexRange | None = None, *, ax: Axes | None = None, options: FigureOptions | None = None
) -> Axes:
    """Plot the reference line in x/y, like ``crg_plot_refline_xy_overview_map``.

    With ``iu``, the whole line is dotted and the selected part solid; ``>``
    and a square mark the start and end of the selection.
    """
    with _data(source) as data:
        return _refline_xy_overview_map(data, iu, ax, _options(options))


def _refline_heading(data: _Data, iu: IndexRange | None, ax: Axes | None, opts: FigureOptions) -> Axes:
    start, stop = data.range_u(iu)
    u = data.u[start:stop]
    heading = np.degrees(data.heading[start:stop])
    ylabel = data.label_heading()

    def draw(ax: Axes) -> None:
        ax.step(u, heading, "-", where="post")
        ax.plot(u[0], heading[0], ">")
        ax.plot(u[-1], heading[-1], "s")
        ax.grid(True)
        ax.set_title("CRG reference line heading")
        ax.set_xlabel("U [m]")
        ax.set_ylabel(ylabel)

    return _draw(ax, draw)


def plot_refline_heading(
    source: Source, iu: IndexRange | None = None, *, ax: Axes | None = None, options: FigureOptions | None = None
) -> Axes:
    """Plot the heading along the reference line in degrees, like ``crg_plot_refline_heading``."""
    with _data(source) as data:
        return _refline_heading(data, iu, ax, _options(options))


def _refline_xy_map_and_curv(data: _Data, iu: IndexRange | None, ax: Axes | None, opts: FigureOptions) -> Axes:
    start, stop = data.range_u(iu)
    rx, ry = data.rx[start:stop], data.ry[start:stop]
    heading = data.heading[start:stop]
    curvature = data.curvature[start:stop] if data.curved else np.zeros(stop - start)
    largest = (float(np.max(np.abs(data.curvature))) if data.curved else 0.0) + data.check_eps
    # the curvature drawn normal to the line, scaled to 0.1 of the selected length
    scale = -0.1 * (stop - start) * data.uinc / largest
    cx = rx - scale * curvature * np.sin(heading)
    cy = ry + scale * curvature * np.cos(heading)
    xlabel, ylabel = data.label_x(), data.label_y()

    def draw(ax: Axes) -> None:
        ax.plot(rx, ry, "-", label="reference line")
        ax.plot(cx, cy, "-", label="norm. neg. curvature")
        ax.plot(rx[0], ry[0], ">")
        ax.plot(rx[-1], ry[-1], "s")
        _equal_aspect(ax)
        ax.grid(True)
        ax.set_title("CRG reference line XY map with norm. neg. curvature")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.legend()

    return _draw(ax, draw)


def plot_refline_xy_map_and_curv(
    source: Source, iu: IndexRange | None = None, *, ax: Axes | None = None, options: FigureOptions | None = None
) -> Axes:
    """Plot the reference line and its curvature, drawn normal to the line and
    scaled to a tenth of the line length, like ``crg_plot_refline_xy_map_and_curv``."""
    with _data(source) as data:
        return _refline_xy_map_and_curv(data, iu, ax, _options(options))


def _refline_curvature(data: _Data, iu: IndexRange | None, ax: Axes | None, opts: FigureOptions) -> Axes:
    start, stop = data.range_u(iu)
    u = data.u[start:stop]
    curvature = data.curvature[start:stop] if data.curved else np.zeros(stop - start)
    mean, std = float(np.mean(curvature)), _std(curvature)

    def draw(ax: Axes) -> None:
        ax.step(u, curvature, "-", where="post", label="curvature")
        _mean_std_lines(ax, u[0], u[-1], mean, std)
        ax.plot(u[0], curvature[0], ">")
        ax.plot(u[-1], curvature[-1], "s")
        ax.grid(True)
        ax.set_title("CRG reference line curvature")
        ax.set_xlabel("U [m]")
        ax.set_ylabel("curvature [1/m]")
        ax.legend()

    return _draw(ax, draw)


def plot_refline_curvature(
    source: Source, iu: IndexRange | None = None, *, ax: Axes | None = None, options: FigureOptions | None = None
) -> Axes:
    """Plot the curvature along the reference line with its mean and standard
    deviation, like ``crg_plot_refline_curvature``.

    The curvature at a cross section is the cross product of the adjacent
    reference line segments divided by the cube of the increment (0 at both ends).
    """
    with _data(source) as data:
        return _refline_curvature(data, iu, ax, _options(options))


def _refline_slope_bank(data: _Data, iu: IndexRange | None, ax: Axes | None, opts: FigureOptions) -> Axes:
    start, stop = data.range_u(iu)
    u = data.u[start:stop]
    slope = 100.0 * data.slope_steps[start:stop]
    bank = 100.0 * data.bank[start:stop]

    def draw(ax: Axes) -> None:
        ax.step(u, slope, "-", where="post", label="slope")
        ax.plot(u, bank, "-", label="banking")
        ax.plot([u[0], u[0]], [slope[0], bank[0]], ">")
        ax.plot([u[-1], u[-1]], [slope[-1], bank[-1]], "s")
        ax.grid(True)
        ax.set_title("CRG reference line slope and banking")
        ax.set_xlabel("U [m]")
        ax.set_ylabel("slope & banking [%]")
        ax.legend()

    return _draw(ax, draw)


def plot_refline_slope_bank(
    source: Source, iu: IndexRange | None = None, *, ax: Axes | None = None, options: FigureOptions | None = None
) -> Axes:
    """Plot slope and banking along the reference line in percent, like
    ``crg_plot_refline_slope_bank``."""
    with _data(source) as data:
        return _refline_slope_bank(data, iu, ax, _options(options))


def _refline_xyz_map(data: _Data, iu: IndexRange | None, ax: Axes | None, opts: FigureOptions) -> Axes:
    start, stop = data.range_u(iu)
    rx, ry, rz = data.rx[start:stop], data.ry[start:stop], data.rz[start:stop]
    xlabel, ylabel, zlabel = data.label_x(), data.label_y(), data.label_z()

    def draw(ax: Axes) -> None:
        assert isinstance(ax, Axes3D)
        ax.plot(rx, ry, rz, "-")
        ax.plot([rx[0]], [ry[0]], [rz[0]], ">")
        ax.plot([rx[-1]], [ry[-1]], [rz[-1]], "s")
        _set_3d_aspect(ax, rx, ry, rz, opts.z_aspect)
        ax.grid(True)
        ax.set_title("CRG reference line XYZ map")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_zlabel(zlabel)

    return _draw(ax, draw, three_d=True)


def plot_refline_xyz_map(
    source: Source, iu: IndexRange | None = None, *, ax: Axes | None = None, options: FigureOptions | None = None
) -> Axes:
    """Plot the reference line in x/y/z (3D, ``ax`` must be a 3D axes), like
    ``crg_plot_refline_xyz_map``."""
    with _data(source) as data:
        return _refline_xyz_map(data, iu, ax, _options(options))


def _refline_elevation(data: _Data, iu: IndexRange | None, ax: Axes | None, opts: FigureOptions) -> Axes:
    start, stop = data.range_u(iu)
    u, rz = data.u[start:stop], data.rz[start:stop]
    ylabel = data.label_z()

    def draw(ax: Axes) -> None:
        ax.plot(u, rz, "-")
        ax.plot(u[0], rz[0], ">")
        ax.plot(u[-1], rz[-1], "s")
        ax.grid(True)
        ax.set_title("CRG reference line elevation")
        ax.set_xlabel("U [m]")
        ax.set_ylabel(ylabel)

    return _draw(ax, draw)


def plot_refline_elevation(
    source: Source, iu: IndexRange | None = None, *, ax: Axes | None = None, options: FigureOptions | None = None
) -> Axes:
    """Plot the elevation of the reference line, like ``crg_plot_refline_elevation``."""
    with _data(source) as data:
        return _refline_elevation(data, iu, ax, _options(options))


def _refpnt_distances(data: _Data, pxy: npt.ArrayLike, ax: Axes | None, opts: FigureOptions) -> Axes:
    px, py = _points(pxy)
    pu, pv = data.xy_to_uv(px, py)
    valid = pv[np.isfinite(pv)]
    mean = float(np.mean(valid)) if valid.size else math.nan
    std = _std(valid)
    ubeg, uend = float(data.u[0]), float(data.u[-1])

    def draw(ax: Axes) -> None:
        ax.plot(pu, pv, ".", label="point distances")
        _mean_std_lines(ax, ubeg, uend, mean, std)
        ax.grid(True)
        ax.set_title("CRG reference point distances from reference line")
        ax.set_xlabel("U [m]")
        ax.set_ylabel("point distance V [m]")
        ax.legend()

    return _draw(ax, draw)


def plot_refpnt_distances(
    source: Source, pxy: npt.ArrayLike, *, ax: Axes | None = None, options: FigureOptions | None = None
) -> Axes:
    """Plot the distance of the points ``pxy`` (shape ``(n, 2)``, x and y) from
    the reference line over their u position, like ``crg_plot_refpnt_distances``."""
    with _data(source) as data:
        return _refpnt_distances(data, pxy, ax, _options(options))


# ---------------------------------------------------------------------------
# elevation grid
# ---------------------------------------------------------------------------


def _elgrid_limits(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, ax: Axes | None, opts: FigureOptions
) -> Axes:
    start, stop = data.range_u(iu)
    v0, v1 = data.range_v(iv)
    left, right = data.limits
    left = np.minimum(v1 - 1, left[start:stop])
    right = np.maximum(v0, right[start:stop])
    u = data.u[start:stop]
    v_left = np.where(left >= 0, data.v[left], np.nan)
    v_right = np.where(right >= 0, data.v[right], np.nan)

    def draw(ax: Axes) -> None:
        ax.plot(u, v_left, "-", label="left limit")
        ax.plot(u, v_right, "-", label="right limit")
        ax.plot([u[0], u[0]], [v_left[0], v_right[0]], ">")
        ax.plot([u[-1], u[-1]], [v_left[-1], v_right[-1]], "s")
        ax.grid(True)
        ax.set_title("CRG elevation grid limits")
        ax.set_xlabel("U [m]")
        ax.set_ylabel("V [m]")
        ax.legend()

    return _draw(ax, draw)


def plot_elgrid_limits(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    ax: Axes | None = None,
    options: FigureOptions | None = None,
) -> Axes:
    """Plot the left and right limits of the valid (non-NaN) elevation data,
    like ``crg_plot_elgrid_limits``."""
    with _data(source) as data:
        return _elgrid_limits(data, iu, iv, ax, _options(options))


def _elgrid_cross_sect(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, ax: Axes | None, opts: FigureOptions
) -> Axes:
    start, stop = data.range_u(iu)
    v0, v1 = data.range_v(iv)
    step = math.ceil((stop - start) / 9)
    rows = [*range(start, stop - 1, step), stop - 1]
    v = data.v[v0:v1]
    sections = [(float(data.u[i]), data.z[i, v0:v1]) for i in rows]

    def draw(ax: Axes) -> None:
        for u, z in sections:
            ax.plot(v, z, "-", label=f"at u = {u:g}")
        ax.invert_xaxis()  # left (positive v) on the left, looking along u
        ax.grid(True)
        ax.set_title("CRG elevation grid cross sections - w/o slope & banking & offset")
        ax.set_xlabel("V [m]")
        ax.set_ylabel("Z [m]")
        ax.legend()

    return _draw(ax, draw)


def plot_elgrid_cross_sect(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    ax: Axes | None = None,
    options: FigureOptions | None = None,
) -> Axes:
    """Plot about ten cross sections of the elevation grid (relative to the
    reference line) over v, like ``crg_plot_elgrid_cross_sect``."""
    with _data(source) as data:
        return _elgrid_cross_sect(data, iu, iv, ax, _options(options))


def _elgrid_long_sect(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, ax: Axes | None, opts: FigureOptions
) -> Axes:
    start, stop = data.range_u(iu)
    v0, v1 = data.range_v(iv)
    step = math.ceil((v1 - v0) / 5)
    columns = [*range(v0, v1 - 1, step), v1 - 1]
    u = data.u[start:stop]
    sections = [(float(data.v[j]), data.z[start:stop, j]) for j in columns]

    def draw(ax: Axes) -> None:
        for v, z in sections:
            (line,) = ax.plot(u, z, "-", label=f"at v = {v:g}")
            ax.plot(u[0], z[0], ">", color=line.get_color())
            ax.plot(u[-1], z[-1], "s", color=line.get_color())
        ax.grid(True)
        ax.set_title("CRG elevation grid long sections - w/o slope & banking & offset")
        ax.set_xlabel("U [m]")
        ax.set_ylabel("Z [m]")
        ax.legend()

    return _draw(ax, draw)


def plot_elgrid_long_sect(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    ax: Axes | None = None,
    options: FigureOptions | None = None,
) -> Axes:
    """Plot about six long sections of the elevation grid (relative to the
    reference line) over u, like ``crg_plot_elgrid_long_sect``."""
    with _data(source) as data:
        return _elgrid_long_sect(data, iu, iv, ax, _options(options))


def _selection(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, maximum: tuple[int, int]
) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]]:
    """Grid indices of the selected area, thinned out to ``maximum`` nodes."""
    start, stop = data.range_u(iu)
    v0, v1 = data.range_v(iv)
    rows = start + _thin(stop - start, maximum[0])
    columns = v0 + _thin(v1 - v0, maximum[1])
    return rows, columns


def _elgrid_uvz_map(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, ax: Axes | None, opts: FigureOptions
) -> Axes:
    rows, columns = _selection(data, iu, iv, opts.max_image)
    u, v = data.u[rows], data.v[columns]
    z = data.z[np.ix_(rows, columns)]

    def draw(ax: Axes) -> None:
        _image(ax, u, v, z, opts, "Z [m]")
        ax.set_title("CRG elevation grid UVZ map (in uncurved UV grid)")

    return _draw(ax, draw)


def plot_elgrid_uvz_map(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    ax: Axes | None = None,
    options: FigureOptions | None = None,
) -> Axes:
    """Plot the elevation grid (relative to the reference line) as a map over
    u and v, like ``crg_plot_elgrid_uvz_map``."""
    with _data(source) as data:
        return _elgrid_uvz_map(data, iu, iv, ax, _options(options))


def _elgrid_xyz_map(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, ax: Axes | None, opts: FigureOptions
) -> Axes:
    rows, columns = _selection(data, iu, iv, opts.max_surface)
    x, y = data.uv_to_xy(data.u[rows, None], data.v[None, columns])
    z = data.z[np.ix_(rows, columns)]
    xlabel, ylabel = data.label_x(), data.label_y()

    def draw(ax: Axes) -> None:
        assert isinstance(ax, Axes3D)
        _surface(ax, x, y, z, opts, "Z [m]")
        ax.set_title("CRG elevation grid XYZ map (in curved XY grid)")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_zlabel("Z [m]")

    return _draw(ax, draw, three_d=True)


def plot_elgrid_xyz_map(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    ax: Axes | None = None,
    options: FigureOptions | None = None,
) -> Axes:
    """Plot the elevation grid (relative to the reference line) as a 3D surface
    over the curved x/y grid, like ``crg_plot_elgrid_xyz_map``."""
    with _data(source) as data:
        return _elgrid_xyz_map(data, iu, iv, ax, _options(options))


# ---------------------------------------------------------------------------
# road surface
# ---------------------------------------------------------------------------


def _road_uvz_map(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, ax: Axes | None, opts: FigureOptions
) -> Axes:
    rows, columns = _selection(data, iu, iv, opts.max_image)
    u, v = data.u[rows], data.v[columns]
    z = data.uv_to_z(u[:, None], v[None, :])
    zlabel = data.label_z()

    def draw(ax: Axes) -> None:
        _image(ax, u, v, z, opts, zlabel)
        ax.set_title("CRG road UVZ map (in uncurved UV grid)")

    return _draw(ax, draw)


def plot_road_uvz_map(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    ax: Axes | None = None,
    options: FigureOptions | None = None,
) -> Axes:
    """Plot the road elevation (with slope, banking and reference line
    elevation) as a map over u and v, like ``crg_plot_road_uvz_map``."""
    with _data(source) as data:
        return _road_uvz_map(data, iu, iv, ax, _options(options))


def _road_xyz_map(
    data: _Data, iu: IndexRange | None, iv: IndexRange | None, ax: Axes | None, opts: FigureOptions
) -> Axes:
    rows, columns = _selection(data, iu, iv, opts.max_surface)
    u, v = data.u[rows, None], data.v[None, columns]
    x, y = data.uv_to_xy(u, v)
    z = data.uv_to_z(u, v)
    xlabel, ylabel, zlabel = data.label_x(), data.label_y(), data.label_z()

    def draw(ax: Axes) -> None:
        assert isinstance(ax, Axes3D)
        _surface(ax, x, y, z, opts, zlabel)
        ax.set_title("CRG road XYZ map (in curved XY grid)")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_zlabel(zlabel)

    return _draw(ax, draw, three_d=True)


def plot_road_xyz_map(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    ax: Axes | None = None,
    options: FigureOptions | None = None,
) -> Axes:
    """Plot the road surface as a 3D surface over the curved x/y grid, like
    ``crg_plot_road_xyz_map``."""
    with _data(source) as data:
        return _road_xyz_map(data, iu, iv, ax, _options(options))


def _road_uv2uvz_map(data: _Data, u: npt.ArrayLike, v: npt.ArrayLike, ax: Axes | None, opts: FigureOptions) -> Axes:
    uu, vv = _positions(u, "u"), _positions(v, "v")
    uu = uu[_thin(len(uu), opts.max_image[0])]
    vv = vv[_thin(len(vv), opts.max_image[1])]
    z = data.uv_to_z(uu[:, None], vv[None, :])
    zlabel = data.label_z()

    def draw(ax: Axes) -> None:
        _image(ax, uu, vv, z, opts, zlabel)
        ax.set_title("CRG road UVZ map (in uncurved UV grid)")

    return _draw(ax, draw)


def plot_road_uv2uvz_map(
    source: Source,
    u: npt.ArrayLike,
    v: npt.ArrayLike,
    *,
    ax: Axes | None = None,
    options: FigureOptions | None = None,
) -> Axes:
    """Plot the road elevation on the grid given by the positions ``u`` and
    ``v`` (1D arrays) as a map, like ``crg_plot_road_uv2uvz_map``.

    Positions outside the data are evaluated with the border options of the
    data set; points that cannot be evaluated stay empty.
    """
    with _data(source) as data:
        return _road_uv2uvz_map(data, u, v, ax, _options(options))


def _road_uv2xyz_map(data: _Data, u: npt.ArrayLike, v: npt.ArrayLike, ax: Axes | None, opts: FigureOptions) -> Axes:
    uu, vv = _positions(u, "u"), _positions(v, "v")
    uu = uu[_thin(len(uu), opts.max_surface[0])]
    vv = vv[_thin(len(vv), opts.max_surface[1])]
    x, y = data.uv_to_xy(uu[:, None], vv[None, :])
    z = data.xy_to_z(x, y)  # as the MATLAB tools: the elevation at the x/y positions
    xlabel, ylabel, zlabel = data.label_x(), data.label_y(), data.label_z()

    def draw(ax: Axes) -> None:
        assert isinstance(ax, Axes3D)
        _surface(ax, x, y, z, opts, zlabel)
        ax.set_title("CRG road XYZ map (in curved XY grid)")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_zlabel(zlabel)

    return _draw(ax, draw, three_d=True)


def plot_road_uv2xyz_map(
    source: Source,
    u: npt.ArrayLike,
    v: npt.ArrayLike,
    *,
    ax: Axes | None = None,
    options: FigureOptions | None = None,
) -> Axes:
    """Plot the road surface on the grid given by ``u`` and ``v`` as a 3D
    surface over x/y, like ``crg_plot_road_uv2xyz_map``.

    As in the MATLAB tools, the elevation is evaluated at the x/y position of
    each node (``xy_to_z``), which shows where the transformation is ambiguous.
    """
    with _data(source) as data:
        return _road_uv2xyz_map(data, u, v, ax, _options(options))
