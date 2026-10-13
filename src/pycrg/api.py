"""High-level Python API for the OpenCRG C library.

Ownership model: every native OpenCRG data set and contact point is owned by
exactly one Python object (:class:`DataSet`, :class:`ContactPoint`). These
objects cannot be copied or pickled, compare by identity, and track whether the
native object still exists. Closing a data set closes its contact points;
:func:`mem_release` closes everything. A data set that is garbage collected
without being closed is released, with a :class:`ResourceWarning`.
"""

from __future__ import annotations

import errno
import os
import sys
import threading
import warnings
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO, TYPE_CHECKING, Any, Literal, NoReturn, Protocol, SupportsIndex, TypeAlias, Union

from . import _messages, _native
from .constants import MSG_LEVEL_NOTICE
from .errors import (
    OpenCRGCheckError,
    OpenCRGClosedError,
    OpenCRGError,
    OpenCRGEvaluationError,
    OpenCRGLoadError,
)
from .header import CrgHeader, read_header

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    FloatArray: TypeAlias = "np.ndarray[Any, np.dtype[np.float64]]"
    ArrayLike: TypeAlias = "npt.ArrayLike"

__all__ = [
    "ContactPoint",
    "CrgGrid",
    "DataSet",
    "MessageCallback",
    "RoadSurface",
    "clear_callbacks",
    "clear_message_callback",
    "get_message_level",
    "get_release_info",
    "is_message_printable",
    "mem_release",
    "msg_print",
    "set_max_log_messages",
    "set_max_warn_messages",
    "set_message_callback",
    "set_message_level",
]

MessageLevel: TypeAlias = Literal[0, 1, 2, 3, 4, 5]
PathType: TypeAlias = Union[str, bytes, "os.PathLike[str]", "os.PathLike[bytes]"]
UV: TypeAlias = "tuple[float, float]"
XY: TypeAlias = "tuple[float, float]"
PK: TypeAlias = "tuple[float, float]"
ClosedTrackData: TypeAlias = "tuple[bool, int, float, float]"


class MessageCallback(Protocol):
    """Receives OpenCRG messages: the level (``MSG_LEVEL_*``) and the text.

    The return value is ignored.
    """

    def __call__(self, level: int, message: str, /) -> object: ...


# ---------------------------------------------------------------------------
# global functions
# ---------------------------------------------------------------------------


def get_release_info() -> str:
    """Return the release string of the bundled OpenCRG C library."""
    return _native.get_release_info()


def mem_release() -> None:
    """Release all memory held by the OpenCRG library.

    All data sets and contact points are closed: using them afterwards raises
    :class:`~pycrg.errors.OpenCRGClosedError`, and closing them is a no-op.
    """
    with _lock:
        for handle in list(_open_datasets.values()):
            handle.invalidate()
        _open_datasets.clear()
        _native.mem_release()


def set_message_level(level: MessageLevel | int) -> None:
    """Set the most verbose OpenCRG message level that is generated.

    The default is ``MSG_LEVEL_NOTICE``. Generated messages are passed to the
    ``pycrg`` logger (see :func:`set_message_callback`), which shows warnings
    and errors by default.
    """
    _native.msg_set_level(int(level))


def get_message_level() -> int:
    """Return the most verbose OpenCRG message level that is generated."""
    return _native.msg_get_level()


def set_max_warn_messages(max_count: int) -> None:
    """Limit the number of OpenCRG messages passed on (``-1``: unlimited).

    Messages beyond the limit are still attached to exceptions. A CRG file can
    set this limit, too (option ``warn_msgs``).
    """
    _native.msg_set_max_warn_msgs(int(max_count))


def set_max_log_messages(max_count: int) -> None:
    """Set the OpenCRG log message limit (kept for API completeness; the C
    library currently does not use it)."""
    _native.msg_set_max_log_msgs(int(max_count))


def is_message_printable(level: MessageLevel | int) -> bool:
    """Return whether messages of ``level`` are currently generated and passed on."""
    return _native.msg_is_printable(int(level))


def msg_print(level: MessageLevel | int, message: str) -> None:
    """Send a message through the OpenCRG message system."""
    _native.msg_print(int(level), str(message))


def set_message_callback(callback: MessageCallback | Callable[[int, str], object] | None) -> None:
    """Route OpenCRG messages to ``callback(level, text)`` instead of logging.

    By default, messages go to the :mod:`logging` logger ``"pycrg"``: FATAL as
    ``ERROR``, WARN as ``WARNING``, NOTICE as ``INFO`` and INFO/DEBUG as
    ``DEBUG``. Without any logging configuration, Python prints warnings and
    errors to ``sys.stderr``.

    The text is passed as OpenCRG formats it, usually ending with a newline.
    An exception raised by the callback is reported through
    :func:`sys.unraisablehook` and does not interrupt OpenCRG. ``None``
    restores the default routing.
    """
    _messages.set_callback(callback)


def clear_message_callback() -> None:
    """Restore the default routing of OpenCRG messages to logging."""
    _messages.set_callback(None)


def clear_callbacks() -> None:
    """Clear the message callback and the (experimental) allocator callbacks."""
    _native.clear_allocator_callbacks()
    _messages.set_callback(None)


# ---------------------------------------------------------------------------
# native handles
# ---------------------------------------------------------------------------

_lock = threading.RLock()
_open_datasets: dict[int, _DataSetHandle] = {}


