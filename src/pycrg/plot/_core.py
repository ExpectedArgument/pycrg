"""Common parts of :mod:`pycrg.plot`: data extraction, figure frame, surfaces."""

from __future__ import annotations

import datetime
import warnings
import weakref
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
from matplotlib import colormaps, rcParams
from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.layout_engine import ConstrainedLayoutEngine
from matplotlib.ticker import MaxNLocator
from mpl_toolkits.mplot3d import Axes3D, proj3d

from .. import constants as c
from ..analysis import IndexRange, Source, _as_dataset, _index_range
from ..api import ContactPoint, DataSet
from ..header import CrgHeader

if TYPE_CHECKING:
    import numpy.typing as npt

    FloatArray = np.ndarray[Any, np.dtype[np.float64]]
    Draw = Callable[[Axes], None]

#: A4 paper proportions, as the OpenCRG MATLAB figures
_LANDSCAPE = (11.69, 8.27)
_PORTRAIT = (8.27, 11.69)
#: longest file name shown at the bottom of a figure
_MAX_LABEL = 100
#: MATLAB's default 3D view
_VIEW_3D = {"elev": 30.0, "azim": -37.5}
_COLORMAP = "viridis"
#: matplotlib's default box of 3D axes (x : y : z), normalized
_DEFAULT_BOX = np.array([4.0, 4.0, 3.0]) / np.linalg.norm([4.0, 4.0, 3.0])
#: offsets of the tick and axis labels of 3D axes in mplot3d (Axis3D), in
#: units of its label pads
_TICK_LABEL_OFFSET = 8.0
_AXIS_LABEL_OFFSET = 21.0
#: additional space between the tick labels and the axis label of the x and
#: y axes of 3D axes, whose labels mplot3d moves sideways on flat boxes
_AXIS_LABEL_GAP = 4.0


@dataclass(frozen=True)
class FigureOptions:
    """Options of the figures, like ``DATA.fopt`` of the OpenCRG MATLAB tools.

    Attributes:
        orientation: ``"landscape"`` (default) or ``"portrait"`` (``ori``).
        title: replaces the figure titles (``tit``).
        file_label: text at the bottom left (``fnm``); default: the file name.
        date_label: text at the bottom right (``dat``); default: the current time.
        color_period: colour 3D surfaces by ``z`` modulo this period, to show
            small undulations on large slopes; 0 (default) colours by ``z``
            (``mod``).
        z_aspect: aspect of the z axis in 3D plots: 0.1 (default) magnifies
            z by 10 (``asp``).
        light: shade 3D surfaces with a light source (``lit``).
        max_surface: largest number of ``(u, v)`` nodes drawn in 3D surfaces;
            larger grids are thinned out evenly.
        max_image: largest number of ``(u, v)`` nodes drawn in 2D maps.
    """

    orientation: Literal["landscape", "portrait"] = "landscape"
    title: str | None = None
    file_label: str | None = None
    date_label: str | None = None
    color_period: float = 0.0
    z_aspect: float = 0.1
    light: bool = False
    max_surface: tuple[int, int] = (300, 80)
    max_image: tuple[int, int] = (2000, 500)

    def __post_init__(self) -> None:
        if self.orientation not in ("landscape", "portrait"):
            raise ValueError(f"orientation must be 'landscape' or 'portrait', not {self.orientation!r}")
        if not np.isfinite(self.color_period) or self.color_period < 0:
            raise ValueError(f"color_period must be a finite number >= 0, not {self.color_period!r}")
        if not np.isfinite(self.z_aspect) or self.z_aspect <= 0:
            raise ValueError(f"z_aspect must be a finite number > 0, not {self.z_aspect!r}")
        for name in ("max_surface", "max_image"):
            value = getattr(self, name)
            if len(value) != 2 or min(value) < 2:
                raise ValueError(f"{name} must be two numbers >= 2, not {value!r}")


_DEFAULT_OPTIONS = FigureOptions()


def _options(options: FigureOptions | None) -> FigureOptions:
    if options is None:
        return _DEFAULT_OPTIONS
    if not isinstance(options, FigureOptions):
        raise TypeError(f"options must be a pycrg.plot.FigureOptions, not {type(options).__name__}")
    return options


