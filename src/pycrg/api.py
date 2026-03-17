from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypeAlias

from . import _native
from .errors import OpenCRGClosedError, OpenCRGError


_MESSAGE_CALLBACK_BRIDGE = None

MessageLevel: TypeAlias = Literal[0, 1, 2, 3, 4, 5]
UV: TypeAlias = tuple[float, float]
XY: TypeAlias = tuple[float, float]
PK: TypeAlias = tuple[float, float]
ClosedTrackData: TypeAlias = tuple[bool, int, float, float]


class MessageCallback(Protocol):
    def __call__(self, level: int, message: str) -> int: ...


def get_release_info() -> str:
    """Return the OpenCRG library release/version string."""
    return _native.get_release_info()


def mem_release() -> None:
    """Release global memory managed by the OpenCRG library."""
    _native.mem_release()


def set_message_level(level: MessageLevel) -> None:
    """Set OpenCRG message verbosity level."""
    _native.msg_set_level(int(level))


def set_max_warn_messages(max_count: int) -> None:
    """Set maximum number of warning/debug messages emitted by OpenCRG."""
    _native.msg_set_max_warn_msgs(int(max_count))


def set_max_log_messages(max_count: int) -> None:
    """Set maximum number of log messages emitted by OpenCRG."""
    _native.msg_set_max_log_msgs(int(max_count))


def is_message_printable(level: MessageLevel) -> bool:
    """Return whether messages at `level` are currently printable."""
    return bool(_native.msg_is_printable(int(level)))


def msg_print(level: MessageLevel, message: str) -> None:
    """Send a message through OpenCRG's message system."""
    _native.msg_print(int(level), str(message))


def set_message_callback(callback: MessageCallback | None) -> None:
    """Register or clear a Python callback for OpenCRG messages.

    The callback receives `(level, message)` and should return an int.
    Return 0 to keep default behavior.
    """
    global _MESSAGE_CALLBACK_BRIDGE
    if callback is None:
        _native.msg_set_callback(None)
        _MESSAGE_CALLBACK_BRIDGE = None
        return

    if not callable(callback):
        raise TypeError("callback must be callable or None")

    def _bridge(level: int, message: str) -> int:
        try:
            result = callback(int(level), str(message))
        except Exception:
            return 0
        try:
            return int(result)
        except Exception:
            return 0

    _MESSAGE_CALLBACK_BRIDGE = _bridge
    _native.msg_set_callback(_MESSAGE_CALLBACK_BRIDGE)


def clear_message_callback() -> None:
    """Clear the currently registered message callback."""
    set_message_callback(None)


def clear_callbacks() -> None:
    """Clear all callbacks registered in the native layer."""
    _native.clear_callbacks()
    global _MESSAGE_CALLBACK_BRIDGE
    _MESSAGE_CALLBACK_BRIDGE = None


