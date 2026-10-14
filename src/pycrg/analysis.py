"""Analysis of OpenCRG data sets: peak detection and comparison.

:func:`find_peaks` and :func:`compare` are the counterparts of the OpenCRG
MATLAB functions ``crg_peakfinder`` and ``crg_isequal``. They require numpy;
:func:`pycrg.plot.show_peaks` and :func:`pycrg.plot.show_isequal` show their
results.

Index ranges (``iu``, ``iv``) select cross sections (``iu``) and long sections
(``iv``) like Python slices: ``(start, stop)`` with ``start`` included and
``stop`` excluded, counted from 0. A range must contain at least two sections.
"""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, SupportsIndex, TypeAlias

from . import constants as c
from .api import ContactPoint, DataSet, RoadSurface, _require_numpy
from .header import CrgHeader

if TYPE_CHECKING:
    import numpy as np

    FloatArray = np.ndarray[Any, np.dtype[np.float64]]
    IndexArray = np.ndarray[Any, np.dtype[np.intp]]

__all__ = ["CrgComparison", "CrgPeaks", "compare", "find_peaks"]

#: what the analysis and plot functions accept as data
Source: TypeAlias = DataSet | RoadSurface
IndexRange: TypeAlias = tuple[SupportsIndex, SupportsIndex]

# maximum number of candidate points processed at once by find_peaks
_PEAK_CHUNK = 65536


def _as_dataset(source: Source) -> DataSet:
    if isinstance(source, RoadSurface):
        return source.dataset
    if isinstance(source, DataSet):
        return source
    raise TypeError(f"expected a pycrg.DataSet or pycrg.RoadSurface, not {type(source).__name__}")


def _index_range(value: IndexRange | None, count: int, name: str) -> tuple[int, int]:
    """Validate an index range ``(start, stop)`` of ``count`` sections."""
    if value is None:
        return 0, count
    try:
        start, stop = value
        start, stop = operator.index(start), operator.index(stop)
    except (TypeError, ValueError):
        raise TypeError(f"{name} must be a (start, stop) pair of integers, not {value!r}") from None
    if start < 0 or start + 2 > stop or stop > count:
        raise ValueError(f"illegal {name} index range ({start}, {stop}): need 0 <= start, start + 2 <= stop <= {count}")
    return start, stop


def _option_double(cp: ContactPoint, option_id: int, default: float) -> float:
    value = cp.option_get_double(option_id)
    return default if value is None else value


# ---------------------------------------------------------------------------
# peaks
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class CrgPeaks:
    """Peaks found by :func:`find_peaks`, ordered by cross section, then long section.

    Attributes:
        iu, iv: cross and long section index of each peak (counted from 0).
        u, v: road co-ordinates of each peak.
        z: elevation at each peak (as :meth:`ContactPoint.uv_to_z` returns it).
        search_iu, search_iv: the index ranges that were searched.
    """

    iu: IndexArray
    iv: IndexArray
    u: FloatArray
    v: FloatArray
    z: FloatArray
    search_iu: tuple[int, int]
    search_iv: tuple[int, int]

    def __len__(self) -> int:
        return len(self.iu)


