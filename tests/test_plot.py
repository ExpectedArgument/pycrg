"""Visualization with pycrg.plot, the counterpart of crg_show and its helpers."""

import subprocess
import sys

import pytest

import pycrg
from pycrg import DataSet, RoadSurface

plot = pytest.importorskip("pycrg.plot")  # requires matplotlib (and numpy)
np = pytest.importorskip("numpy")

from matplotlib.backend_bases import MouseEvent  # noqa: E402
from mpl_toolkits.mplot3d import Axes3D  # noqa: E402

CURVED = "handmade_curved_banked_sloped.crg"  # curved, sloped and banked, variable v spacing


def subplots(fig):
    return [ax for ax in fig.axes if ax.get_label() != "<colorbar>"]


def colorbars(fig):
    return [ax for ax in fig.axes if ax.get_label() == "<colorbar>"]


def titles(fig):
    return [ax.get_title() for ax in subplots(fig)]


def texts(fig):
    return "\n".join(text.get_text() for text in fig.texts)


def file_label(path):
    """The file name at the bottom of a figure: long names are cut to their
    last 97 characters, so that the tests pass in deep directories too."""
    text = str(path)
    return text if len(text) <= 100 else "..." + text[-97:]


def mesh_values(ax, shape):
    """The values of the 2D map of ``ax`` as a ``(nu, nv)`` array."""
    (mesh,) = ax.collections
    return np.ma.filled(mesh.get_array(), np.nan).reshape(shape[1], shape[0]).T


@pytest.fixture
def curved(crg_txt):
    return crg_txt / CURVED


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "labels"),
    [
        (
            CURVED,
            [
                "CRG reference line map",
                "CRG reference line elevation",
                "CRG elevation grid cuts and limits",
                "CRG elevation grid surface - w/o slope and banking",
                "CRG road surface",
                "CRG information",
            ],
        ),
        # straight: no reference line map; flat: no elevation figures
        ("handmade_straight.crg", ["CRG elevation grid cuts and limits", "CRG road surface", "CRG information"]),
        (
            "handmade_arc.crg",
            ["CRG reference line map", "CRG elevation grid cuts and limits", "CRG road surface", "CRG information"],
        ),
    ],
)
def test_show_figures(plt, crg_txt, name, labels):
    with DataSet.open(crg_txt / name) as dataset:
        figures = plot.show(dataset)
    assert [fig.get_label() for fig in figures] == labels
    layout = {
        "CRG reference line map": (4, 0),
        "CRG reference line elevation": (4, 1),
        "CRG elevation grid cuts and limits": (4, 0),
        "CRG elevation grid surface - w/o slope and banking": (3, 1),
        "CRG road surface": (3, 1),
        "CRG information": (0, 0),
    }
    for fig in figures:
        axes = subplots(fig)
        count, three_d = layout[fig.get_label()]
        assert len(axes) == count
        assert sum(isinstance(ax, Axes3D) for ax in axes) == three_d
        assert fig._suptitle.get_text() == fig.get_label()
        assert file_label(crg_txt / name) in texts(fig)  # file name at the bottom
        fig.canvas.draw()  # the layout can be drawn


def test_show_titles_of_the_subplots(plt, curved):
    with DataSet.open(curved) as dataset:
        figures = {fig.get_label(): fig for fig in plot.show(dataset)}
    assert titles(figures["CRG reference line map"]) == [
        "CRG reference line XY overview map",
        "CRG reference line heading",
        "CRG reference line XY map with norm. neg. curvature",
        "CRG reference line curvature",
    ]
    assert titles(figures["CRG reference line elevation"]) == [
        "CRG reference line XY overview map",
        "CRG reference line slope and banking",
        "CRG reference line XYZ map",
        "CRG reference line elevation",
    ]
    assert titles(figures["CRG elevation grid cuts and limits"]) == [
        "CRG reference line XY overview map",
        "CRG elevation grid limits",
        "CRG elevation grid cross sections - w/o slope & banking & offset",
        "CRG elevation grid long sections - w/o slope & banking & offset",
    ]
    assert titles(figures["CRG road surface"]) == [
        "CRG reference line XY overview map",
        "CRG road XYZ map (in curved XY grid)",
        "CRG road UVZ map (in uncurved UV grid)",
    ]