class _DataSetHandle:
    """Shared state of one native data set."""

    __slots__ = ("id", "alive", "contact_points", "__weakref__")

    def __init__(self, dataset_id: int) -> None:
        self.id = dataset_id
        self.alive = True
        self.contact_points: set[_ContactPointHandle] = set()

    def invalidate(self) -> None:
        self.alive = False
        for contact_point in self.contact_points:
            contact_point.alive = False
        self.contact_points.clear()


class _ContactPointHandle:
    """Shared state of one native contact point."""

    __slots__ = ("id", "alive", "dataset", "__weakref__")

    def __init__(self, cp_id: int, dataset: _DataSetHandle) -> None:
        self.id = cp_id
        self.alive = True
        self.dataset = dataset


def _release_dataset(handle: _DataSetHandle) -> None:
    with _lock:
        if not handle.alive:
            return
        handle.invalidate()
        _open_datasets.pop(handle.id, None)
        # also deletes the contact points of the data set
        _native.dataset_release(handle.id)


def _release_contact_point(handle: _ContactPointHandle) -> None:
    with _lock:
        if not handle.alive:
            return
        handle.alive = False
        handle.dataset.contact_points.discard(handle)
        if handle.dataset.alive:
            _native.contact_point_delete(handle.id)


def _finalize_dataset(handle: _DataSetHandle, description: str) -> None:
    if handle.alive:
        # release first: the warning raises if warnings are turned into errors
        _release_dataset(handle)
        warnings.warn(f"unclosed {description}", ResourceWarning, stacklevel=2)


def _raise_closed(kind: str) -> NoReturn:
    raise OpenCRGClosedError(f"{kind} is closed")


class _NotCopyable:
    """Objects owning a native OpenCRG object cannot be copied or pickled: a copy
    would release the native object a second time or outlive it."""

    __slots__ = ()

    def _refuse(self) -> NoReturn:
        raise TypeError(f"{type(self).__name__} objects own a native OpenCRG object and cannot be copied or pickled")

    def __copy__(self) -> NoReturn:
        self._refuse()

    def __deepcopy__(self, memo: object) -> NoReturn:
        self._refuse()

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        self._refuse()


def _require_numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError("this function requires numpy (pip install pycrg[numpy])") from exc
    return numpy


def _failure(what: str, path: str | None, messages: _messages.MessageList) -> str:
    text = what if path is None else f"{what}: {path!r}"
    details = _messages.summarize(messages)
    return f"{text} ({details})" if details else text


def _check_path(path: PathType) -> str | bytes:
    fspath = os.fspath(path)
    if not isinstance(fspath, (str, bytes)):  # pragma: no cover - os.fspath guarantees this
        raise TypeError(f"expected str, bytes or os.PathLike, not {type(path).__name__}")
    if os.path.isdir(fspath):
        raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), fspath)
    if not os.path.exists(fspath):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), fspath)
    return fspath


# ---------------------------------------------------------------------------
# DataSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class CrgGrid:
    """The arrays of a loaded data set, as returned by :meth:`DataSet.grid`.

    The values are those used for evaluation, after any applied modifiers.
    ``nu`` is the number of cross sections, ``nv`` the number of long sections.

    Attributes:
        u: u position of each cross section, shape ``(nu,)``.
        v: v position of each long section, shape ``(nv,)``.
        z: elevation grid relative to the reference line, shape ``(nu, nv)``.
            OpenCRG keeps it in single precision.
        x, y: reference line position at each cross section, shape ``(nu,)``.
        phi: reference line heading, shape ``(nu,)``; ``phi[i]`` is the heading
            of the segment from cross section ``i - 1`` to ``i`` (``phi[0]`` is
            the start heading).
        slope: reference line slope, shape ``(nu,)``.
        bank: banking (cross slope), shape ``(nu,)``.
        ref_z: reference line elevation, shape ``(nu,)``.
    """

    u: FloatArray
    v: FloatArray
    z: FloatArray
    x: FloatArray
    y: FloatArray
    phi: FloatArray
    slope: FloatArray
    bank: FloatArray
    ref_z: FloatArray

    @property
    def elevation(self) -> FloatArray:
        """Absolute elevation at the grid nodes, shape ``(nu, nv)``:
        ``z + ref_z + bank * v``, which is what ``uv_to_z`` returns there."""
        return self.z + self.ref_z[:, None] + self.bank[:, None] * self.v[None, :]