def find_peaks(
    source: Source,
    iu: IndexRange | None = None,
    iv: IndexRange | None = None,
    *,
    threshold: float = 0.5,
    window: int = 3,
) -> CrgPeaks:
    """Find peaks in the road surface, like ``crg_peakfinder`` of the OpenCRG tools.

    The elevation is evaluated at the grid nodes of the selected area. A
    Laplacian edge filter marks candidate nodes whose response exceeds
    ``threshold``; around each candidate, the nodes whose absolute elevation
    exceeds twice the median of a ``(2 * window + 1)`` square window (at least
    0.1) are reported as peaks. As in the MATLAB tools, the test works on
    absolute elevations, so it suits data sets whose road surface lies near
    ``z = 0``.

    Args:
        source: a :class:`~pycrg.DataSet` or :class:`~pycrg.RoadSurface`.
        iu, iv: the index ranges to search (default: everything).
        threshold: threshold of the edge filter (MATLAB ``th``).
        window: half size of the median window (MATLAB ``ra``); should exceed
            the expected peak size.

    Raises:
        ValueError: invalid ranges or parameters, or an area smaller than
            ``2 * window + 2`` sections in either direction.
    """
    np = _require_numpy()
    dataset = _as_dataset(source)
    threshold = float(threshold)
    if not math.isfinite(threshold):
        raise ValueError(f"threshold must be finite, not {threshold!r}")
    window = operator.index(window)
    if window < 1:
        raise ValueError(f"window must be at least 1, not {window}")

    grid = dataset.grid()
    nu, nv = grid.z.shape
    u0, u1 = _index_range(iu, nu, "iu")
    v0, v1 = _index_range(iv, nv, "iv")
    minimum = 2 * window + 2
    if u1 - u0 < minimum or v1 - v0 < minimum:
        raise ValueError(
            f"the searched area must span at least 2 * window + 2 = {minimum} cross and long sections, "
            f"not {u1 - u0} x {v1 - v0}"
        )

    u = grid.u[u0:u1]
    v = grid.v[v0:v1]
    with dataset.create_contact_point() as cp:
        # rows: long sections (v), columns: cross sections (u), as in MATLAB
        z = cp.uv_to_z_many(u[None, :], v[:, None])

    candidates = _laplacian_edges(np, z, threshold)
    peaks = _median_peaks(np, z, candidates, window)
    # column-major order, as MATLAB's find: by cross section, then long section
    col, row = np.nonzero(peaks.T)
    index_u = (u0 + col).astype(np.intp)
    index_v = (v0 + row).astype(np.intp)
    return CrgPeaks(
        iu=index_u,
        iv=index_v,
        u=grid.u[index_u],
        v=grid.v[index_v],
        z=z[row, col],
        search_iu=(u0, u1),
        search_iv=(v0, v1),
    )


def _laplacian_edges(np: Any, z: Any, threshold: float) -> Any:
    """crg_peakfinder_laplacian: 10 * Laplacian (with diagonals) of |z| above the threshold."""
    a = np.abs(z)
    neighbours = (
        a[:-2, :-2] + a[:-2, 1:-1] + a[:-2, 2:] + a[1:-1, :-2] + a[1:-1, 2:] + a[2:, :-2] + a[2:, 1:-1] + a[2:, 2:]
    )
    edges = np.zeros(a.shape, dtype=bool)
    with np.errstate(invalid="ignore"):
        edges[1:-1, 1:-1] = 10.0 * (8.0 * a[1:-1, 1:-1] - neighbours) > threshold
    return edges


def _median_peaks(np: Any, z: Any, candidates: Any, window: int) -> Any:
    """crg_peakfinder_peak: mark nodes above twice the window median around each candidate."""
    rows, cols = z.shape
    r, col = np.nonzero(candidates)
    # move windows into the area exactly like the MATLAB code (which, at the
    # upper border, stops one node short of the last row and column)
    col = np.where(col > cols - window - 2, cols - window - 2, col)
    col = np.where(col < window, window, col)
    r = np.where(r > rows - window - 2, rows - window - 2, r)
    r = np.where(r < window, window, r)

    counts = np.zeros(z.shape, dtype=np.intp)
    offsets = np.arange(-window, window + 1)
    for start in range(0, len(r), _PEAK_CHUNK):
        rr = r[start : start + _PEAK_CHUNK]
        cc = col[start : start + _PEAK_CHUNK]
        patches = z[rr[:, None, None] + offsets[None, :, None], cc[:, None, None] + offsets[None, None, :]]
        with np.errstate(invalid="ignore"):
            median = np.median(patches.reshape(len(rr), -1), axis=1)
            level = np.fmax(median, 0.05)  # NaN medians give 0.05, as MATLAB's max ignores NaN
            hits = np.abs(patches) > (level + np.abs(level))[:, None, None]
        for i, dr in enumerate(offsets):
            for j, dc in enumerate(offsets):
                np.add.at(counts, (rr + dr, cc + dc), hits[:, i, j])
    return counts > 0


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class CrgComparison:
    """The result of :func:`compare`.

    Attributes:
        identical: no errors, and all elevation differences below
            ``tolerance`` (positions where either data set has no value are
            ignored).
        errors: differences of the grids and reference lines.
        warnings: differences that were not compared, such as the comment text.
        u, v: the grid of the first data set, on which both were evaluated.
        difference: absolute elevation difference ``|z_b - z_a|``, shape
            ``(len(u), len(v))``.
        relative: relative difference ``(z_b / z_a - 1) * 100`` in percent.
        tolerance: the relative tolerance used (the larger ``check_eps``).
        paths: the files of both data sets.
    """

    identical: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    u: FloatArray
    v: FloatArray
    difference: FloatArray
    relative: FloatArray
    tolerance: float
    paths: tuple[str, str] | None = None

    def __bool__(self) -> bool:
        return self.identical

    @property
    def max_difference(self) -> float:
        """The largest absolute elevation difference (NaN if there is none)."""
        np = _require_numpy()
        finite = self.difference[np.isfinite(self.difference)]
        return float(np.max(finite)) if finite.size else math.nan


