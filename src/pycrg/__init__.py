"""Unofficial Python bindings for the ASAM OpenCRG C API.

Typical use::

    import pycrg

    with pycrg.DataSet.open("road.crg") as dataset:   # load, apply modifiers
        cp = dataset.create_contact_point()
        z = cp.uv_to_z(10.0, 0.5)

See :class:`DataSet`, :class:`ContactPoint`, :class:`RoadSurface`,
:func:`read_header` and :func:`write`.
"""

from . import constants, errors, experimental
from ._version import __version__
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
    "CrgGrid",
    "CrgHeader",
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
    "constants",
    "errors",
    "experimental",
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