class DataSet(_NotCopyable):
    """An OpenCRG data set loaded from a ``.crg`` file.

    Create it with :meth:`DataSet.open`, preferably in a ``with`` block::

        with DataSet.open("road.crg") as dataset:
            cp = dataset.create_contact_point()
            z = cp.uv_to_z(10.0, 0.5)
    """

    __slots__ = ("_handle", "_path", "_finalizer", "_header", "__weakref__")

    _handle: _DataSetHandle
    _path: str | bytes
    _finalizer: weakref.finalize[..., DataSet]
    _header: CrgHeader | None

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("DataSet objects are created with DataSet.open()")

    @classmethod
    def open(cls, path: PathType, *, apply_modifiers: bool = True, check: bool = False) -> DataSet:
        """Load a CRG file.

        This follows the sequence of the OpenCRG tools: load the file, check it
        (if ``check`` is true) and apply its modifiers (if ``apply_modifiers`` is
        true).

        Args:
            path: the file (``str``, ``bytes`` or ``os.PathLike``).
            apply_modifiers: apply the modifiers of the file's
                ``$ROAD_CRG_MODS`` section, for example re-positioning, scaling
                or NaN handling. Without such a section, OpenCRG's default
                modifiers apply: they move the start of the reference line to
                ``x = y = z = 0`` with heading 0 and replace NaN values at the
                borders by the last valid value. An empty ``$ROAD_CRG_MODS``
                section disables them. Pass ``False`` to get the data exactly as
                stored in the file, for example to set your own modifiers before
                calling :meth:`modifiers_apply`.
            check: run the OpenCRG consistency check first and raise
                :class:`~pycrg.errors.OpenCRGCheckError` if it fails.

        Raises:
            FileNotFoundError: the file does not exist.
            IsADirectoryError: ``path`` is a directory.
            OpenCRGLoadError: OpenCRG cannot load the file; the exception's
                ``messages`` say why.
            OpenCRGCheckError: the check failed (with ``check=True``), or the
                file's modifiers are invalid.
        """
        fspath = _check_path(path)
        with _lock:
            with _messages.capture(exclusive=True) as messages:
                dataset_id = _native.loader_read_file(fspath)
            if dataset_id <= 0:
                raise OpenCRGLoadError(
                    _failure("Failed to load CRG file", os.fsdecode(fspath), messages), messages=messages
                )
            _messages.replay(messages)
            stale = _open_datasets.get(dataset_id)
            if stale is not None:  # pragma: no cover - only if _native is used directly
                stale.invalidate()
            handle = _DataSetHandle(dataset_id)
            _open_datasets[dataset_id] = handle

        dataset = object.__new__(cls)
        dataset._handle = handle
        dataset._path = os.path.abspath(fspath)
        dataset._header = None
        dataset._finalizer = weakref.finalize(
            dataset, _finalize_dataset, handle, f"pycrg.DataSet {os.fsdecode(fspath)!r}"
        )
        dataset._finalizer.atexit = False

        try:
            if check:
                dataset.check(raise_on_error=True)
            if apply_modifiers:
                dataset.modifiers_apply()
        except BaseException:
            dataset.close()
            raise
        return dataset

    # --- state -------------------------------------------------------------

    def _live(self) -> _DataSetHandle:
        handle = self._handle
        if not handle.alive:
            _raise_closed("DataSet")
        return handle

    @property
    def closed(self) -> bool:
        """Whether the data set has been closed or released."""
        return not self._handle.alive

    @property
    def dataset_id(self) -> int:
        """Native OpenCRG data set id (reused by OpenCRG after closing)."""
        return self._handle.id

    @property
    def path(self) -> str:
        """Absolute path of the loaded file."""
        return os.fsdecode(self._path)

    @property
    def header(self) -> CrgHeader:
        """The parsed header of the file (see :func:`pycrg.read_header`).

        It describes the file as written; modifiers do not change it. The file
        is read on first access.
        """
        if self._header is None:
            self._header = read_header(self._path)
        return self._header

    def close(self) -> None:
        """Release the data set and its contact points. Closing twice is a no-op."""
        self._finalizer.detach()
        _release_dataset(self._handle)

    def __enter__(self) -> DataSet:
        self._live()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def __repr__(self) -> str:
        state = "closed" if self.closed else f"id={self._handle.id}"
        return f"<pycrg.DataSet {state} path={self.path!r}>"

    # --- checks and information ---------------------------------------------

    def check(self, *, raise_on_error: bool = False) -> bool:
        """Run the OpenCRG consistency checks (options, modifiers, curvature).

        Returns whether the data set is valid; the reasons for a failure are
        logged as OpenCRG messages (see :func:`set_message_callback`). With
        ``raise_on_error=True``, a failed check raises
        :class:`~pycrg.errors.OpenCRGCheckError` instead, whose message and
        ``messages`` contain the reasons.
        """
        handle = self._live()
        with _messages.capture(exclusive=raise_on_error) as messages:
            ok = _native.check(handle.id)
        if raise_on_error:
            if not ok:
                raise OpenCRGCheckError(_failure("CRG data check failed", self.path, messages), messages=messages)
            _messages.replay(messages)
        return ok

    def format_header(self) -> str:
        """Return the header summary that :meth:`print_header` prints."""
        return self._format(_native.dataset_print_header)

    def format_channel_info(self) -> str:
        """Return the channel overview that :meth:`print_channel_info` prints."""
        return self._format(_native.dataset_print_channel_info)

    def format_road_info(self) -> str:
        """Return the road summary that :meth:`print_road_info` prints."""
        return self._format(_native.dataset_print_road_info)

    def format_modifiers(self) -> str:
        """Return the modifier list that :meth:`modifiers_print` prints."""
        return self._format(_native.dataset_modifiers_print)

    def print_header(self, file: IO[str] | None = None) -> None:
        """Print the OpenCRG header summary to ``file`` (default ``sys.stdout``)."""
        print(self.format_header(), end="", file=file if file is not None else sys.stdout)

    def print_channel_info(self, file: IO[str] | None = None) -> None:
        """Print the OpenCRG channel overview to ``file`` (default ``sys.stdout``)."""
        print(self.format_channel_info(), end="", file=file if file is not None else sys.stdout)

    def print_road_info(self, file: IO[str] | None = None) -> None:
        """Print the OpenCRG road summary to ``file`` (default ``sys.stdout``)."""
        print(self.format_road_info(), end="", file=file if file is not None else sys.stdout)

    def modifiers_print(self, file: IO[str] | None = None) -> None:
        """Print the current modifiers to ``file`` (default ``sys.stdout``)."""
        print(self.format_modifiers(), end="", file=file if file is not None else sys.stdout)

    def _format(self, function: Callable[[int], None]) -> str:
        handle = self._live()
        with _messages.collect_text(MSG_LEVEL_NOTICE) as messages:
            function(handle.id)
        return _messages.join_text(messages)

    def u_range(self) -> UV:
        """Return ``(u_min, u_max)``."""
        return _native.dataset_get_u_range(self._live().id)

    def v_range(self) -> UV:
        """Return ``(v_min, v_max)``."""
        return _native.dataset_get_v_range(self._live().id)

    def increments(self) -> UV:
        """Return ``(u_increment, v_increment)``; the v increment is 0 for
        explicitly positioned long sections with variable spacing."""
        return _native.dataset_get_increments(self._live().id)

    def closed_track_data(self) -> ClosedTrackData:
        """Return ``(ok, is_closed, u_min, u_max)`` for closed tracks.

        ``is_closed`` tells whether the reference line can be closed; ``u_min``
        and ``u_max`` are NaN otherwise.
        """
        ok, is_closed, u_min, u_max = _native.dataset_get_closed_track(self._live().id)
        return bool(ok), int(is_closed), float(u_min), float(u_max)

    def grid(self) -> CrgGrid:
        """Return the arrays of the data set as numpy arrays (requires numpy)."""
        np = _require_numpy()
        handle = self._live()
        nu, nv = _native.dataset_grid_shape(handle.id)
        u_min, _ = _native.dataset_get_u_range(handle.id)
        u_inc, _ = _native.dataset_get_increments(handle.id)
        arrays: dict[str, Any] = {}
        for name, shape in (
            ("v", (nv,)),
            ("z", (nu, nv)),
            ("x", (nu,)),
            ("y", (nu,)),
            ("phi", (nu,)),
            ("slope", (nu,)),
            ("bank", (nu,)),
            ("ref_z", (nu,)),
        ):
            array = np.empty(shape, dtype=np.float64)
            _native.dataset_grid_fill(handle.id, name, array)
            arrays[name] = array
        arrays["u"] = u_min + u_inc * np.arange(nu, dtype=np.float64)
        return CrgGrid(**arrays)

    # --- modifiers -----------------------------------------------------------

    def modifier_set_int(self, modifier_id: int, value: int) -> bool:
        """Set an integer modifier (``MOD_*``); returns whether it was accepted."""
        return _native.dataset_modifier_set_int(self._live().id, int(modifier_id), int(value))

    def modifier_set_double(self, modifier_id: int, value: float) -> bool:
        """Set a floating-point modifier (``MOD_*``); returns whether it was accepted."""
        return _native.dataset_modifier_set_double(self._live().id, int(modifier_id), float(value))

    def modifier_get_int(self, modifier_id: int) -> int | None:
        """Return an integer modifier, or ``None`` if it is not set."""
        found, value = _native.dataset_modifier_get_int(self._live().id, int(modifier_id))
        return int(value) if found else None

    def modifier_get_double(self, modifier_id: int) -> float | None:
        """Return a floating-point modifier, or ``None`` if it is not set."""
        found, value = _native.dataset_modifier_get_double(self._live().id, int(modifier_id))
        return float(value) if found else None

    def modifier_remove(self, modifier_id: int) -> bool:
        """Remove one modifier."""
        return _native.dataset_modifier_remove(self._live().id, int(modifier_id))

    def modifier_remove_all(self) -> bool:
        """Remove all modifiers."""
        return _native.dataset_modifier_remove_all(self._live().id)

    def modifier_set_default(self) -> None:
        """Replace the modifiers by OpenCRG's defaults (re-position the start of
        the reference line to the origin, keep the last value for NaNs)."""
        _native.dataset_modifier_set_default(self._live().id)

    def modifiers_apply(self) -> None:
        """Apply the current modifiers to the data, then remove them.

        As in the OpenCRG tools, the modifiers are completed with their
        defaults and validated first (``crgCheckMods``). Since applied modifiers
        are removed, calling this again only applies modifiers set since.
        :meth:`DataSet.open` calls this unless ``apply_modifiers=False``.

        Raises:
            OpenCRGCheckError: the modifiers are invalid or contradictory; the
                data set is left unchanged.
        """
        handle = self._live()
        with _messages.capture(exclusive=True) as messages:
            ok = _native.dataset_modifiers_apply(handle.id)
        if not ok:
            raise OpenCRGCheckError(_failure("Invalid CRG modifiers", self.path, messages), messages=messages)
        _messages.replay(messages)

    def option_set_default(self) -> None:
        """Reset the data set's default options, which new contact points copy."""
        _native.dataset_option_set_default(self._live().id)

    # --- contact points ------------------------------------------------------

    def create_contact_point(self) -> ContactPoint:
        """Create a :class:`ContactPoint` for evaluating this data set."""
        with _lock:
            handle = self._live()
            cp_id = _native.contact_point_create(handle.id)
            if cp_id < 0:
                raise OpenCRGError("Failed to create a contact point")
            cp_handle = _ContactPointHandle(cp_id, handle)
            handle.contact_points.add(cp_handle)
        contact_point = object.__new__(ContactPoint)
        contact_point._handle = cp_handle
        contact_point._dataset = self
        contact_point._finalizer = weakref.finalize(contact_point, _release_contact_point, cp_handle)
        contact_point._finalizer.atexit = False
        return contact_point