def _pyplot() -> Any:
    # imported on use, so that the command line tool can choose the backend first
    import matplotlib.pyplot as plt

    return plt


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------


class _Data:
    """The arrays of a data set used for plotting, extracted once.

    The names follow the derived data of the MATLAB tools (``rx``, ``rc``,
    ``il``, ...). A contact point for evaluations is created on first use and
    deleted by :meth:`close`.
    """

    def __init__(self, dataset: DataSet) -> None:
        self.dataset = dataset
        grid = dataset.grid()
        self.u: FloatArray = grid.u
        self.v: FloatArray = grid.v
        self.z: FloatArray = grid.z  # relative to the reference line, may hold NaN
        self.rx: FloatArray = grid.x
        self.ry: FloatArray = grid.y
        self.rz: FloatArray = grid.ref_z
        self.bank: FloatArray = grid.bank
        self.phi: FloatArray = grid.phi
        self.slope: FloatArray = grid.slope
        self.nu, self.nv = self.z.shape
        self.uinc, self.vinc = dataset.increments()
        self.path = dataset.path
        self._cp: ContactPoint | None = None

    def close(self) -> None:
        if self._cp is not None:
            self._cp.close()
            self._cp = None

    @property
    def cp(self) -> ContactPoint:
        if self._cp is None:
            self._cp = self.dataset.create_contact_point()
        return self._cp

    @cached_property
    def header(self) -> CrgHeader | None:
        try:
            return self.dataset.header
        except (OSError, ValueError):
            return None

    def _road(self, key: str) -> float:
        if self.header is None:
            return 0.0
        value = self.header.road.get(key, 0.0)
        return float(value) if isinstance(value, (int, float)) else 0.0

    @cached_property
    def xoff(self) -> float:
        return self._road("reference_line_offset_x")

    @cached_property
    def yoff(self) -> float:
        return self._road("reference_line_offset_y")

    @cached_property
    def zoff(self) -> float:
        return self._road("reference_line_offset_z")

    @cached_property
    def poff(self) -> float:
        return self._road("reference_line_offset_phi")

    @cached_property
    def heading(self) -> FloatArray:
        """Heading at each cross section: the heading of the following segment
        and, at the end, the end heading (MATLAB ``[p pend]``)."""
        return np.append(self.phi[1:], self.phi[-1])

    @cached_property
    def slope_steps(self) -> FloatArray:
        """Slope at each cross section, like :attr:`heading` (MATLAB ``[s send]``)."""
        return np.append(self.slope[1:], self.slope[-1])

    @cached_property
    def curvature(self) -> FloatArray:
        """Curvature at each cross section, 0 at both ends (MATLAB ``[0 rc 0]``)."""
        dx = np.diff(self.rx)
        dy = np.diff(self.ry)
        rc = (dx[:-1] * dy[1:] - dy[:-1] * dx[1:]) / self.uinc**3
        return np.concatenate(([0.0], rc, [0.0]))

    @cached_property
    def curved(self) -> bool:
        """Whether the heading varies (MATLAB: ``isfield(data, 'rx')``)."""
        return bool(np.ptp(self.phi) > 0.0)

    @cached_property
    def elevated(self) -> bool:
        """Whether the reference line has slope or banking (MATLAB: ``rz`` or ``b``)."""
        return bool(np.any(self.slope != 0.0) or np.any(self.bank != 0.0))

    @cached_property
    def limits(self) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.intp]]:
        """Indices of the leftmost and rightmost valid value of each cross
        section (MATLAB ``il``, ``ir``); -1 for cross sections without values."""
        valid = ~np.isnan(self.z)
        any_valid = valid.any(axis=1)
        left = np.where(any_valid, self.nv - 1 - np.argmax(valid[:, ::-1], axis=1), -1)
        right = np.where(any_valid, np.argmax(valid, axis=1), -1)
        return left.astype(np.intp), right.astype(np.intp)

    @cached_property
    def check_eps(self) -> float:
        value = self.cp.option_get_double(c.CP_OPTION_CHECK_EPS)
        return 1e-6 if value is None else value

    def range_u(self, iu: IndexRange | None) -> tuple[int, int]:
        return _index_range(iu, self.nu, "iu")

    def range_v(self, iv: IndexRange | None) -> tuple[int, int]:
        return _index_range(iv, self.nv, "iv")

    def uv_to_xy(self, u: npt.ArrayLike, v: npt.ArrayLike) -> tuple[FloatArray, FloatArray]:
        return self.cp.uv_to_xy_many(u, v)

    def uv_to_z(self, u: npt.ArrayLike, v: npt.ArrayLike) -> FloatArray:
        return self.cp.uv_to_z_many(u, v)

    def xy_to_z(self, x: npt.ArrayLike, y: npt.ArrayLike) -> FloatArray:
        return self.cp.xy_to_z_many(x, y)

    def xy_to_uv(self, x: npt.ArrayLike, y: npt.ArrayLike) -> tuple[FloatArray, FloatArray]:
        return self.cp.xy_to_uv_many(x, y)

    # axis labels with the reference line offsets, as the MATLAB tools
    def label_x(self) -> str:
        return "X [m]" if self.xoff == 0 or self.poff != 0 else f"X [m] ({self.xoff:+g}m)"

    def label_y(self) -> str:
        return "Y [m]" if self.yoff == 0 or self.poff != 0 else f"Y [m] ({self.yoff:+g}m)"

    def label_z(self) -> str:
        return "Z [m]" if self.zoff == 0 else f"Z [m] ({self.zoff:+g}m)"

    def label_heading(self) -> str:
        return "heading [deg]" if self.poff == 0 else f"heading [deg] ({np.degrees(self.poff):+g}deg)"


