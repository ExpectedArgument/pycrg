"""Unofficial Python bindings for the ASAM OpenCRG C API.

Typical use::

    import pycrg

    with pycrg.DataSet.open("road.crg") as dataset:   # load, apply modifiers
        cp = dataset.create_contact_point()
        z = cp.uv_to_z(10.0, 0.5)

See :class:`DataSet`, :class:`ContactPoint`, :class:`RoadSurface`,
:func:`read_header`, :func:`write`, :func:`find_peaks` and :func:`compare`.
"""

from . import constants, errors, experimental
from ._version import __version__
from .analysis import CrgComparison, CrgPeaks, compare, find_peaks
from .api import (
    ContactPoint,
    CrgGrid,
    DataSet,
    MessageCallback,
    RoadSurface,
    clear_callbacks,
    clear_message_callback,
    get_message_level,
    get_release_info,
    is_message_printable,
    mem_release,
    msg_print,
    set_max_log_messages,
    set_max_warn_messages,
    set_message_callback,
    set_message_level,
)
from .constants import *  # noqa: F403
from .constants import __all__ as _constants_all
from .errors import (
    OpenCRGCheckError,
    OpenCRGClosedError,
    OpenCRGError,
    OpenCRGEvaluationError,
    OpenCRGLoadError,
)
from .header import CrgChannel, CrgHeader, read_header
from .writer import write

__all__ = [
    "__version__",
    "ContactPoint",
    "CrgChannel",
    "CrgComparison",
    "CrgGrid",
    "CrgHeader",
    "CrgPeaks",
    "DataSet",
    "MessageCallback",
    "OpenCRGCheckError",
    "OpenCRGClosedError",
    "OpenCRGError",
    "OpenCRGEvaluationError",
    "OpenCRGLoadError",
    "RoadSurface",
    "clear_callbacks",
    "clear_message_callback",
    "compare",
    "constants",
    "errors",
    "experimental",
    "find_peaks",
    "get_message_level",
    "get_release_info",
    "is_message_printable",
    "mem_release",
    "msg_print",
    "read_header",
    "set_max_log_messages",
    "set_max_warn_messages",
    "set_message_callback",
    "set_message_level",
    "write",
    *_constants_all,
]