# ---------------------------------------------------------------------------
# ContactPoint
# ---------------------------------------------------------------------------


class ContactPoint(_NotCopyable):
    """An OpenCRG contact point: evaluation options plus a search history.

    Create it with :meth:`DataSet.create_contact_point`. It keeps its data set
    alive and is closed together with it.
    """

    __slots__ = ("_handle", "_dataset", "_finalizer", "__weakref__")

    _handle: _ContactPointHandle
    _dataset: DataSet
    _finalizer: weakref.finalize[..., ContactPoint]

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("ContactPoint objects are created with DataSet.create_contact_point()")

    def _live(self) -> _ContactPointHandle:
        handle = self._handle
        if not handle.alive:
            _raise_closed("ContactPoint")
        return handle

    @property
    def closed(self) -> bool:
        """Whether the contact point (or its data set) has been closed."""
        return not self._handle.alive

    @property
    def cp_id(self) -> int:
        """Native OpenCRG contact point id (reused by OpenCRG after closing)."""
        return self._handle.id

    @property
    def dataset(self) -> DataSet:
        """The data set this contact point evaluates."""
        return self._dataset

    def close(self) -> None:
        """Delete the contact point. Closing twice, or after the data set, is a no-op."""
        self._finalizer.detach()
        _release_contact_point(self._handle)

    def __enter__(self) -> ContactPoint:
        self._live()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def __repr__(self) -> str:
        state = "closed" if self.closed else f"id={self._handle.id}"
        return f"<pycrg.ContactPoint {state} dataset={self._dataset!r}>"

    # --- options -------------------------------------------------------------

    def option_set_int(self, option_id: int, value: int) -> bool:
        """Set an integer option (``CP_OPTION_*``); returns whether it was accepted."""
        return _native.cp_option_set_int(self._live().id, int(option_id), int(value))

    def option_set_double(self, option_id: int, value: float) -> bool:
        """Set a floating-point option (``CP_OPTION_*``); returns whether it was accepted."""
        return _native.cp_option_set_double(self._live().id, int(option_id), float(value))

    def option_get_int(self, option_id: int) -> int | None:
        """Return an integer option, or ``None`` if it is not set."""
        found, value = _native.cp_option_get_int(self._live().id, int(option_id))
        return int(value) if found else None

    def option_get_double(self, option_id: int) -> float | None:
        """Return a floating-point option, or ``None`` if it is not set."""
        found, value = _native.cp_option_get_double(self._live().id, int(option_id))
        return float(value) if found else None

    def option_remove(self, option_id: int) -> bool:
        """Remove one option (its default behaviour applies again)."""
        return _native.cp_option_remove(self._live().id, int(option_id))

    def option_remove_all(self) -> bool:
        """Remove all options."""
        return _native.cp_option_remove_all(self._live().id)

    def set_default_options(self) -> None:
        """Reset the options to OpenCRG's defaults."""
        _native.cp_set_default_options(self._live().id)

    def set_history(self, history_size: int) -> bool:
        """Set the size of the history used to speed up successive x/y queries."""
        return _native.cp_set_history(self._live().id, int(history_size))

    def format_options(self) -> str:
        """Return the option list that :meth:`options_print` prints."""
        handle = self._live()
        with _messages.collect_text(MSG_LEVEL_NOTICE) as messages:
            _native.cp_options_print(handle.id)
        return _messages.join_text(messages)

    def options_print(self, file: IO[str] | None = None) -> None:
        """Print the current options to ``file`` (default ``sys.stdout``)."""
        print(self.format_options(), end="", file=file if file is not None else sys.stdout)

    # --- evaluation ----------------------------------------------------------
    # The native functions raise OpenCRGEvaluationError for positions that
    # cannot be evaluated and for non-finite coordinates.

    def uv_to_z(self, u: float, v: float) -> float:
        """Evaluate the elevation ``z`` at ``(u, v)``."""
        handle = self._handle
        if not handle.alive:
            _raise_closed("ContactPoint")
        return _native.eval_uv_to_z(handle.id, u, v)

    def xy_to_z(self, x: float, y: float) -> float:
        """Evaluate the elevation ``z`` at ``(x, y)``."""
        handle = self._handle
        if not handle.alive:
            _raise_closed("ContactPoint")
        return _native.eval_xy_to_z(handle.id, x, y)

    def uv_to_xy(self, u: float, v: float) -> XY:
        """Transform ``(u, v)`` to ``(x, y)``."""
        handle = self._handle
        if not handle.alive:
            _raise_closed("ContactPoint")
        return _native.eval_uv_to_xy(handle.id, u, v)

    def xy_to_uv(self, x: float, y: float) -> UV:
        """Transform ``(x, y)`` to ``(u, v)``."""
        handle = self._handle
        if not handle.alive:
            _raise_closed("ContactPoint")
        return _native.eval_xy_to_uv(handle.id, x, y)

    def uv_to_pk(self, u: float, v: float) -> PK:
        """Evaluate heading and curvature ``(phi, curvature)`` at ``(u, v)``."""
        handle = self._handle
        if not handle.alive:
            _raise_closed("ContactPoint")
        return _native.eval_uv_to_pk(handle.id, u, v)

    def xy_to_pk(self, x: float, y: float) -> PK:
        """Evaluate heading and curvature ``(phi, curvature)`` at ``(x, y)``."""
        handle = self._handle
        if not handle.alive:
            _raise_closed("ContactPoint")
        return _native.eval_xy_to_pk(handle.id, x, y)

    def try_uv_to_z(self, u: float, v: float) -> float | None:
        """Like :meth:`uv_to_z`, but return ``None`` if the point cannot be evaluated."""
        handle = self._live()
        try:
            return _native.eval_uv_to_z(handle.id, u, v)
        except OpenCRGEvaluationError:
            return None

    def try_xy_to_z(self, x: float, y: float) -> float | None:
        """Like :meth:`xy_to_z`, but return ``None`` if the point cannot be evaluated."""
        handle = self._live()
        try:
            return _native.eval_xy_to_z(handle.id, x, y)
        except OpenCRGEvaluationError:
            return None

    def try_uv_to_xy(self, u: float, v: float) -> XY | None:
        """Like :meth:`uv_to_xy`, but return ``None`` if the point cannot be transformed."""
        handle = self._live()
        try:
            return _native.eval_uv_to_xy(handle.id, u, v)
        except OpenCRGEvaluationError:
            return None

    def try_xy_to_uv(self, x: float, y: float) -> UV | None:
        """Like :meth:`xy_to_uv`, but return ``None`` if the point cannot be transformed."""
        handle = self._live()
        try:
            return _native.eval_xy_to_uv(handle.id, x, y)
        except OpenCRGEvaluationError:
            return None

    def try_uv_to_pk(self, u: float, v: float) -> PK | None:
        """Like :meth:`uv_to_pk`, but return ``None`` if the point cannot be evaluated."""
        handle = self._live()
        try:
            return _native.eval_uv_to_pk(handle.id, u, v)
        except OpenCRGEvaluationError:
            return None

    def try_xy_to_pk(self, x: float, y: float) -> PK | None:
        """Like :meth:`xy_to_pk`, but return ``None`` if the point cannot be evaluated."""
        handle = self._live()
        try:
            return _native.eval_xy_to_pk(handle.id, x, y)
        except OpenCRGEvaluationError:
            return None

    # --- vectorised evaluation (numpy) ---------------------------------------

    def _many(self, op: int, a: ArrayLike, b: ArrayLike, outputs: int) -> list[FloatArray]:
        np = _require_numpy()
        a_array, b_array = np.broadcast_arrays(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))
        shape = a_array.shape
        a_flat = np.ascontiguousarray(a_array).reshape(-1)
        b_flat = np.ascontiguousarray(b_array).reshape(-1)
        out = [np.empty(a_flat.shape, dtype=np.float64) for _ in range(outputs)]
        _native.eval_many(op, self._live().id, a_flat, b_flat, out[0], out[1] if outputs == 2 else None)
        return [array.reshape(shape) for array in out]

    def uv_to_z_many(self, u: ArrayLike, v: ArrayLike) -> FloatArray:
        """Evaluate ``z`` for arrays of ``u`` and ``v`` (broadcast against each other).

        Returns a float64 array; points that cannot be evaluated are NaN.
        Requires numpy.
        """
        return self._many(_native.OP_UV_TO_Z, u, v, 1)[0]

    def xy_to_z_many(self, x: ArrayLike, y: ArrayLike) -> FloatArray:
        """Evaluate ``z`` for arrays of ``x`` and ``y``; see :meth:`uv_to_z_many`."""
        return self._many(_native.OP_XY_TO_Z, x, y, 1)[0]

    def uv_to_xy_many(self, u: ArrayLike, v: ArrayLike) -> tuple[FloatArray, FloatArray]:
        """Transform arrays of ``u`` and ``v`` to ``(x, y)`` arrays; see :meth:`uv_to_z_many`."""
        first, second = self._many(_native.OP_UV_TO_XY, u, v, 2)
        return first, second

    def xy_to_uv_many(self, x: ArrayLike, y: ArrayLike) -> tuple[FloatArray, FloatArray]:
        """Transform arrays of ``x`` and ``y`` to ``(u, v)`` arrays; see :meth:`uv_to_z_many`."""
        first, second = self._many(_native.OP_XY_TO_UV, x, y, 2)
        return first, second

    def uv_to_pk_many(self, u: ArrayLike, v: ArrayLike) -> tuple[FloatArray, FloatArray]:
        """Evaluate ``(phi, curvature)`` arrays for arrays of ``u`` and ``v``; see :meth:`uv_to_z_many`."""
        first, second = self._many(_native.OP_UV_TO_PK, u, v, 2)
        return first, second

    def xy_to_pk_many(self, x: ArrayLike, y: ArrayLike) -> tuple[FloatArray, FloatArray]:
        """Evaluate ``(phi, curvature)`` arrays for arrays of ``x`` and ``y``; see :meth:`uv_to_z_many`."""
        first, second = self._many(_native.OP_XY_TO_PK, x, y, 2)
        return first, second