def test_show_windows_of_long_data(plt, write_road, numpy):
    nu = 3500
    path = write_road(z=numpy.zeros((nu, 5)), nu=nu, nv=5, du=0.1, slope=0.01, mods={})
    with RoadSurface.open(path) as road:
        figures = plot.show(road)
        u = road.grid().u
    labels = [fig.get_label() for fig in figures]
    windows = [(0, 1001), (1250, 2251), (2499, 3500)]
    expected = [f" (u = {u[a]:g} ... {u[b - 1]:g} m)" for a, b in windows]
    assert labels == [
        "CRG reference line elevation",
        "CRG elevation grid cuts and limits",
        *("CRG elevation grid surface - w/o slope and banking" + suffix for suffix in expected),
        *("CRG road surface" + suffix for suffix in expected),
        "CRG information",
    ]
    for fig, (a, b) in zip(figures[-4:-1], windows, strict=True):
        uv_map = subplots(fig)[2]
        assert uv_map.get_xlim() == pytest.approx((u[a], u[b - 1]))


def test_show_selected_ranges(plt, curved):
    with DataSet.open(curved) as dataset:
        figures = plot.show(dataset, iu=(2, 10), iv=(1, 5))
        grid = dataset.grid()
    road = next(fig for fig in figures if fig.get_label() == "CRG road surface")
    overview, _, uv_map = subplots(road)
    whole, part = overview.get_lines()[:2]
    assert whole.get_linestyle() == ":"
    assert whole.get_xdata() == pytest.approx(grid.x)
    assert part.get_xdata() == pytest.approx(grid.x[2:10])
    assert uv_map.get_xlim() == pytest.approx((grid.u[2], grid.u[9]))
    assert uv_map.get_ylim() == pytest.approx((grid.v[1], grid.v[4]))


def test_show_checks_ranges_before_drawing(plt, curved):
    with DataSet.open(curved) as dataset:
        for iu, iv in (((5, 3), None), ((0, 24), None), (None, (0, 1)), ((-1, 5), None)):
            with pytest.raises(ValueError, match="illegal"):
                plot.show(dataset, iu, iv)
        with pytest.raises(TypeError):
            plot.show(dataset, iu=(0.0, 5))
    assert plt.get_fignums() == []


def test_shortcuts(plt, curved):
    with DataSet.open(curved) as dataset:
        labels = [fig.get_label() for fig in dataset.show(iu=(0, 12))]
    with RoadSurface.open(curved) as road:
        assert [fig.get_label() for fig in road.show(iu=(0, 12))] == labels
    assert len(labels) == 6


def test_closed_data_set(plt, curved):
    dataset = DataSet.open(curved)
    dataset.close()
    with pytest.raises(pycrg.OpenCRGClosedError):
        plot.show(dataset)
    with pytest.raises(TypeError, match=r"DataSet or pycrg\.RoadSurface"):
        plot.show_road_surface(str(curved))


# ---------------------------------------------------------------------------
# reference line plots
# ---------------------------------------------------------------------------


def test_refline_plots(plt, curved):
    with DataSet.open(curved) as dataset:
        grid = dataset.grid()
        uinc = dataset.increments()[0]
        overview = plot.plot_refline_xy_overview_map(dataset)
        heading = plot.plot_refline_heading(dataset, (1, 20))
        curvature = plot.plot_refline_curvature(dataset)
        slope_bank = plot.plot_refline_slope_bank(dataset)
        elevation = plot.plot_refline_elevation(dataset)
        xyz = plot.plot_refline_xyz_map(dataset)
        with_curvature = plot.plot_refline_xy_map_and_curv(dataset)

    line, start, end = overview.get_lines()
    assert line.get_xdata() == pytest.approx(grid.x)
    assert line.get_ydata() == pytest.approx(grid.y)
    assert (start.get_marker(), end.get_marker()) == (">", "s")
    assert overview.get_aspect() == 1.0

    # MATLAB [p pend]: the heading of the following segment at each cross section
    phi = np.append(grid.phi[1:], grid.phi[-1])
    assert heading.get_lines()[0].get_xdata() == pytest.approx(grid.u[1:20])
    assert heading.get_lines()[0].get_ydata() == pytest.approx(np.degrees(phi[1:20]))
    assert heading.get_lines()[0].get_drawstyle() == "steps-post"

    dx, dy = np.diff(grid.x), np.diff(grid.y)
    rc = np.concatenate(([0.0], (dx[:-1] * dy[1:] - dy[:-1] * dx[1:]) / uinc**3, [0.0]))
    assert curvature.get_lines()[0].get_ydata() == pytest.approx(rc)
    assert curvature.get_lines()[1].get_ydata() == pytest.approx([rc.mean()] * 2)
    labels = [text.get_text() for text in curvature.get_legend().get_texts()]
    assert labels == ["curvature", f"mean = {rc.mean():.6g}", f"std = {rc.std(ddof=1):.6g}"]

    slope = np.append(grid.slope[1:], grid.slope[-1])
    assert slope_bank.get_lines()[0].get_ydata() == pytest.approx(100 * slope)
    assert slope_bank.get_lines()[1].get_ydata() == pytest.approx(100 * grid.bank)
    assert elevation.get_lines()[0].get_ydata() == pytest.approx(grid.ref_z)

    assert isinstance(xyz, Axes3D)
    z3 = xyz.get_lines()[0].get_data_3d()[2]
    assert z3 == pytest.approx(grid.ref_z)
    assert with_curvature.get_legend() is not None
    assert len(with_curvature.get_lines()) == 4


