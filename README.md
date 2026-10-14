# pycrg

Unofficial Python bindings for the [ASAM OpenCRG](https://www.asam.net/standards/detail/opencrg/)
C API: load, check and evaluate OpenCRG road surfaces, read their headers and grids, write CRG
files, and draw the figures of the OpenCRG MATLAB tools.

```python
import pycrg

with pycrg.RoadSurface.open("road.crg") as road:   # load and apply the file's modifiers
    z = road.uv_to_z(10.0, 0.5)                    # elevation 10 m along, 0.5 m left
    x, y = road.uv_to_xy(10.0, 0.5)                # the same point in x/y
```

- `DataSet`, `ContactPoint` and `RoadSurface` cover the OpenCRG C API: loading, consistency
  checks, modifiers, contact point options, all evaluations and transforms.
- Vectorised evaluation with numpy (`uv_to_z_many` etc.), the data set arrays (`grid()`) and the
  file header (`read_header()`).
- `write()` creates CRG files in all four OpenCRG data formats.
- `pycrg.plot` draws the figures of the OpenCRG MATLAB tools (`crg_show` and its `crg_show_*` and
  `crg_plot_*` functions) with matplotlib; `pycrg-show road.crg` does so from the command line.
  `find_peaks()` and `compare()` port `crg_peakfinder` and `crg_isequal`.
- OpenCRG messages go to Python `logging`; failures raise exceptions that carry OpenCRG's reasons.
- Bundles OpenCRG 2.0.1 with later upstream fixes and a few patches of its own (see
  [Bundled OpenCRG library](#bundled-opencrg-library)).

## Installation

```bash
pip install pycrg            # evaluation only
pip install "pycrg[numpy]"   # with grid access, vectorised evaluation, writing, peaks, comparisons
pip install "pycrg[plot]"    # and the figures (numpy and matplotlib)
```

Wheels are available for CPython 3.10–3.14 on Linux (x86_64, i686, aarch64), Windows (x64, x86)
and macOS (arm64, x86_64); the 32-bit x86 wheels need a processor with SSE2. Other platforms build
from the source distribution with a C compiler. matplotlib publishes no wheels for 32-bit x86, so
`pycrg[plot]` builds it from source there.

## Loading a file

`DataSet.open(path, *, apply_modifiers=True, check=False)` follows the sequence of the OpenCRG
tools: load the file, optionally check it, then apply its modifiers.

- **Modifiers** re-position, scale or repair the data (for example `GRID_NAN_MODE`). They are
  defined in the file's `$ROAD_CRG_MODS` section. A file without that section gets OpenCRG's
  *default* modifiers, which move the start of the reference line to `x = y = z = 0` with heading 0
  and replace NaN values at the road borders by the last valid value. An empty `$ROAD_CRG_MODS`
  section keeps the data where it is.
  Pass `apply_modifiers=False` to get the data exactly as stored, for example to set modifiers of
  your own before calling `modifiers_apply()`.
- `check=True` runs the OpenCRG consistency check first and raises `OpenCRGCheckError` if it fails.

`path` may be a `str`, `bytes` or `os.PathLike`, including non-ASCII names on Windows.

```python
from pycrg import DataSet, MOD_REF_LINE_OFFSET_Z, BORDER_MODE_NONE, CP_OPTION_BORDER_MODE_U

with DataSet.open("road.crg", check=True) as dataset:
    print(dataset.u_range(), dataset.v_range(), dataset.increments())
    cp = dataset.create_contact_point()
    cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_NONE)  # no values beyond the data
    z = cp.try_uv_to_z(-5.0, 0.0)                                 # None: outside the data

with DataSet.open("road.crg", apply_modifiers=False) as dataset:  # the raw data
    dataset.modifier_remove_all()
    dataset.modifier_set_double(MOD_REF_LINE_OFFSET_Z, 10.0)
    dataset.modifiers_apply()                                     # applied once, then removed
```

## API overview

### Data sets — `DataSet`

| Member | Purpose |
|---|---|
| `DataSet.open(path, *, apply_modifiers=True, check=False)` | load a file (see above) |
| `close()`, `closed`, `with ...` | release the data set and its contact points |
| `check(*, raise_on_error=False)` | OpenCRG consistency check; `True` if valid |
| `u_range()`, `v_range()`, `increments()` | extent and grid spacing (v increment 0: long sections at variable spacing) |
| `closed_track_data()` | `(ok, is_closed, u_min, u_max)` of a closed track (NaN if not closed) |
| `header`, `path` | the parsed file header (`CrgHeader`), the file name |
| `grid()` | numpy arrays of the data: `u`, `v`, `z`, `x`, `y`, `phi`, `slope`, `bank`, `ref_z`, `elevation` |
| `show(iu=None, iv=None, *, options=None)` | the figures of `crg_show` (see [Visualization](#visualization)) |
| `modifier_set_int/_double(id, value)`, `modifier_get_int/_double(id)` | modifiers (`MOD_*`) |
| `modifier_remove(id)`, `modifier_remove_all()`, `modifier_set_default()` | |
| `modifiers_apply()` | check, apply and remove the current modifiers |
| `option_set_default()` | reset the options new contact points start with |
| `create_contact_point()` | a `ContactPoint` for evaluations |
| `format_header()`, `format_channel_info()`, `format_road_info()`, `format_modifiers()` | OpenCRG's summaries as text |
| `print_header()`, `print_channel_info()`, `print_road_info()`, `modifiers_print()` | ... printed to `sys.stdout` (or `file=`) |

### Evaluation — `ContactPoint`

A contact point holds evaluation options and a search history; create one per thread or per
independent query sequence.

| Member | Purpose |
|---|---|
| `uv_to_z(u, v)`, `xy_to_z(x, y)` | elevation |
| `uv_to_xy(u, v)`, `xy_to_uv(x, y)` | transforms between road (u/v) and world (x/y) co-ordinates |
| `uv_to_pk(u, v)`, `xy_to_pk(x, y)` | heading and curvature of the reference line |
| `try_*` variants | return `None` instead of raising `OpenCRGEvaluationError` |
| `*_many(a, b)` variants | numpy arrays in, arrays out (broadcasting); failed points are NaN |
| `option_set_int/_double(id, value)`, `option_get_int/_double(id)` | options (`CP_OPTION_*`) |
| `option_remove(id)`, `option_remove_all()`, `set_default_options()`, `set_history(size)` | |
| `format_options()`, `options_print()` | the current options |
| `close()`, `closed`, `dataset` | |

Evaluating a position outside the data depends on the border mode options
(`CP_OPTION_BORDER_MODE_U/V`: `BORDER_MODE_NONE`, `_EX_ZERO`, `_EX_KEEP` (default), `_REPEAT`,
`_REFLECT`). Non-finite co-ordinates are refused.

### `RoadSurface`

`RoadSurface.open(path, *, apply_modifiers=True, check=False)` creates a data set and one contact
point, available as `.dataset` and `.contact_point`. It offers the evaluation, option, modifier,
check, grid, `show()` and text methods of both, and `close()` closes both. `RoadSurface(dataset)`
wraps a data set you already have.

### Handles and lifetime

Each `DataSet` and `ContactPoint` owns its native OpenCRG object. They compare by identity and cannot
be copied or pickled. Closing a data set closes its contact points; closing twice, or in any order,
is fine. `pycrg.mem_release()` releases everything OpenCRG holds and closes all handles. A data set
that is garbage collected without `close()` is released with a `ResourceWarning` (like a file) — use
`with` blocks.

### Header, grid and writing

```python
header = pycrg.read_header("road.crg")   # without loading the data
header.data_format                        # "KRBI", "LRFI", ...
header.road["reference_line_start_x"]     # $ROAD_CRG entries
header.modifiers                          # None: no $ROAD_CRG_MODS section, {}: an empty one
header.comment, header.channels, header.file_reference

with pycrg.DataSet.open("road.crg") as dataset:
    grid = dataset.grid()                 # numpy arrays as used for evaluation
    grid.z.shape                          # (cross sections, long sections)
```

`pycrg.write(path, z, du, v, phi=None, *, u0, x0, y0, z0, end_xy, slope, banking, fmt, comment,
opts, mods, road)` writes a CRG file: `z` is the elevation grid relative to the reference line
(shape `(nu, nv)`, NaN allowed only at the left and right borders), `du` the spacing of the cross
sections, `v` the lateral positions of the long sections and `phi` the heading of each of the
`nu - 1` segments of the reference line (a number for a straight line). `fmt` is `"KRBI"`
(default), `"KDBI"`, `"LRFI"` or `"LDFI"`. Pass `mods={}` to write an empty modifier section, so that
readers keep the data where it is instead of applying OpenCRG's default re-positioning. The writer
follows the reference writer of the OpenCRG MATLAB tools and checks the rules the C loader relies on.

```python
import numpy as np
import pycrg

v = np.linspace(-2.0, 2.0, 41)                     # 4 m wide, a long section every 10 cm
z = np.zeros((2001, v.size))                       # 100 m with a cross section every 5 cm
headings = np.full(2000, 0.3)                      # a straight line heading 0.3 rad
pycrg.write("road.crg", z, 0.05, v, headings, x0=500.0, y0=200.0, mods={})
```

For a reference line given as points `x`, `y` spaced `du` apart, the headings are
`np.arctan2(np.diff(y), np.diff(x))`.

### Peaks and comparisons

```python
with pycrg.DataSet.open("road.crg") as dataset:
    peaks = pycrg.find_peaks(dataset)    # crg_peakfinder
    peaks.u, peaks.v, peaks.z            # position and elevation of each peak
    peaks.iu, peaks.iv                   # their grid indices

with pycrg.DataSet.open("a.crg") as a, pycrg.DataSet.open("b.crg") as b:
    result = pycrg.compare(a, b)         # crg_isequal
    result.identical, result.errors, result.warnings
    result.max_difference                # largest |z_b - z_a| on the grid of a
```

`find_peaks(source, iu=None, iv=None, *, threshold=0.5, window=3)` finds isolated spikes and holes
in the elevation grid like `crg_peakfinder`: an edge filter marks candidates, which count as peaks
when their elevation is more than twice the median of the surrounding window (at least 0.1 m). As in
the MATLAB tools, it tests absolute elevations, so it suits data sets whose road surface lies near
`z = 0`. `compare(a, b)` checks the grid layout and the reference lines within the `check_eps` and
`check_tol` tolerances and evaluates both elevations on the grid of `a`, like `crg_isequal`; unlike
`crg_isequal`, `identical` is also false when the grids differ. Both need numpy;
`pycrg.plot.show_peaks()` and `show_isequal()` draw their results.

### Errors

All errors derive from `pycrg.OpenCRGError` (a `RuntimeError`): `OpenCRGLoadError`,
`OpenCRGCheckError`, `OpenCRGEvaluationError` and `OpenCRGClosedError`. Their `messages` attribute
holds the OpenCRG messages `(level, text)` that explain the failure. In addition, `open()` raises
`FileNotFoundError` and `IsADirectoryError` as usual.

### Messages

OpenCRG reports through messages with the levels `MSG_LEVEL_FATAL`, `_WARN`, `_NOTICE`, `_INFO` and
`_DEBUG`. pycrg passes them to the `logging` logger `"pycrg"` (FATAL as `ERROR`, WARN as `WARNING`,
NOTICE as `INFO`, INFO and DEBUG as `DEBUG`), so by default only warnings and errors are shown.
Messages that explain an exception are attached to it instead of being logged.

```python
import logging
logging.getLogger("pycrg").setLevel(logging.INFO)    # also show OpenCRG's notices

pycrg.set_message_callback(lambda level, text: ...)  # or route them to a callback
pycrg.clear_message_callback()
pycrg.set_message_level(pycrg.MSG_LEVEL_DEBUG)       # what OpenCRG generates (default NOTICE)
pycrg.set_max_warn_messages(100)                     # limit the number passed on (-1: no limit)
```

An exception raised by the callback is reported through `sys.unraisablehook` and does not interrupt
OpenCRG.

### Threads

The OpenCRG library keeps global state and pycrg calls it with the GIL held, so calls never run
concurrently. Data sets and contact points may be used from several threads, but closing a data set
while another thread evaluates it is an error of the program. Use a contact point per thread, since
it keeps a search history.

### Experimental allocator callbacks

`pycrg.experimental` exposes OpenCRG's allocator hooks (`set_calloc_callback`,
`set_realloc_callback`, `set_free_callback`, `clear_unsafe_callbacks`) and direct `calloc`,
`realloc` and `free`. They can crash the process if misused and require the environment variable
`PYCRG_ENABLE_UNSAFE_CALLBACKS=1`.

## Visualization

`pycrg.plot` (`pip install "pycrg[plot]"`) draws the figures of the OpenCRG MATLAB tools with
matplotlib: A4 figures with a title, the file name and the date, made of the same plots.

```python
import matplotlib.pyplot as plt
import pycrg
import pycrg.plot

with pycrg.DataSet.open("road.crg") as dataset:
    dataset.show()                                     # all figures, like crg_show
    pycrg.plot.show_road_surface(dataset, (0, 500))    # the first 500 cross sections
    fig, ax = plt.subplots()
    pycrg.plot.plot_elgrid_cross_sect(dataset, ax=ax)  # a single plot in axes of your own
plt.show()                                             # or fig.savefig("road.png")
```

The functions create the figures without displaying them: call `matplotlib.pyplot.show()`, or save
them with `savefig`; Jupyter displays them by itself. The data set may be closed once they exist.
Double-clicking a plot of these figures opens it in a figure of its own, as `copy_ax2fig(ax)` does.

| OpenCRG MATLAB tools | `pycrg.plot` |
|---|---|
| `crg_show` | `show(source, iu, iv)`, also `DataSet.show()` and `RoadSurface.show()` |
| `crg_show_refline_map`, `crg_show_refline_elevation` | `show_refline_map(source, iu)`, `show_refline_elevation(source, iu)` |
| `crg_show_elgrid_cuts_and_limits`, `crg_show_elgrid_surface`, `crg_show_road_surface` | `show_elgrid_cuts_and_limits(source, iu, iv)` and so on |
| `crg_show_road_uv2surface` | `show_road_uv2surface(source, u, v)`: the surface on a grid of your own, also beyond the data |
| `crg_show_refpnts_and_refline` | `show_refpnts_and_refline(source, pxy)`: points `(n, 2)` and their distance from the reference line |
| `crg_show_info` | `show_info(source)`: header, modifiers, options and derived data |
| `crg_show_peaks`, `crg_show_isequal` | `show_peaks(source, peaks)`, `show_isequal(comparison)` |
| `crg_plot_*` (17 plots) | `plot_*(source, ..., *, ax=None, options=None)`: one plot, in `ax` or a new figure |
| `crg_surf`, `crg_figure`, `copy_ax2fig` | `surf(x, y, z)`, `figure(source, title)`, `copy_ax2fig(ax)` |
| `crg_peakfinder`, `crg_isequal` | `pycrg.find_peaks()`, `pycrg.compare()` |
| `DATA.fopt` | `FigureOptions` |

`source` is a `DataSet` or a `RoadSurface`. `iu` and `iv` select cross and long sections as
`(start, stop)` index pairs like Python slices, counted from 0: MATLAB's `[1 100]` is `(0, 100)`.
For more than 3000 cross sections, `show()` draws the surfaces in windows of 1001 cross sections at
the start, in the middle and at the end, as `crg_show` does. Large grids are thinned out for
drawing; select a range for full detail.

`FigureOptions` (argument `options`) sets the `orientation` (`"landscape"` or `"portrait"`), the
`title`, the `file_label` and `date_label` at the bottom, `z_aspect` (0.1 by default: the z axis of
3D plots magnified ten times), `color_period` (colour surfaces by `z` modulo a period, to show small
undulations on large slopes), `light` (shaded surfaces) and the thinning limits `max_surface` and
`max_image`.

### Command line

```bash
pycrg-show road.crg                              # display all figures
pycrg-show road.crg -o figures/                  # one PNG file per figure
pycrg-show road.crg -o road.pdf                  # all figures in one PDF file
pycrg-show road.crg -f road-surface --iu 0 1000 --z-aspect 1 -o surface.svg
pycrg-show road.crg --peaks                      # find and show peaks
pycrg-show a.crg --compare b.crg -o diff.png     # exit status 1 if the files differ
python -m pycrg.plot --help                      # the same command
```

`-f`/`--figure` (repeatable) selects `refline-map`, `refline-elevation`, `elgrid-cuts`,
`elgrid-surface`, `road-surface` or `info`; `--refpoints POINTS` shows the x/y points of a text file
with the reference line; `--no-modifiers` and `--check` control the loading. The exit status is 0 on
success, 1 if `--compare` found differences and 2 on errors. Without `-o`, the figures need an
interactive matplotlib backend.

## Notes on OpenCRG

- **Single precision.** OpenCRG keeps the elevation grid in single precision, also for the double
  precision formats `KDBI` and `LDFI` (about 1e-9 m at centimetre values). `KRBI` stores exactly
  what OpenCRG uses.
- **Text formats.** In `LRFI`/`LDFI` data, a field of exactly `**unused**` reads as 0.0 and any
  other field that is not a number (such as `**********`) as NaN.
- **File references.** `$ROAD_CRG_FILE` names another CRG file. OpenCRG resolves a relative name
  against the working directory of the process; pycrg also tries the directory of the referencing
  file when there is no such file.

## Bundled OpenCRG library

`src/pycrg/vendor/opencrg` holds the OpenCRG C base library (see `VENDOR.md` there for the upstream
commit): release 2.0.1 plus the later upstream fixes for the heading of `uv_to_pk`, the
reference line integration without end point, the default reference point of the modifiers and the
reset of file references after a failure. pycrg applies these patches on top
(`tools/vendor_patches`), each marked with `pycrg:` comments in the code:

1. open file names as UTF-8 on Windows (non-ASCII paths);
2. resolve `$ROAD_CRG_FILE` references against the referencing file as well, and allow references
   in referenced files;
3. reset the reader state for every file (modifiers and options of referenced files were ignored
   after loading certain other files) and release the data set of a failed load;
4. release loader buffers with `crgFree()` (matters with allocator callbacks);
5. query the message limit, so that it also applies with a message callback;
6. let a successful local curvature check pass the check, as in the OpenCRG MATLAB tools;
7. report a diagnostic of straight reference lines at debug instead of warning level;
8. refuse files without data records or with a single cross section, which crashed the loader;
9. avoid an integer overflow in the `BORDER_MODE_REFLECT` evaluation far away from the data.

## Legal notice

`pycrg` is an unofficial community wrapper and is not affiliated with or endorsed by ASAM e.V.

ASAM OpenCRG® is a registered trademark of ASAM e.V.

This package redistributes parts of OpenCRG under the Apache License 2.0 and includes the required
attribution files: `LICENSE`, `NOTICE` and the license files of the vendored sources in
`src/pycrg/vendor/opencrg/`. The sample files in `tests/data/crg-txt` are the OpenCRG text samples.

## Development

```bash
pip install -r requirements-dev.txt
pip install -e .
pytest
ruff check src tests tools examples && mypy
```

Refresh the vendored OpenCRG sources from a clone of the OpenCRG repository; the patches in
`tools/vendor_patches` are applied with `git apply`:

```bash
python tools/vendor_snapshot.py --source ../OpenCRG          # update
python tools/vendor_snapshot.py --source ../OpenCRG --check  # verify the committed snapshot
```

To change the vendored code, create the snapshot with `--no-patches` in a scratch git repository,
apply the existing patches, commit the change and add it as a new patch with `git format-patch`.

Build the distributions with `python -m build`; release wheels are built with `cibuildwheel`
(configuration in `pyproject.toml`).

### Examples

`examples/scripts` contains Python ports of the OpenCRG C demos (`simple_demo.py`,
`reader_demo.py`, `eval_z_demo.py`, `eval_xyuv_demo.py`, `eval_options_demo.py`,
`curvature_demo.py`) and further demos (`basic_roadsurface_demo.py`,
`dataset_contactpoint_demo.py`, `message_callback_demo.py`, `write_and_evaluate_demo.py`,
`visualization_demo.py`, which needs matplotlib, and the experimental allocator demos, which need
`PYCRG_ENABLE_UNSAFE_CALLBACKS=1`). They use the samples in `tests/data/crg-txt` by default and
take a CRG file as argument. The C demo ports follow the C sequence (load with
`apply_modifiers=False`, check, apply the modifiers) and use the `try_*` methods, so that
evaluation failures are reported and the demo continues.

## Changelog

Release notes are maintained in [CHANGELOG.md](CHANGELOG.md).
