# pycrg

Unofficial Python bindings for the ASAM OpenCRG C API.

## Features

- Full non-visual OpenCRG C API coverage in Python
- High-level `DataSet`, `ContactPoint`, and `RoadSurface` APIs
- Stable message callback support
- Experimental allocator callback support behind `PYCRG_ENABLE_UNSAFE_CALLBACKS=1`
- Demo scripts and smoke tests

Exposed functionality includes:

- dataset lifecycle and consistency checks
- dataset metadata printing and range/increment queries
- dataset modifier set/get/remove/apply/default operations
- contact point lifecycle and option set/get/remove/default/history operations
- evaluation and transforms: `(u, v) <-> (x, y)`, `(u, v) -> z`, `(x, y) -> z`, `(u, v)/(x, y) -> (phi, curv)`
- global controls: OpenCRG release info, memory release, message level and limits

Public callback APIs:

- Stable/public:
  - `set_message_callback`
  - `clear_message_callback`
- Experimental/unsafe (`pycrg.experimental`):
  - `set_calloc_callback`
  - `set_realloc_callback`
  - `set_free_callback`
  - `clear_unsafe_callbacks`

Unsafe allocator callbacks are disabled by default and require `PYCRG_ENABLE_UNSAFE_CALLBACKS=1`.

## Legal notice

`pycrg` is an unofficial community wrapper and is not affiliated with or endorsed by ASAM e.V.

ASAM OpenCRG® is a registered trademark of ASAM e.V.

This package redistributes parts of OpenCRG under Apache License 2.0 and includes required attribution files:

- `LICENSE`
- `NOTICE`
- vendored source license files under `src/pycrg/vendor/opencrg/`

## Installation

```bash
pip install pycrg
```

## Development

### 0) Install development dependencies

```bash
pip install -r requirements-dev.txt
```

### 1) Refresh vendor snapshot (before building wheel/sdist)

```bash
python tools/vendor_snapshot.py --source ../OpenCRG
```

`--source` may point to any local clone of OpenCRG.

### 2) Build

```bash
python -m build
```

### 3) Install locally

```bash
pip install dist/*.whl
```

## Changelog

Release notes are maintained in [CHANGELOG.md](CHANGELOG.md).

## Minimal usage

```python
from pycrg import ContactPoint, DataSet, RoadSurface

dataset = DataSet.open("tests/data/sample.crg")
cp: ContactPoint = dataset.create_contact_point()

print(dataset.u_range())
print(cp.uv_to_z(0.0, 0.0))
cp.close()
dataset.close()

road = RoadSurface.open("tests/data/sample.crg")
print(road.u_range())
print(road.v_range())
print(road.uv_to_z(0.0, 0.0))
road.close()
```

## Example scripts

Run from project root after install/build.

- C demo ports (`simple`, `eval_z`, `eval_xyuv`, `eval_options`) are exception-safe: evaluation/conversion failures are handled as warnings and execution continues.
- This behavior is implemented via non-throwing `try_*` API methods on `ContactPoint` / `RoadSurface`.
- `python examples/scripts/basic_roadsurface_demo.py`
- `python examples/scripts/dataset_contactpoint_demo.py`
- `python examples/scripts/message_callback_demo.py`
- `python examples/scripts/simple_demo.py`
- `python examples/scripts/reader_demo.py`
- `python examples/scripts/eval_z_demo.py`
- `python examples/scripts/eval_xyuv_demo.py`
- `python examples/scripts/eval_options_demo.py`
- `python examples/scripts/curvature_demo.py`
- `PYCRG_ENABLE_UNSAFE_CALLBACKS=1 python examples/scripts/unsafe_allocator_callbacks_demo.py`
- `PYCRG_ENABLE_UNSAFE_CALLBACKS=1 python examples/scripts/experimental_allocator_api_demo.py`