@contextmanager
def _data(source: Source | _Data) -> Iterator[_Data]:
    """The plot data of ``source``; reuses ``source`` if it is plot data already."""
    if isinstance(source, _Data):
        yield source
        return
    data = _Data(_as_dataset(source))
    try:
        yield data
    finally:
        data.close()


def _thin(count: int, maximum: int) -> npt.NDArray[np.intp]:
    """Indices of at most ``maximum`` evenly spread items, including the last."""
    if count <= maximum:
        return np.arange(count)
    return np.unique(np.linspace(0, count - 1, maximum).round().astype(np.intp))


# ---------------------------------------------------------------------------
# figures and axes
# ---------------------------------------------------------------------------

# the drawing function of each axes drawn by pycrg.plot, for copy_ax2fig
_DRAWINGS: weakref.WeakKeyDictionary[Axes, Draw] = weakref.WeakKeyDictionary()


def figure(source: Source | None = None, title: str = "CRG figure", *, options: FigureOptions | None = None) -> Figure:
    """Create an empty OpenCRG figure, like ``crg_figure`` of the OpenCRG tools.

    The figure has A4 proportions and shows ``title`` at the top, the file
    name of ``source`` at the bottom left and the date at the bottom right
    (see :class:`FigureOptions`). It is created with :mod:`matplotlib.pyplot`,
    so that ``matplotlib.pyplot.show()`` displays it. Double-clicking a
    subplot drawn by :mod:`pycrg.plot` opens it in a figure of its own
    (:func:`copy_ax2fig`).
    """
    return _frame(None if source is None else _as_dataset(source).path, title, _options(options))


def _frame(path: str | None, title: str, opts: FigureOptions) -> Figure:
    if opts.title is not None:
        title = opts.title
    if opts.file_label is not None:
        file_label = opts.file_label
    elif path is not None:
        file_label = path
    else:
        file_label = "<unknown CRG file name>"
    if len(file_label) > _MAX_LABEL:  # keep clear of the date
        file_label = "..." + file_label[3 - _MAX_LABEL :]
    if opts.date_label is not None:
        date_label = opts.date_label
    else:
        date_label = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fig: Figure = _pyplot().figure(
        figsize=_LANDSCAPE if opts.orientation == "landscape" else _PORTRAIT, layout="constrained"
    )
    engine = fig.get_layout_engine()
    if isinstance(engine, ConstrainedLayoutEngine):  # keep the frame texts clear of the subplots
        engine.set(rect=(0.0, 0.035, 1.0, 0.965))
    fig.suptitle(title)
    fig.text(0.005, 0.005, file_label, ha="left", va="bottom", fontsize="small")
    fig.text(0.995, 0.005, date_label, ha="right", va="bottom", fontsize="small")
    fig.set_label(title)
    manager = fig.canvas.manager
    if manager is not None:
        manager.set_window_title(title)
    fig.canvas.mpl_connect("button_press_event", _on_button_press)
    return fig