def test_plots_into_given_axes(plt, curved):
    fig = plt.figure()
    ax = fig.add_subplot(1, 2, 1)
    ax3d = fig.add_subplot(1, 2, 2, projection="3d")
    with DataSet.open(curved) as dataset:
        assert plot.plot_refline_heading(dataset, ax=ax) is ax
        assert plot.plot_road_xyz_map(dataset, ax=ax3d) is ax3d
        with pytest.raises(TypeError, match="3D axes"):
            plot.plot_refline_xyz_map(dataset, ax=ax)
        with pytest.raises(TypeError, match="matplotlib Axes"):
            plot.plot_refline_heading(dataset, ax="axes")
    assert plt.get_fignums() == [fig.number]


# ---------------------------------------------------------------------------
# elevation grid and road surface plots
# ---------------------------------------------------------------------------


def test_cross_and_long_sections(plt, straight):
    with DataSet.open(straight) as dataset:
        grid = dataset.grid()
        cross = plot.plot_elgrid_cross_sect(dataset)
        long = plot.plot_elgrid_long_sect(dataset, iv=(1, 6))
    # about ten cross sections: every ceil(23 / 9) = 3rd and the last one
    rows = [0, 3, 6, 9, 12, 15, 18, 21, 22]
    assert len(cross.get_lines()) == len(rows)
    for line, row in zip(cross.get_lines(), rows, strict=True):
        assert line.get_ydata() == pytest.approx(grid.z[row])
    assert [text.get_text() for text in cross.get_legend().get_texts()] == [f"at u = {grid.u[i]:g}" for i in rows]
    assert cross.xaxis_inverted()
    # about six long sections: every ceil(5 / 5) = 1st of the selection
    columns = [1, 2, 3, 4, 5]
    lines = [line for line in long.get_lines() if line.get_label().startswith("at v")]
    assert [line.get_label() for line in lines] == [f"at v = {grid.v[j]:g}" for j in columns]
    for line, column in zip(lines, columns, strict=True):
        assert line.get_ydata() == pytest.approx(grid.z[:, column])


def test_limits_of_valid_data(plt, write_road, numpy):
    z = numpy.zeros((30, 9))
    z[:10, :2] = numpy.nan  # right border
    z[20:, 7:] = numpy.nan  # left border
    v = numpy.linspace(-2, 2, 9)
    with DataSet.open(write_road(z=z, nu=30, nv=9, v=v, mods={})) as dataset:
        ax = plot.plot_elgrid_limits(dataset)
    left, right = ax.get_lines()[:2]
    assert left.get_ydata() == pytest.approx(np.where(np.arange(30) < 20, v[8], v[6]))
    assert right.get_ydata() == pytest.approx(np.where(np.arange(30) < 10, v[2], v[0]))


def test_maps_show_the_data(plt, curved):
    with DataSet.open(curved) as dataset:
        grid = dataset.grid()
        elgrid = plot.plot_elgrid_uvz_map(dataset)
        road = plot.plot_road_uvz_map(dataset, (3, 15), (2, 7))
        with dataset.create_contact_point() as cp:
            expected = cp.uv_to_z_many(grid.u[3:15, None], grid.v[None, 2:7])
    assert mesh_values(elgrid, grid.z.shape) == pytest.approx(grid.z)
    assert mesh_values(road, expected.shape) == pytest.approx(expected)
    assert elgrid.get_xlabel() == "U [m]"
    assert colorbars(elgrid.figure)[0].get_ylabel() == "Z [m]"


