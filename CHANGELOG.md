# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

- No changes yet.

## [2.1.0] - 2026-10-14

This release adds the visualization of the OpenCRG MATLAB tools.

### Added

- `pycrg.plot` draws the figures and plots of the OpenCRG MATLAB tools with matplotlib
  (`pip install "pycrg[plot]"`), named like the MATLAB functions without the `crg_` prefix:
  `show()` (`crg_show`); the figures `show_refline_map()`, `show_refline_elevation()`,
  `show_refpnts_and_refline()`, `show_elgrid_cuts_and_limits()`, `show_elgrid_surface()`,
  `show_road_surface()`, `show_road_uv2surface()`, `show_info()`, `show_peaks()` and
  `show_isequal()`; the 17 `plot_*` plots, which also draw into axes of your own; `surf()`,
  `figure()`, `copy_ax2fig()` and `FigureOptions` (`DATA.fopt`). As `crg_show`, `show()` draws long
  data sets in windows of 1001 cross sections. Large grids are thinned out for drawing, and
  double-clicking a plot opens it in a figure of its own
- `DataSet.show()` and `RoadSurface.show()`, shortcuts for `pycrg.plot.show()`
- The command `pycrg-show` (also `python -m pycrg.plot`) shows a CRG file or writes its figures to
  image or PDF files; it also finds peaks (`--peaks`), compares with another file (`--compare`, exit
  status 1 if they differ) and shows reference points (`--refpoints`)
- `pycrg.find_peaks()` (`crg_peakfinder`) finds isolated spikes and holes in the elevation grid,
  `pycrg.compare()` (`crg_isequal`) compares two data sets; results `CrgPeaks` and `CrgComparison`
- Optional dependency `pycrg[plot]` (numpy and matplotlib) and the example
  `visualization_demo.py`

### Fixed

- `increments()` returned a v increment of 0.01 (or the value of the file header) for long
  sections at variable positions instead of 0, as documented

### Packaging

- The wheel tests and the type checks include the visualization; on 32-bit Windows and Linux,
  which have no matplotlib wheels, the visualization tests are skipped

## [2.0.0] - 2026-10-13

This release changes the defaults of `open()` and the routing of OpenCRG messages. See
"Upgrading from 1.x" below.

### Changed

- `DataSet.open()` and `RoadSurface.open()` now follow the loading sequence of the OpenCRG tools
  and apply the file's modifiers (`$ROAD_CRG_MODS`) by default. A file without that section gets
  OpenCRG's default modifiers, which move the start of the reference line to `x = y = z = 0` with
  heading 0 and replace NaN values at the road borders. New keyword arguments:
  `open(path, *, apply_modifiers=True, check=False)`
- OpenCRG messages are passed to the `logging` logger `"pycrg"` instead of being written to C
  `stderr`; by default only warnings and errors are shown. The messages explaining a failure are
  attached to the exception instead (`OpenCRGError.messages`) and summarized in its text
- `set_message_callback()` callbacks may return anything (the value is ignored); an exception
  raised by the callback is reported through `sys.unraisablehook` instead of being swallowed, and
  `set_max_warn_messages()` now also limits the messages passed to a callback
- `print_header()`, `print_channel_info()`, `print_road_info()`, `modifiers_print()` and
  `options_print()` print to `sys.stdout` (or `file=`) instead of C `stderr`
- `modifiers_apply()` checks the modifiers first (raising `OpenCRGCheckError` for invalid ones),
  then applies and removes them, so that applying twice does not apply them twice
- `DataSet`, `ContactPoint` and `RoadSurface` are no longer dataclasses: they cannot be created
  from an id, copied or pickled, and compare by identity. Closing a data set closes its contact
  points; `mem_release()` closes all handles. A data set garbage collected without `close()` is
  released with a `ResourceWarning`
- Evaluations refuse non-finite co-ordinates (`OpenCRGEvaluationError`, or `None` from `try_*`)
- The bundled OpenCRG C library is updated to the current upstream state (release 2.0.1 plus later
  fixes for the heading of `uv_to_pk`, the reference line integration and the default modifiers),
  with pycrg patches kept in `tools/vendor_patches` and listed in the README
- Status changed to "Production/Stable"

### Added

- Exceptions `OpenCRGLoadError`, `OpenCRGCheckError` and `OpenCRGEvaluationError` (subclasses of
  `OpenCRGError`, a `RuntimeError`), exported from `pycrg` together with `OpenCRGClosedError`.
  `open()` raises `FileNotFoundError` and `IsADirectoryError` with `errno` set
- `check(*, raise_on_error=False)`; `format_header()`, `format_channel_info()`,
  `format_road_info()`, `format_modifiers()` and `format_options()` return OpenCRG's summaries
  as text
- `DataSet.header` and `pycrg.read_header()`: the parsed file header (`CrgHeader`, `CrgChannel`),
  including the comment, `$ROAD_CRG` entries, modifiers, options and channel definitions
- `DataSet.grid()`: the data set arrays as numpy arrays (`CrgGrid`)
- Vectorised evaluation with numpy: `uv_to_z_many()`, `xy_to_z_many()`, `uv_to_xy_many()`,
  `xy_to_uv_many()`, `uv_to_pk_many()`, `xy_to_pk_many()`