def _new_axes(projection: str | None = None) -> Axes:
    fig = _pyplot().figure(layout="constrained")
    fig.canvas.mpl_connect("button_press_event", _on_button_press)
    ax: Axes = fig.add_subplot(projection=projection)
    return ax


def _target(ax: Axes | None, three_d: bool) -> Axes:
    if ax is None:
        return _new_axes("3d" if three_d else None)
    if not isinstance(ax, Axes):
        raise TypeError(f"ax must be a matplotlib Axes, not {type(ax).__name__}")
    if three_d and not isinstance(ax, Axes3D):
        raise TypeError("this plot needs a 3D axes, for example fig.add_subplot(projection='3d')")
    return ax


def _draw(ax: Axes | None, draw: Draw, *, three_d: bool = False) -> Axes:
    """Run ``draw`` on ``ax`` (or a new figure) and remember it for copy_ax2fig."""
    target = _target(ax, three_d)
    draw(target)
    _DRAWINGS[target] = draw
    return target


def _overlay(ax: Axes, extra: Draw) -> Axes:
    """Draw ``extra`` on top of the plot of ``ax``, also in copies of it."""
    base = _DRAWINGS.get(ax)
    extra(ax)
    if base is not None:

        def draw(target: Axes) -> None:
            base(target)
            extra(target)

        _DRAWINGS[ax] = draw
    return ax


def copy_ax2fig(ax: Axes) -> Figure:
    """Draw the plot of ``ax`` again in a figure of its own, like ``copy_ax2fig``.

    ``ax`` must have been drawn by a :mod:`pycrg.plot` function. The data set
    need not be open any more. The current view (limits and 3D angles) is
    kept. In interactive figures, double-clicking a subplot does the same.
    """
    draw = _DRAWINGS.get(ax)
    if draw is None:
        raise ValueError("ax was not drawn by a pycrg.plot function")
    three_d = isinstance(ax, Axes3D)
    target = _new_axes("3d" if three_d else None)
    draw(target)
    _DRAWINGS[target] = draw
    target.set_xlim(ax.get_xlim())
    target.set_ylim(ax.get_ylim())
    if three_d and isinstance(target, Axes3D) and isinstance(ax, Axes3D):
        target.set_zlim(ax.get_zlim())
        target.view_init(elev=ax.elev, azim=ax.azim)
    return target.figure  # type: ignore[return-value]


def _on_button_press(event: Any) -> None:
    ax = getattr(event, "inaxes", None)
    if getattr(event, "dblclick", False) and ax is not None and ax in _DRAWINGS:
        fig = copy_ax2fig(ax)
        with warnings.catch_warnings():  # non-interactive backends cannot show it
            warnings.simplefilter("ignore", UserWarning)
            fig.show()


# ---------------------------------------------------------------------------
# surfaces and maps
# ---------------------------------------------------------------------------


def _color_values(z: FloatArray, period: float) -> FloatArray:
    if period > 0:
        result: FloatArray = np.mod(z, period)
        return result
    return z


def _norm(values: FloatArray) -> Normalize:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return Normalize(0.0, 1.0)
    low, high = float(np.min(finite)), float(np.max(finite))
    if low == high:
        low, high = low - 0.5, high + 0.5
    return Normalize(low, high)