def test_surfaces(plt, curved):
    with DataSet.open(curved) as dataset:
        grid = dataset.grid()
        road = plot.plot_road_xyz_map(dataset)
        elgrid = plot.plot_elgrid_xyz_map(dataset, options=plot.FigureOptions(z_aspect=1.0))
        with dataset.create_contact_point() as cp:
            z = cp.uv_to_z_many(grid.u[:, None], grid.v[None, :])
    assert isinstance(road, Axes3D)
    assert road.get_zlim() == pytest.approx((z.min(), z.max()))
    # data aspect 1 : 1 : 0.1, as MATLAB's daspect([1 1 0.1])
    (dx, dy, dz) = (np.ptp(lim) for lim in (road.get_xlim(), road.get_ylim(), road.get_zlim()))
    box = road.get_box_aspect()
    assert box / box[0] == pytest.approx(np.array([dx, dy, dz / 0.1]) / dx, rel=1e-3)
    box = elgrid.get_box_aspect()
    zx = np.ptp(elgrid.get_zlim()) / np.ptp(elgrid.get_xlim())
    assert box[2] / box[0] == pytest.approx(zx, rel=1e-3)
    assert len(colorbars(road.figure)) == 1
    assert (road.elev, road.azim) == (30.0, -37.5)  # MATLAB's view(3)


def test_3d_ticks_fit_the_box(plt, straight):
    with DataSet.open(straight) as dataset:
        ax = plot.plot_road_xyz_map(dataset)
    ax.figure.canvas.draw()
    # the long x side gets several ticks, the flat z side none (the colour bar
    # shows z) and no label
    assert len(ax.get_xticks()) >= 3
    assert len(ax.get_zticks()) == 0
    assert not ax.zaxis.label.get_visible()
    assert ax.xaxis.labelpad > plt.rcParams["axes.labelpad"]  # off the tick labels
    ax.set_box_aspect((1, 1, 1))
    ax.figure.canvas.draw()
    assert len(ax.get_zticks()) >= 2
    assert ax.zaxis.label.get_visible()


def test_large_grids_are_thinned(plt, write_road, numpy):
    with DataSet.open(write_road(nu=300, nv=21)) as dataset:
        options = plot.FigureOptions(max_image=(50, 7), max_surface=(20, 5))
        uv_map = plot.plot_road_uvz_map(dataset, options=options)
        surface = plot.plot_road_xyz_map(dataset, options=options)
        u = dataset.grid().u
    (mesh,) = uv_map.collections
    assert mesh.get_array().size == 50 * 7
    assert uv_map.get_xlim() == pytest.approx((u[0], u[-1]))  # the ends are kept
    (polygons,) = surface.collections
    assert len(polygons.get_paths()) <= 19 * 4


def test_uv2_maps(plt, curved):
    u = np.linspace(-5.0, 30.0, 36)  # beyond the data
    v = np.linspace(-3.0, 3.0, 13)
    with DataSet.open(curved) as dataset:
        uv_map = plot.plot_road_uv2uvz_map(dataset, u, v)
        surface = plot.plot_road_uv2xyz_map(dataset, u, v)
        figure = plot.show_road_uv2surface(dataset, u, v)
        with dataset.create_contact_point() as cp:
            expected = cp.uv_to_z_many(u[:, None], v[None, :])
        for bad in ([1.0], [[1.0, 2.0]], [0.0, np.nan]):
            with pytest.raises(ValueError, match="1D array"):
                plot.plot_road_uv2uvz_map(dataset, bad, v)
    assert mesh_values(uv_map, expected.shape) == pytest.approx(expected)
    assert isinstance(surface, Axes3D)
    overview = subplots(figure)[0]
    outline = overview.get_lines()[-1]
    assert len(outline.get_xdata()) == 2 * (len(u) + len(v))


def test_reference_points(plt, curved):
    with DataSet.open(curved) as dataset:
        grid = dataset.grid()
        points = np.column_stack([grid.x, grid.y])
        figure = plot.show_refpnts_and_refline(dataset, points)
        distances = plot.plot_refpnt_distances(dataset, points.tolist())
        with pytest.raises(ValueError, match="shape"):
            plot.plot_refpnt_distances(dataset, [1.0, 2.0])
    assert len(subplots(figure)) == 6
    assert titles(figure)[0] == "CRG reference points in reference line XY overview map"
    assert distances.get_lines()[0].get_xdata() == pytest.approx(grid.u, abs=1e-6)
    assert distances.get_lines()[0].get_ydata() == pytest.approx(np.zeros(len(grid.u)), abs=1e-6)


# ---------------------------------------------------------------------------
# information, peaks, comparison
# ---------------------------------------------------------------------------


