# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
from contextvars import ContextVar
import uuid

trace_id_var = ContextVar("trace_id", default=None)
span_id_var = ContextVar("span_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_id() -> str:
    return uuid.uuid4().hex