def _limits(values: FloatArray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 1.0
    low, high = float(np.min(finite)), float(np.max(finite))
    if low == high:
        pad = max(abs(low) * 1e-6, 1e-3)
        low, high = low - pad, high + pad
    return low, high


def _projected_length(ax: Axes3D, index: int) -> float:
    """The length on screen, in points, of the side ``index`` (0: x, 1: y,
    2: z) of the box of ``ax`` as last drawn."""
    limits = (ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d())
    start = [low for low, _ in limits]
    end = list(start)
    end[index] = limits[index][1]
    xs, ys, _ = proj3d.proj_transform(*np.array([start, end]).T, ax.M)
    (x0, y0), (x1, y1) = ax.transData.transform(np.column_stack([xs, ys]))
    return float(np.hypot(x1 - x0, y1 - y0) * 72.0 / ax.figure.dpi)


class _ProjectedLocator(MaxNLocator):
    """Ticks of a 3D axis, as many as fit its length on screen.

    matplotlib places as many ticks on each side of a 3D box as fit the whole
    axes; on the short sides of the flat, long boxes of roads, the tick labels
    overlap. This locator allows a tick interval per three label heights of
    the side as drawn, like a 2D x axis, and no ticks and no axis label on
    shorter sides (the colour bar shows the values of flat surfaces).
    """

    def __init__(self, index: int) -> None:
        super().__init__(nbins="auto", steps=[1, 2, 2.5, 5, 10])
        self._index = index
        self._hid_label = False

    def __call__(self) -> Sequence[float]:
        axis = self.axis
        ax = getattr(axis, "axes", None)
        if not isinstance(axis, Axis) or not isinstance(ax, Axes3D) or getattr(ax, "M", None) is None:
            return super().__call__()  # not drawn yet
        size = rcParams["xtick.labelsize"] if self._index == 0 else rcParams["ytick.labelsize"]  # no ztick.*
        spacing = 3.0 * FontProperties(size=size).get_size_in_points()
        bins = int(_projected_length(ax, self._index) // spacing)
        if bins < 1:
            if axis.label.get_visible():
                axis.label.set_visible(False)
                self._hid_label = True
            return []
        if self._hid_label:
            axis.label.set_visible(True)
            self._hid_label = False
        self.set_params(nbins=bins)
        return super().__call__()


def _set_3d_label_offsets(ax: Axes3D, sides: Sequence[float]) -> None:
    """mplot3d moves the tick and axis labels of a side away from the box
    along the two other sides, by distances proportional to their length: on
    the flat, long boxes of roads, the labels of the long sides end up on top
    of each other. Scale the distances back to those of the default box."""
    normalized = np.asarray(sides, dtype=np.float64) / np.linalg.norm(sides)
    for index, axis in enumerate((ax.xaxis, ax.yaxis, ax.zaxis)):
        others = [i for i in range(3) if i != index]
        scale = float(np.clip(normalized[others].sum() / _DEFAULT_BOX[others].sum(), 0.1, 1.0))
        name = "xyz"[index]
        label_pad = _AXIS_LABEL_OFFSET + rcParams["axes.labelpad"] + (_AXIS_LABEL_GAP if name != "z" else 0.0)
        axis.labelpad = label_pad / scale - _AXIS_LABEL_OFFSET
        tick_pad = _TICK_LABEL_OFFSET + rcParams["xtick.major.pad" if name == "x" else "ytick.major.pad"]
        ax.tick_params(axis=name, pad=tick_pad / scale - _TICK_LABEL_OFFSET)


def _set_3d_aspect(ax: Axes3D, x: FloatArray, y: FloatArray, z: FloatArray, z_aspect: float | None) -> None:
    """Tight limits and a data aspect of 1 : 1 : z_aspect, as MATLAB's
    ``axis tight`` and ``daspect([1 1 asp])``, and MATLAB's default view;
    with ``z_aspect=None``, the default box of matplotlib (for values that
    are no elevations)."""
    xl, yl, zl = _limits(x), _limits(y), _limits(z)
    ax.set_xlim(xl)
    ax.set_ylim(yl)
    ax.set_zlim(zl)
    ax.view_init(**_VIEW_3D)
    if z_aspect is None:
        return
    dx, dy, dz = xl[1] - xl[0], yl[1] - yl[0], (zl[1] - zl[0]) / z_aspect
    largest = max(dx, dy, dz)
    # very flat boxes cannot be drawn; keep each side at least 1/1000 of the longest
    sides = (max(dx, largest / 1000), max(dy, largest / 1000), max(dz, largest / 1000))
    ax.set_box_aspect(sides)
    for index, axis in enumerate((ax.xaxis, ax.yaxis, ax.zaxis)):
        axis.set_major_locator(_ProjectedLocator(index))
    _set_3d_label_offsets(ax, sides)


def _surface(
    ax: Axes3D,
    x: FloatArray,
    y: FloatArray,
    z: FloatArray,
    opts: FigureOptions,
    label: str | None = None,
    *,
    elevation: bool = True,
) -> None:
    """Draw a coloured surface with a colour bar, like ``crg_surf``; for
    values that are no elevations (``elevation=False``), the z axis is scaled
    automatically, like a plain MATLAB ``surf``."""
    values = _color_values(z, opts.color_period)
    norm = _norm(values)
    cmap = colormaps[_COLORMAP]
    colors = cmap(norm(np.ma.masked_invalid(values)))
    rows, cols = z.shape
    ax.plot_surface(
        x,
        y,
        z,
        facecolors=colors,
        rcount=rows,
        ccount=cols,
        linewidth=0,
        antialiased=False,
        shade=opts.light,
    )
    mappable = ScalarMappable(norm=norm, cmap=cmap)
    # the layout leaves no room for the z axis label of 3D axes
    colorbar = ax.figure.colorbar(mappable, ax=ax, shrink=0.7, pad=0.15)
    if label is not None:
        colorbar.set_label(label if opts.color_period == 0 else f"{label} mod {opts.color_period:g}")
    _set_3d_aspect(ax, x, y, z, opts.z_aspect if elevation else None)
    ax.grid(True)


def _image(ax: Axes, u: FloatArray, v: FloatArray, z: FloatArray, opts: FigureOptions, label: str) -> None:
    """Draw ``z`` (shape ``(len(u), len(v))``) as a map over u and v, like a
    MATLAB surface seen from above (``view(2)``)."""
    values = _color_values(z, opts.color_period)
    norm = _norm(values)
    # smooth colours like MATLAB's 'shading interp'; cells next to NaN stay empty
    mesh = ax.pcolormesh(
        u,
        v,
        np.ma.masked_invalid(values.T),
        shading="gouraud" if np.isfinite(values).all() else "nearest",
        cmap=_COLORMAP,
        norm=norm,
        rasterized=True,
    )
    colorbar = ax.figure.colorbar(mesh, ax=ax)
    colorbar.set_label(label if opts.color_period == 0 else f"{label} mod {opts.color_period:g}")
    ax.set_xlim(u[0], u[-1])
    ax.set_ylim(min(v[0], v[-1]), max(v[0], v[-1]))
    ax.set_xlabel("U [m]")
    ax.set_ylabel("V [m]")


def surf(
    x: npt.ArrayLike,
    y: npt.ArrayLike,
    z: npt.ArrayLike,
    *,
    ax: Axes | None = None,
    options: FigureOptions | None = None,
) -> Axes3D:
    """Plot a 3D surface the way the OpenCRG figures do, like ``crg_surf``.

    ``x``, ``y`` and ``z`` are 2D arrays of the same shape. The surface is
    coloured by ``z`` (or ``z`` modulo ``options.color_period``) and gets a
    colour bar; the z axis is scaled by ``options.z_aspect``.
    """
    opts = _options(options)
    xa, ya, za = (np.asarray(value, dtype=np.float64) for value in (x, y, z))
    if xa.ndim != 2 or xa.shape != ya.shape or xa.shape != za.shape:
        raise ValueError("x, y and z must be 2D arrays of the same shape")

    def draw(target: Axes) -> None:
        assert isinstance(target, Axes3D)
        _surface(target, xa, ya, za, opts)

    result = _draw(ax, draw, three_d=True)
    assert isinstance(result, Axes3D)
    return result