# ---------------------------------------------------------------------------
# RoadSurface
# ---------------------------------------------------------------------------


class RoadSurface(_NotCopyable):
    """Convenience wrapper owning one :class:`DataSet` and one :class:`ContactPoint`.

    ``RoadSurface.open(path)`` loads, (optionally) checks and applies the
    modifiers like :meth:`DataSet.open`, then creates a contact point. Closing
    the road surface closes both.
    """

    __slots__ = ("_dataset", "_cp", "__weakref__")

    def __init__(self, dataset: DataSet, contact_point: ContactPoint | None = None) -> None:
        """Wrap ``dataset`` (and ``contact_point``, created if omitted).

        The road surface takes ownership: closing it closes the data set.
        """
        if not isinstance(dataset, DataSet):
            raise TypeError("dataset must be a pycrg.DataSet")
        if contact_point is None:
            contact_point = dataset.create_contact_point()
        elif contact_point.dataset is not dataset:
            raise ValueError("contact_point does not belong to dataset")
        self._dataset = dataset
        self._cp = contact_point

    @classmethod
    def open(cls, path: PathType, *, apply_modifiers: bool = True, check: bool = False) -> RoadSurface:
        """Load a CRG file and create a contact point; see :meth:`DataSet.open`."""
        dataset = DataSet.open(path, apply_modifiers=apply_modifiers, check=check)
        try:
            return cls(dataset)
        except BaseException:
            dataset.close()
            raise

    @property
    def dataset(self) -> DataSet:
        """The underlying data set."""
        return self._dataset

    @property
    def contact_point(self) -> ContactPoint:
        """The underlying contact point."""
        return self._cp

    @property
    def closed(self) -> bool:
        """Whether the road surface has been closed."""
        return self._dataset.closed or self._cp.closed

    @property
    def dataset_id(self) -> int:
        """Native data set id of the underlying data set."""
        return self._dataset.dataset_id

    @property
    def cp_id(self) -> int:
        """Native contact point id of the underlying contact point."""
        return self._cp.cp_id

    @property
    def path(self) -> str:
        """Absolute path of the loaded file."""
        return self._dataset.path

    @property
    def header(self) -> CrgHeader:
        """The parsed header of the file; see :attr:`DataSet.header`."""
        return self._dataset.header

    def close(self) -> None:
        """Close the contact point and the data set. Closing twice is a no-op."""
        self._cp.close()
        self._dataset.close()

    def __enter__(self) -> RoadSurface:
        if self.closed:
            _raise_closed("RoadSurface")
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<pycrg.RoadSurface {'closed' if self.closed else 'open'} path={self.path!r}>"

    # --- data set ------------------------------------------------------------

    def check(self, *, raise_on_error: bool = False) -> bool:
        """See :meth:`DataSet.check`."""
        return self._dataset.check(raise_on_error=raise_on_error)

    def u_range(self) -> UV:
        """See :meth:`DataSet.u_range`."""
        return self._dataset.u_range()

    def v_range(self) -> UV:
        """See :meth:`DataSet.v_range`."""
        return self._dataset.v_range()

    def increments(self) -> UV:
        """See :meth:`DataSet.increments`."""
        return self._dataset.increments()

    def closed_track_data(self) -> ClosedTrackData:
        """See :meth:`DataSet.closed_track_data`."""
        return self._dataset.closed_track_data()

    def grid(self) -> CrgGrid:
        """See :meth:`DataSet.grid`."""
        return self._dataset.grid()

    def format_header(self) -> str:
        """See :meth:`DataSet.format_header`."""
        return self._dataset.format_header()

    def format_channel_info(self) -> str:
        """See :meth:`DataSet.format_channel_info`."""
        return self._dataset.format_channel_info()

    def format_road_info(self) -> str:
        """See :meth:`DataSet.format_road_info`."""
        return self._dataset.format_road_info()

    def format_modifiers(self) -> str:
        """See :meth:`DataSet.format_modifiers`."""
        return self._dataset.format_modifiers()

    def print_header(self, file: IO[str] | None = None) -> None:
        """See :meth:`DataSet.print_header`."""
        self._dataset.print_header(file)

    def print_channel_info(self, file: IO[str] | None = None) -> None:
        """See :meth:`DataSet.print_channel_info`."""
        self._dataset.print_channel_info(file)

    def print_road_info(self, file: IO[str] | None = None) -> None:
        """See :meth:`DataSet.print_road_info`."""
        self._dataset.print_road_info(file)

    def modifiers_print(self, file: IO[str] | None = None) -> None:
        """See :meth:`DataSet.modifiers_print`."""
        self._dataset.modifiers_print(file)

    def modifier_set_int(self, modifier_id: int, value: int) -> bool:
        """See :meth:`DataSet.modifier_set_int`."""
        return self._dataset.modifier_set_int(modifier_id, value)

    def modifier_set_double(self, modifier_id: int, value: float) -> bool:
        """See :meth:`DataSet.modifier_set_double`."""
        return self._dataset.modifier_set_double(modifier_id, value)

    def modifier_get_int(self, modifier_id: int) -> int | None:
        """See :meth:`DataSet.modifier_get_int`."""
        return self._dataset.modifier_get_int(modifier_id)

    def modifier_get_double(self, modifier_id: int) -> float | None:
        """See :meth:`DataSet.modifier_get_double`."""
        return self._dataset.modifier_get_double(modifier_id)

    def modifier_remove(self, modifier_id: int) -> bool:
        """See :meth:`DataSet.modifier_remove`."""
        return self._dataset.modifier_remove(modifier_id)

    def modifier_remove_all(self) -> bool:
        """See :meth:`DataSet.modifier_remove_all`."""
        return self._dataset.modifier_remove_all()

    def modifier_set_default(self) -> None:
        """See :meth:`DataSet.modifier_set_default`."""
        self._dataset.modifier_set_default()

    def modifiers_apply(self) -> None:
        """See :meth:`DataSet.modifiers_apply`."""
        self._dataset.modifiers_apply()

    # --- contact point -------------------------------------------------------

    def option_set_int(self, option_id: int, value: int) -> bool:
        """See :meth:`ContactPoint.option_set_int`."""
        return self._cp.option_set_int(option_id, value)

    def option_set_double(self, option_id: int, value: float) -> bool:
        """See :meth:`ContactPoint.option_set_double`."""
        return self._cp.option_set_double(option_id, value)

    def option_get_int(self, option_id: int) -> int | None:
        """See :meth:`ContactPoint.option_get_int`."""
        return self._cp.option_get_int(option_id)

    def option_get_double(self, option_id: int) -> float | None:
        """See :meth:`ContactPoint.option_get_double`."""
        return self._cp.option_get_double(option_id)

    def option_remove(self, option_id: int) -> bool:
        """See :meth:`ContactPoint.option_remove`."""
        return self._cp.option_remove(option_id)

    def option_remove_all(self) -> bool:
        """See :meth:`ContactPoint.option_remove_all`."""
        return self._cp.option_remove_all()

    def set_default_options(self) -> None:
        """See :meth:`ContactPoint.set_default_options`."""
        self._cp.set_default_options()

    def format_options(self) -> str:
        """See :meth:`ContactPoint.format_options`."""
        return self._cp.format_options()

    def options_print(self, file: IO[str] | None = None) -> None:
        """See :meth:`ContactPoint.options_print`."""
        self._cp.options_print(file)

    def uv_to_z(self, u: float, v: float) -> float:
        """See :meth:`ContactPoint.uv_to_z`."""
        return self._cp.uv_to_z(u, v)

    def try_uv_to_z(self, u: float, v: float) -> float | None:
        """See :meth:`ContactPoint.try_uv_to_z`."""
        return self._cp.try_uv_to_z(u, v)

    def xy_to_z(self, x: float, y: float) -> float:
        """See :meth:`ContactPoint.xy_to_z`."""
        return self._cp.xy_to_z(x, y)

    def try_xy_to_z(self, x: float, y: float) -> float | None:
        """See :meth:`ContactPoint.try_xy_to_z`."""
        return self._cp.try_xy_to_z(x, y)

    def uv_to_xy(self, u: float, v: float) -> XY:
        """See :meth:`ContactPoint.uv_to_xy`."""
        return self._cp.uv_to_xy(u, v)

    def try_uv_to_xy(self, u: float, v: float) -> XY | None:
        """See :meth:`ContactPoint.try_uv_to_xy`."""
        return self._cp.try_uv_to_xy(u, v)

    def xy_to_uv(self, x: float, y: float) -> UV:
        """See :meth:`ContactPoint.xy_to_uv`."""
        return self._cp.xy_to_uv(x, y)

    def try_xy_to_uv(self, x: float, y: float) -> UV | None:
        """See :meth:`ContactPoint.try_xy_to_uv`."""
        return self._cp.try_xy_to_uv(x, y)

    def uv_to_pk(self, u: float, v: float) -> PK:
        """See :meth:`ContactPoint.uv_to_pk`."""
        return self._cp.uv_to_pk(u, v)

    def try_uv_to_pk(self, u: float, v: float) -> PK | None:
        """See :meth:`ContactPoint.try_uv_to_pk`."""
        return self._cp.try_uv_to_pk(u, v)

    def xy_to_pk(self, x: float, y: float) -> PK:
        """See :meth:`ContactPoint.xy_to_pk`."""
        return self._cp.xy_to_pk(x, y)

    def try_xy_to_pk(self, x: float, y: float) -> PK | None:
        """See :meth:`ContactPoint.try_xy_to_pk`."""
        return self._cp.try_xy_to_pk(x, y)

    def uv_to_z_many(self, u: ArrayLike, v: ArrayLike) -> FloatArray:
        """See :meth:`ContactPoint.uv_to_z_many`."""
        return self._cp.uv_to_z_many(u, v)

    def xy_to_z_many(self, x: ArrayLike, y: ArrayLike) -> FloatArray:
        """See :meth:`ContactPoint.xy_to_z_many`."""
        return self._cp.xy_to_z_many(x, y)

    def uv_to_xy_many(self, u: ArrayLike, v: ArrayLike) -> tuple[FloatArray, FloatArray]:
        """See :meth:`ContactPoint.uv_to_xy_many`."""
        return self._cp.uv_to_xy_many(u, v)

    def xy_to_uv_many(self, x: ArrayLike, y: ArrayLike) -> tuple[FloatArray, FloatArray]:
        """See :meth:`ContactPoint.xy_to_uv_many`."""
        return self._cp.xy_to_uv_many(x, y)

    def uv_to_pk_many(self, u: ArrayLike, v: ArrayLike) -> tuple[FloatArray, FloatArray]:
        """See :meth:`ContactPoint.uv_to_pk_many`."""
        return self._cp.uv_to_pk_many(u, v)

    def xy_to_pk_many(self, x: ArrayLike, y: ArrayLike) -> tuple[FloatArray, FloatArray]:
        """See :meth:`ContactPoint.xy_to_pk_many`."""
        return self._cp.xy_to_pk_many(x, y)