def test_info(plt, curved):
    with DataSet.open(curved) as dataset:
        text = texts(plot.show_info(dataset))
    assert "CRG elevation grid size:" in text
    assert "length                    =                   23" in text
    assert "reference_line_end_u      =                   22" in text
    assert "long_section_v_increment" not in text  # long sections at variable positions
    assert "(none pending: applied or not set)" in text
    assert "border_mode_u             =                    2" in text
    assert "crossing_ulen             =                    0" in text
    assert "CRG comment data:" in text
    assert "with curved, banked, and sloped reference line" in text


def test_info_lists_pending_modifiers(plt, write_road):
    path = write_road(mods={"refline_offset_z": 2.5, "grid_nan_mode": 1})
    with DataSet.open(path, apply_modifiers=False) as dataset:
        text = texts(plot.show_info(dataset))
    assert "refline_offset_z          =                  2.5" in text
    assert "grid_nan_mode             =                    1" in text


def test_info_cuts_long_comments(plt, write_road):
    comment = "\n".join(f"comment line {i:03d} " + "x" * 50 for i in range(600))
    with DataSet.open(write_road(comment=comment)) as dataset:
        fig = plot.show_info(dataset)
    comment_text = fig.texts[-1]
    assert comment_text.get_fontsize() == 6.0  # not smaller: cut instead
    lines = comment_text.get_text().splitlines()
    assert lines[:3] == ["CRG comment data:", "", "comment line 000 " + "x" * 50]
    assert lines[-1].startswith("... (") and lines[-1].endswith(" more lines)")
    assert len(lines) < 600


def test_show_peaks(plt, write_road, numpy):
    z = numpy.zeros((60, 21))
    z[30, 8] = 0.4
    with DataSet.open(write_road(z=z, nu=60, nv=21, mods={})) as dataset:
        grid = dataset.grid()
        peaks = pycrg.find_peaks(dataset, iu=(10, 50))
        fig = plot.show_peaks(dataset, peaks)
        indexed = plot.show_peaks(dataset, [[30, 8]], su=(10, 50), iu=(0, 60))
        empty = plot.show_peaks(dataset, numpy.zeros((0, 2), dtype=int))
        for bad in ([[30.0, 8.0]], [[60, 0]], [1, 2]):
            with pytest.raises(ValueError):
                plot.show_peaks(dataset, bad)
    assert fig.get_label() == "CRG peak visualizer"
    for figure in (fig, indexed):
        _, surface, uv_map = subplots(figure)
        markers, box = uv_map.get_lines()[-2:]
        assert markers.get_xdata() == pytest.approx([grid.u[30]])
        assert markers.get_ydata() == pytest.approx([grid.v[8]])
        assert box.get_xdata() == pytest.approx([grid.u[10], grid.u[49], grid.u[49], grid.u[10], grid.u[10]])
        assert surface.get_lines()[-1].get_data_3d()[2] == pytest.approx([0.4], rel=1e-6)
    assert subplots(empty)[2].get_lines()[-2].get_xdata().size == 0


def test_show_isequal(plt, write_road, numpy):
    z = numpy.zeros((40, 7))
    changed = z.copy()
    changed[20, 3] = 0.1
    with (
        DataSet.open(write_road("a.crg", z=z, mods={})) as a,
        DataSet.open(write_road("b.crg", z=changed, mods={})) as b,
    ):
        result = pycrg.compare(a, b)
        same = pycrg.compare(a, a)
    fig = plot.show_isequal(result)
    assert fig.get_label() == "CRG comparison"
    histogram, difference_map, absolute, relative = subplots(fig)
    assert difference_map.get_title() == "CRG absolute elevation differences"
    assert not isinstance(difference_map, Axes3D)
    status = histogram.texts[0].get_text()
    assert status.startswith("different\nmax |dz| = 0.1 m")
    assert histogram.get_yscale() == "log"  # one large difference among many zeros
    assert isinstance(absolute, Axes3D)
    assert isinstance(relative, Axes3D)
    assert "a.crg  vs.  b.crg" in texts(fig)
    assert subplots(plot.show_isequal(same))[0].texts[0].get_text().startswith("identical")
    with pytest.raises(TypeError, match="CrgComparison"):
        plot.show_isequal("result")


# ---------------------------------------------------------------------------
# options and helpers
# ---------------------------------------------------------------------------


