"""Visualization of OpenCRG data sets with matplotlib (``pip install "pycrg[plot]"``).

The OpenCRG C library has no visualization; the OpenCRG MATLAB tools provide
it (chapter "Visualizing OpenCRG data" of the OpenCRG specification). This
module offers the same figures and plots, named like the MATLAB functions
without the ``crg_`` prefix:

* :func:`show` creates all figures of a data set (``crg_show``);
* ``show_*`` functions create one figure each, made of several plots
  (``crg_show_*``);
* ``plot_*`` functions draw one plot into a matplotlib ``Axes``, or into a
  new figure (``crg_plot_*``);
* :func:`surf`, :func:`figure` and :func:`copy_ax2fig` correspond to
  ``crg_surf``, ``crg_figure`` and ``copy_ax2fig``; :class:`FigureOptions`
  to ``DATA.fopt``.

Peaks and comparisons come from :func:`pycrg.find_peaks` and
:func:`pycrg.compare` (``crg_peakfinder``, ``crg_isequal``).

Index ranges ``iu`` (cross sections) and ``iv`` (long sections) are
``(start, stop)`` pairs like Python slices, counted from 0. Large grids are
thinned out for drawing (see :class:`FigureOptions`); select a range for full
detail.

The figures are created with :mod:`matplotlib.pyplot` but not displayed:
call ``matplotlib.pyplot.show()`` to display them (Jupyter displays them by
itself), or save them with ``Figure.savefig``. Double-clicking a subplot opens
it in a figure of its own. Example::

    import matplotlib.pyplot as plt
    import pycrg
    import pycrg.plot

    with pycrg.DataSet.open("road.crg") as dataset:
        pycrg.plot.show(dataset)
    plt.show()

The command ``pycrg-show road.crg`` (or ``python -m pycrg.plot road.crg``)
does the same and can write the figures to files.
"""

try:
    import matplotlib  # noqa: F401
except ModuleNotFoundError as exc:  # pragma: no cover - depends on the environment
    # a ModuleNotFoundError, as for any missing module (pytest.importorskip skips only those)
    raise ModuleNotFoundError(
        'pycrg.plot requires matplotlib; install it with: pip install "pycrg[plot]"', name=exc.name
    ) from exc

from ._core import FigureOptions, copy_ax2fig, figure, surf
from ._figures import (
    show,
    show_elgrid_cuts_and_limits,
    show_elgrid_surface,
    show_info,
    show_isequal,
    show_peaks,
    show_refline_elevation,
    show_refline_map,
    show_refpnts_and_refline,
    show_road_surface,
    show_road_uv2surface,
)
from ._plots import (
    plot_elgrid_cross_sect,
    plot_elgrid_limits,
    plot_elgrid_long_sect,
    plot_elgrid_uvz_map,
    plot_elgrid_xyz_map,
    plot_refline_curvature,
    plot_refline_elevation,
    plot_refline_heading,
    plot_refline_slope_bank,
    plot_refline_xy_map_and_curv,
    plot_refline_xy_overview_map,
    plot_refline_xyz_map,
    plot_refpnt_distances,
    plot_road_uv2uvz_map,
    plot_road_uv2xyz_map,
    plot_road_uvz_map,
    plot_road_xyz_map,
)

__all__ = [
    "FigureOptions",
    "copy_ax2fig",
    "figure",
    "surf",
    # figures
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
    # plots
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