- `pycrg.write()`: writes CRG files in the formats `KRBI`, `KDBI`, `LRFI` and `LDFI`, following
  the reference writer of the OpenCRG MATLAB tools and validating the input
- `RoadSurface` offers the check, modifier, option, grid and text methods of its data set and
  contact point, exposes them as `.dataset` and `.contact_point`, and wraps an open data set with
  `RoadSurface(dataset)`
- `DataSet.path`, `closed` properties, `ContactPoint.dataset`, `get_message_level()`
- Paths may be `str`, `bytes` or `os.PathLike`
- Optional dependency `pycrg[numpy]`; typed native module (`_native.pyi`); the constants module
  defines `__all__`
- Tests for loading, modifiers, messages, lifetime, evaluation, header, grid and writer, using the
  OpenCRG text samples (`tests/data/crg-txt`)

### Fixed

- File names with non-ASCII characters could not be opened on Windows
- `$ROAD_CRG_FILE` references are also resolved against the directory of the referencing file
  (OpenCRG uses the working directory of the process only)
- The state of a file read before, for example one that failed to load, could change how the next
  file was read (its modifiers, options and file references); the data set of a failed load leaked
- Using a closed data set or contact point could act on an unrelated, newer object, because
  OpenCRG reuses ids
- Files without data records or with a single cross section crashed the process; evaluation far
  outside the data with `BORDER_MODE_REFLECT` overflowed an integer
- The consistency check failed when the global curvature test failed although the local test
  succeeded (the OpenCRG MATLAB tools accept such data), and each check leaked a contact point
- The loader released buffers with `free()` instead of `crgFree()` (matters with the experimental
  allocator callbacks)
- On 32-bit x86 Linux, the consistency check rejected every file: with the x87 FPU, OpenCRG
  compared its default `check_eps` with a constant evaluated in extended precision. The extension
  is now built with SSE2 floating point there, as on all other platforms

### Removed

- The undocumented native functions `open_file`, `close`, `u_range`, `v_range`, `uv_to_z`,
  `xy_to_z`, `uv_to_xy`, `xy_to_uv`, `msg_set_callback` and `clear_callbacks` of the private
  module `pycrg._native`

### Packaging

- Wheels for Linux aarch64, macOS x86_64 and CPython 3.14; the wheel tests run the test suite
- Wheels no longer contain the C sources; the sdist contains the tests and their data
- CI builds the sdist, builds the wheel from it and runs the tests outside the checkout on Linux
  (x86_64, aarch64), Windows and macOS, runs ruff and mypy, and checks that the vendored OpenCRG
  sources match upstream plus the patches
- PEP 639 license metadata (`license-files`), Python version classifiers and `Typing :: Typed`

### Upgrading from 1.x

- To keep the data exactly as stored in the file, as 1.x did, use
  `DataSet.open(path, apply_modifiers=False)`. Positions and elevations of files without a
  `$ROAD_CRG_MODS` section differ otherwise
- Configure the `"pycrg"` logger (or set a message callback) to see OpenCRG's notices, such as the
  data set statistics, which 1.x printed to `stderr`
- Catching `RuntimeError` or `OpenCRGError` keeps working; the new subclasses tell the failures
  apart

## [1.0.1] - 2026-07-21

### Fixed

- Made `src/pycrg/_version.py` the single source of truth for the package version instead of a second, unused copy hardcoded in `pyproject.toml`, and exposed it as `pycrg.__version__`
- Fixed a 32/64-bit varargs format mismatch in the native allocator callback bridges (`calloc`/`realloc`) that passed `unsigned long long` values through the `k`/`O..k` format codes (which read a narrower `unsigned long`), corrupting sizes/pointers on LLP64 platforms such as the Windows wheel build
- Fixed `pycrg/experimental.py` so its module docstring is no longer discarded by a `from __future__ import annotations` placed before it

### Changed

- Added `cp313-*` to the `cibuildwheel` build matrix so PyPI releases ship prebuilt wheels for Python 3.13
- Updated `testpypi.yml` GitHub Actions to the same action versions already used by `ci.yml`/`release.yml`

## [1.0.0] - 2026-03-17

### Changed

- Excluded heavyweight test data from the source distribution to keep PyPI uploads small and reliable
- Allowed the release workflow to skip already-published files so missing wheels can be uploaded safely

## [0.1.0] - 2026-03-16

### Added

- Full non-visual `pycrg` Python wrapper for OpenCRG C API
- Native CPython extension (`pycrg._native`) with:
  - file open/close
  - `u/v` range queries
  - `uv <-> xy` conversion
  - `uv/xy -> z` evaluation
- High-level `DataSet`, `ContactPoint`, and `RoadSurface` APIs
- Constants module mirroring OpenCRG option/modifier/message IDs
- Stable message callback APIs and experimental allocator callback APIs
- Runnable demo scripts under `examples/scripts`
- Vendor snapshot workflow via `tools/vendor_snapshot.py`
- Packaging for `sdist` and platform wheel builds
- CI workflow with smoke tests
- Release workflow for multi-platform wheels + sdist + Trusted Publishing to PyPI
- Legal attribution packaging (`LICENSE`, `NOTICE`, vendored OpenCRG license files)