def compare(a: Source, b: Source) -> CrgComparison:
    """Compare two data sets, like ``crg_isequal`` of the OpenCRG tools.

    The grid layout and the reference lines are compared within the
    tolerances of the ``check_eps`` (relative) and ``check_tol`` (absolute)
    options; the elevation of both data sets is evaluated on the grid of ``a``.

    Unlike ``crg_isequal``, ``identical`` is false whenever ``errors`` is not
    empty, for example for grids of different size.
    """
    np = _require_numpy()
    first, second = _as_dataset(a), _as_dataset(b)
    ga, gb = first.grid(), second.grid()
    errors: list[str] = []
    warnings: list[str] = []

    with first.create_contact_point() as cpa, second.create_contact_point() as cpb:
        eps = max(_option_double(cpa, c.CP_OPTION_CHECK_EPS, 1e-6), _option_double(cpb, c.CP_OPTION_CHECK_EPS, 1e-6))
        tol = max(_option_double(cpa, c.CP_OPTION_CHECK_TOL, 1e-4), _option_double(cpb, c.CP_OPTION_CHECK_TOL, 1e-4))

        def differ(x: float, y: float) -> bool:
            return bool(abs(y - x) > max(eps * abs(x + y), tol))

        nua, nva = ga.z.shape
        nub, nvb = gb.z.shape
        if nua != nub:
            errors.append("different u-dimension")
        if nva != nvb:
            errors.append("different v-dimension")
        elif np.any(np.abs(gb.v - ga.v) > np.maximum(eps * np.abs(ga.v + gb.v), tol)):
            errors.append("cross cut positions are not equal")
        uinc_a, vinc_a = first.increments()
        uinc_b, vinc_b = second.increments()
        values = (
            ("ubeg", ga.u[0], gb.u[0]),
            ("uend", ga.u[-1], gb.u[-1]),
            ("uinc", uinc_a, uinc_b),
            ("vmin", ga.v[0], gb.v[0]),
            ("vmax", ga.v[-1], gb.v[-1]),
            ("xbeg", ga.x[0], gb.x[0]),
            ("xend", ga.x[-1], gb.x[-1]),
            ("ybeg", ga.y[0], gb.y[0]),
            ("yend", ga.y[-1], gb.y[-1]),
        )
        for name, x, y in values:
            if differ(float(x), float(y)):
                errors.append(f"{name} of CRG-files are not equal")
        if vinc_a and vinc_b and differ(vinc_a, vinc_b):
            errors.append("vinc of CRG-files are not equal")
        if ga.z.shape != gb.z.shape:
            errors.append("different z-dimension")

        warnings.extend(_header_warnings(first, second))

        grid_u, grid_v = np.meshgrid(ga.u, ga.v, indexing="ij")
        za = cpa.uv_to_z_many(grid_u, grid_v)
        zb = cpb.uv_to_z_many(grid_u, grid_v)

    with np.errstate(divide="ignore", invalid="ignore"):
        difference = np.abs(za - zb)
        relative = (zb / za - 1.0) * 100.0
        within = (difference < eps) | np.isnan(difference)
    identical = not errors and bool(np.all(within))
    return CrgComparison(
        identical=identical,
        errors=tuple(errors),
        warnings=tuple(warnings),
        u=ga.u,
        v=ga.v,
        difference=difference,
        relative=relative,
        tolerance=eps,
        paths=(first.path, second.path),
    )


def _header_warnings(first: DataSet, second: DataSet) -> list[str]:
    """Report header differences that the comparison does not consider."""
    headers: list[CrgHeader] = []
    for dataset in (first, second):
        try:
            headers.append(dataset.header)
        except (OSError, ValueError) as exc:
            return [f"the header of {dataset.path!r} could not be read: {exc}"]
    ha, hb = headers
    warnings = []
    if ha.comment != hb.comment:
        warnings.append("the comment text differs (not considered)")
    if ha.options != hb.options:
        warnings.append("the $ROAD_CRG_OPTS sections differ (not considered)")
    if ha.modifiers != hb.modifiers:
        warnings.append("the $ROAD_CRG_MODS sections differ (only their effect on the data is considered)")
    return warnings