def test_figure_options(plt, curved):
    options = plot.FigureOptions(
        orientation="portrait", title="My road", file_label="road file", date_label="today", color_period=0.01
    )
    with DataSet.open(curved) as dataset:
        fig = plot.show_road_surface(dataset, options=options)
        lit = plot.plot_road_xyz_map(dataset, options=plot.FigureOptions(light=True))
    assert tuple(fig.get_size_inches()) == pytest.approx((8.27, 11.69))
    assert fig.get_label() == "My road"
    assert "road file" in texts(fig)
    assert "today" in texts(fig)
    assert colorbars(fig)[0].get_ylabel() == "Z [m] mod 0.01"
    uv_map = subplots(fig)[2]
    assert np.nanmax(uv_map.collections[0].get_array()) < 0.01
    assert isinstance(lit, Axes3D)
    for bad in (
        {"orientation": "square"},
        {"z_aspect": 0.0},
        {"color_period": -1.0},
        {"color_period": float("nan")},
        {"max_image": (1, 10)},
        {"max_surface": (10,)},
    ):
        with pytest.raises(ValueError):
            plot.FigureOptions(**bad)
    with DataSet.open(curved) as dataset, pytest.raises(TypeError, match="FigureOptions"):
        plot.show_info(dataset, options={"title": "x"})


def test_figure_and_surf_helpers(plt, curved):
    with DataSet.open(curved) as dataset:
        fig = plot.figure(dataset, "My figure")
    assert fig.get_label() == "My figure"
    assert file_label(curved) in texts(fig)
    assert tuple(fig.get_size_inches()) == pytest.approx((11.69, 8.27))
    assert "<unknown CRG file name>" in texts(plot.figure())
    long_name = plot.figure(options=plot.FigureOptions(file_label="x" * 300))
    assert any(text.get_text() == "..." + "x" * 97 for text in long_name.texts)

    x, y = np.meshgrid(np.arange(5.0), np.arange(3.0), indexing="ij")
    ax = plot.surf(x, y, x * y)
    assert isinstance(ax, Axes3D)
    assert ax.get_zlim() == pytest.approx((0.0, 8.0))
    with pytest.raises(ValueError, match="same shape"):
        plot.surf(x, y, x[:, :2])


def test_copy_ax2fig(plt, curved):
    with DataSet.open(curved) as dataset:
        fig = plot.show_road_surface(dataset)
    _, surface, uv_map = subplots(fig)
    surface.view_init(elev=60, azim=10)
    # the data set is closed: copies redraw from the extracted data
    copy = plot.copy_ax2fig(surface)
    (copied,) = subplots(copy)
    assert copied is not surface
    assert copied.get_title() == surface.get_title()
    assert (copied.elev, copied.azim) == (60, 10)
    assert copied.get_zlim() == pytest.approx(surface.get_zlim())
    uv_copy = subplots(plot.copy_ax2fig(uv_map))[0]
    assert uv_copy.get_xlim() == pytest.approx(uv_map.get_xlim())
    other = plt.figure().add_subplot()
    with pytest.raises(ValueError, match=r"not drawn by a pycrg\.plot function"):
        plot.copy_ax2fig(other)


def test_double_click_opens_a_copy(plt, curved):
    with DataSet.open(curved) as dataset:
        fig = plot.show_refline_map(dataset)
    heading = subplots(fig)[1]
    count = len(plt.get_fignums())
    fig.canvas.draw()
    x, y = heading.transAxes.transform((0.5, 0.5))
    single = MouseEvent("button_press_event", fig.canvas, x, y, button=1)
    fig.canvas.callbacks.process("button_press_event", single)
    assert len(plt.get_fignums()) == count
    double = MouseEvent("button_press_event", fig.canvas, x, y, button=1, dblclick=True)
    fig.canvas.callbacks.process("button_press_event", double)
    assert len(plt.get_fignums()) == count + 1
    copy = plt.figure(plt.get_fignums()[-1])
    assert titles(copy) == ["CRG reference line heading"]


def test_import_does_not_need_matplotlib():
    code = "import sys, pycrg; assert 'matplotlib' not in sys.modules, 'matplotlib imported'"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_plot_without_matplotlib(monkeypatch, curved):
    for name in [name for name in sys.modules if name == "pycrg.plot" or name.startswith("pycrg.plot.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    with pytest.raises(ModuleNotFoundError, match='pip install "pycrg\\[plot\\]"') as excinfo:
        import pycrg.plot  # noqa: F401
    assert excinfo.value.name == "matplotlib"
    with DataSet.open(curved) as dataset, pytest.raises(ModuleNotFoundError, match="matplotlib"):
        dataset.show()