@dataclass
class DataSet:
    """Represents an OpenCRG dataset loaded from a `.crg` file."""

    _dataset_id: int
    _closed: bool = False

    @classmethod
    def open(cls, path: str) -> "DataSet":
        """Load a CRG file and return a `DataSet` handle."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(str(file_path))

        dataset_id = int(_native.loader_read_file(str(file_path)))
        if dataset_id <= 0:
            raise OpenCRGError(f"Failed to load CRG file: {file_path}")

        return cls(_dataset_id=dataset_id)

    @property
    def dataset_id(self) -> int:
        """Native OpenCRG dataset identifier."""
        return self._dataset_id

    def _ensure_open(self) -> None:
        if self._closed:
            raise OpenCRGClosedError("DataSet is already closed")

    def check(self) -> bool:
        """Run OpenCRG consistency checks for this dataset."""
        self._ensure_open()
        return bool(_native.check(self._dataset_id))

    def print_header(self) -> None:
        """Print dataset header information via OpenCRG."""
        self._ensure_open()
        _native.dataset_print_header(self._dataset_id)

    def print_channel_info(self) -> None:
        """Print dataset channel information via OpenCRG."""
        self._ensure_open()
        _native.dataset_print_channel_info(self._dataset_id)

    def print_road_info(self) -> None:
        """Print dataset road/reference-line statistics via OpenCRG."""
        self._ensure_open()
        _native.dataset_print_road_info(self._dataset_id)

    def u_range(self) -> UV:
        """Return minimum and maximum `u` coordinates."""
        self._ensure_open()
        return _native.dataset_get_u_range(self._dataset_id)

    def v_range(self) -> UV:
        """Return minimum and maximum `v` coordinates."""
        self._ensure_open()
        return _native.dataset_get_v_range(self._dataset_id)

    def increments(self) -> UV:
        """Return `(u_increment, v_increment)` for the dataset grid."""
        self._ensure_open()
        return _native.dataset_get_increments(self._dataset_id)

    def closed_track_data(self) -> ClosedTrackData:
        """Return closed-track utility tuple `(ok, is_closed, u_min, u_max)`."""
        self._ensure_open()
        ok, is_closed, u_close_min, u_close_max = _native.dataset_get_closed_track(self._dataset_id)
        return bool(ok), int(is_closed), float(u_close_min), float(u_close_max)

    def modifier_set_int(self, modifier_id: int, value: int) -> bool:
        """Set an integer dataset modifier value."""
        self._ensure_open()
        return bool(_native.dataset_modifier_set_int(self._dataset_id, int(modifier_id), int(value)))

    def modifier_set_double(self, modifier_id: int, value: float) -> bool:
        """Set a floating-point dataset modifier value."""
        self._ensure_open()
        return bool(_native.dataset_modifier_set_double(self._dataset_id, int(modifier_id), float(value)))

    def modifier_get_int(self, modifier_id: int) -> int | None:
        """Get an integer modifier value or `None` if unset."""
        self._ensure_open()
        found, value = _native.dataset_modifier_get_int(self._dataset_id, int(modifier_id))
        return int(value) if found else None

    def modifier_get_double(self, modifier_id: int) -> float | None:
        """Get a floating-point modifier value or `None` if unset."""
        self._ensure_open()
        found, value = _native.dataset_modifier_get_double(self._dataset_id, int(modifier_id))
        return float(value) if found else None

    def modifier_remove(self, modifier_id: int) -> bool:
        """Remove one modifier from the dataset."""
        self._ensure_open()
        return bool(_native.dataset_modifier_remove(self._dataset_id, int(modifier_id)))

    def modifier_remove_all(self) -> bool:
        """Remove all modifiers from the dataset."""
        self._ensure_open()
        return bool(_native.dataset_modifier_remove_all(self._dataset_id))

    def modifiers_print(self) -> None:
        """Print current dataset modifiers via OpenCRG."""
        self._ensure_open()
        _native.dataset_modifiers_print(self._dataset_id)

    def modifiers_apply(self) -> None:
        """Apply currently configured modifiers and clear them."""
        self._ensure_open()
        _native.dataset_modifiers_apply(self._dataset_id)

    def modifier_set_default(self) -> None:
        """Reset dataset modifiers to OpenCRG defaults."""
        self._ensure_open()
        _native.dataset_modifier_set_default(self._dataset_id)

    def option_set_default(self) -> None:
        """Reset dataset-level default options used by contact points."""
        self._ensure_open()
        _native.dataset_option_set_default(self._dataset_id)

    def create_contact_point(self) -> "ContactPoint":
        """Create a `ContactPoint` bound to this dataset."""
        self._ensure_open()
        cp_id = int(_native.contact_point_create(self._dataset_id))
        if cp_id < 0:
            raise OpenCRGError("Failed to create contact point")
        return ContactPoint(_dataset=self, _cp_id=cp_id)

    def close(self) -> None:
        """Release dataset resources in OpenCRG."""
        if self._closed:
            return
        _native.contact_point_delete_all(self._dataset_id)
        released = bool(_native.dataset_release(self._dataset_id))
        if not released:
            raise OpenCRGError("Failed to release dataset")
        self._closed = True

    def __enter__(self) -> "DataSet":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


@dataclass
class ContactPoint:
    """Represents an OpenCRG contact point for evaluations/options."""

    _dataset: DataSet
    _cp_id: int
    _closed: bool = False

    @property
    def cp_id(self) -> int:
        """Native OpenCRG contact-point identifier."""
        return self._cp_id

    def _ensure_open(self) -> None:
        self._dataset._ensure_open()
        if self._closed:
            raise OpenCRGClosedError("ContactPoint is already closed")

    def option_set_int(self, option_id: int, value: int) -> bool:
        """Set an integer contact-point option value."""
        self._ensure_open()
        return bool(_native.cp_option_set_int(self._cp_id, int(option_id), int(value)))

    def option_set_double(self, option_id: int, value: float) -> bool:
        """Set a floating-point contact-point option value."""
        self._ensure_open()
        return bool(_native.cp_option_set_double(self._cp_id, int(option_id), float(value)))

    def option_get_int(self, option_id: int) -> int | None:
        """Get an integer option value or `None` if unset."""
        self._ensure_open()
        found, value = _native.cp_option_get_int(self._cp_id, int(option_id))
        return int(value) if found else None

    def option_get_double(self, option_id: int) -> float | None:
        """Get a floating-point option value or `None` if unset."""
        self._ensure_open()
        found, value = _native.cp_option_get_double(self._cp_id, int(option_id))
        return float(value) if found else None

    def option_remove(self, option_id: int) -> bool:
        """Remove one option from the contact point."""
        self._ensure_open()
        return bool(_native.cp_option_remove(self._cp_id, int(option_id)))

    def option_remove_all(self) -> bool:
        """Remove all options from the contact point."""
        self._ensure_open()
        return bool(_native.cp_option_remove_all(self._cp_id))

    def options_print(self) -> None:
        """Print current contact-point options via OpenCRG."""
        self._ensure_open()
        _native.cp_options_print(self._cp_id)

    def set_default_options(self) -> None:
        """Reset contact-point options to defaults."""
        self._ensure_open()
        _native.cp_set_default_options(self._cp_id)

    def set_history(self, history_size: int) -> bool:
        """Set contact-point history size used by OpenCRG internals."""
        self._ensure_open()
        return bool(_native.cp_set_history(self._cp_id, int(history_size)))

    def uv_to_z(self, u: float, v: float) -> float:
        """Evaluate elevation `z` at `(u, v)`."""
        self._ensure_open()
        return float(_native.eval_uv_to_z(self._cp_id, float(u), float(v)))

    def try_uv_to_z(self, u: float, v: float) -> float | None:
        """Evaluate elevation at `(u, v)` and return `None` on conversion/eval failure."""
        self._ensure_open()
        try:
            return self.uv_to_z(u, v)
        except RuntimeError:
            return None

    def xy_to_z(self, x: float, y: float) -> float:
        """Evaluate elevation `z` at `(x, y)`."""
        self._ensure_open()
        return float(_native.eval_xy_to_z(self._cp_id, float(x), float(y)))

    def try_xy_to_z(self, x: float, y: float) -> float | None:
        """Evaluate elevation at `(x, y)` and return `None` on conversion/eval failure."""
        self._ensure_open()
        try:
            return self.xy_to_z(x, y)
        except RuntimeError:
            return None

    def uv_to_xy(self, u: float, v: float) -> XY:
        """Transform `(u, v)` to world coordinates `(x, y)`."""
        self._ensure_open()
        x, y = _native.eval_uv_to_xy(self._cp_id, float(u), float(v))
        return float(x), float(y)

    def try_uv_to_xy(self, u: float, v: float) -> XY | None:
        """Transform `(u, v)` to `(x, y)` and return `None` on conversion failure."""
        self._ensure_open()
        try:
            return self.uv_to_xy(u, v)
        except RuntimeError:
            return None

    def xy_to_uv(self, x: float, y: float) -> UV:
        """Transform world coordinates `(x, y)` to `(u, v)`."""
        self._ensure_open()
        u, v = _native.eval_xy_to_uv(self._cp_id, float(x), float(y))
        return float(u), float(v)

    def try_xy_to_uv(self, x: float, y: float) -> UV | None:
        """Transform `(x, y)` to `(u, v)` and return `None` on conversion failure."""
        self._ensure_open()
        try:
            return self.xy_to_uv(x, y)
        except RuntimeError:
            return None

    def uv_to_pk(self, u: float, v: float) -> PK:
        """Evaluate heading/curvature `(phi, curv)` at `(u, v)`."""
        self._ensure_open()
        phi, curv = _native.eval_uv_to_pk(self._cp_id, float(u), float(v))
        return float(phi), float(curv)

    def try_uv_to_pk(self, u: float, v: float) -> PK | None:
        """Evaluate heading/curvature at `(u, v)` and return `None` on failure."""
        self._ensure_open()
        try:
            return self.uv_to_pk(u, v)
        except RuntimeError:
            return None

    def xy_to_pk(self, x: float, y: float) -> PK:
        """Evaluate heading/curvature `(phi, curv)` at `(x, y)`."""
        self._ensure_open()
        phi, curv = _native.eval_xy_to_pk(self._cp_id, float(x), float(y))
        return float(phi), float(curv)

    def try_xy_to_pk(self, x: float, y: float) -> PK | None:
        """Evaluate heading/curvature at `(x, y)` and return `None` on failure."""
        self._ensure_open()
        try:
            return self.xy_to_pk(x, y)
        except RuntimeError:
            return None

    def close(self) -> None:
        """Release contact-point resources in OpenCRG."""
        if self._closed:
            return
        deleted = bool(_native.contact_point_delete(self._cp_id))
        if not deleted:
            raise OpenCRGError("Failed to delete contact point")
        self._closed = True


@dataclass
class RoadSurface:
    """Convenience wrapper owning one `DataSet` and one `ContactPoint`."""

    _dataset: DataSet
    _cp: ContactPoint

    @classmethod
    def open(cls, path: str) -> "RoadSurface":
        """Open a CRG file and create ready-to-use convenience wrapper."""
        dataset = DataSet.open(path)
        cp = dataset.create_contact_point()
        return cls(_dataset=dataset, _cp=cp)

    @property
    def dataset_id(self) -> int:
        """Native dataset id of the underlying dataset."""
        return self._dataset.dataset_id

    @property
    def cp_id(self) -> int:
        """Native contact-point id of the underlying contact point."""
        return self._cp.cp_id

    def u_range(self) -> UV:
        return self._dataset.u_range()

    def v_range(self) -> UV:
        return self._dataset.v_range()

    def increments(self) -> UV:
        return self._dataset.increments()

    def uv_to_z(self, u: float, v: float) -> float:
        return self._cp.uv_to_z(u, v)

    def try_uv_to_z(self, u: float, v: float) -> float | None:
        return self._cp.try_uv_to_z(u, v)

    def xy_to_z(self, x: float, y: float) -> float:
        return self._cp.xy_to_z(x, y)

    def try_xy_to_z(self, x: float, y: float) -> float | None:
        return self._cp.try_xy_to_z(x, y)

    def uv_to_xy(self, u: float, v: float) -> XY:
        return self._cp.uv_to_xy(u, v)

    def try_uv_to_xy(self, u: float, v: float) -> XY | None:
        return self._cp.try_uv_to_xy(u, v)

    def xy_to_uv(self, x: float, y: float) -> UV:
        return self._cp.xy_to_uv(x, y)

    def try_xy_to_uv(self, x: float, y: float) -> UV | None:
        return self._cp.try_xy_to_uv(x, y)

    def uv_to_pk(self, u: float, v: float) -> PK:
        return self._cp.uv_to_pk(u, v)

    def try_uv_to_pk(self, u: float, v: float) -> PK | None:
        return self._cp.try_uv_to_pk(u, v)

    def xy_to_pk(self, x: float, y: float) -> PK:
        return self._cp.xy_to_pk(x, y)

    def try_xy_to_pk(self, x: float, y: float) -> PK | None:
        return self._cp.try_xy_to_pk(x, y)

    def close(self) -> None:
        """Close contact point and dataset in the correct order."""
        self._cp.close()
        self._dataset.close()

    def __enter__(self) -> "RoadSurface":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
