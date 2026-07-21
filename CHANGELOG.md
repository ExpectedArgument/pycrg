# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

- No changes yet.

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
