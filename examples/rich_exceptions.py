"""
End-to-end demo of the rich exception rendering.

Mirrors the `structlog.dev.RichTracebackFormatter` style:
- Boxed `Traceback (most recent call last)` header
- Source code window with the offending line marked by `▶`
- Locals block per frame

Run it:
    python examples/rich_exceptions.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make `src` importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / 'src'
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
from obserlog import LoggerConfig, LoggerFactory
from obserlog.core.exception_render import format_exception_pretty


# ---------------------------------------------------------------------------
# A small domain with a bug.
# ---------------------------------------------------------------------------
class SomeClass:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self) -> str:
        attrs = ", ".join(f"{k}={v!r}" for k, v in vars(self).items())
        return f"SomeClass({attrs})"


def make_call_stack_more_impressive(some_logger) -> None:
    """Intentionally buggy function — triggers a KeyError deep in the stack."""
    try:
        d = {"x": 42}
        print(SomeClass(d["y"], "foo"))  # ← KeyError on d["y"]
    except Exception:
        some_logger.exception("poor me")
        raise


def make_invoice(order_id: str, amount: float) -> str:
    """A second buggy function for visual comparison."""
    d = {"x": 42}
    return d["y"]  # ← KeyError on d["y"]


# ---------------------------------------------------------------------------
# Build two loggers: one for `some_logger`, one for `another_logger`.
# ---------------------------------------------------------------------------
config = LoggerConfig(
    service_name="show-off",
    level="DEBUG",
    directory="logs",
    console={"colors": True, "destination": "stdout"},
)

# ---------------------------------------------------------------------------
# The demo: emit a variety of log levels, then raise an exception and log it.
# ---------------------------------------------------------------------------
def main() -> None:
    with LoggerFactory(config) as factory:
        some_logger = factory.get_logger().bind(logger="some_logger")
        another_logger = factory.get_logger().bind(logger="another_logger")

        # Some colorized INFO/DEBUG lines
        some_logger.debug("debugging is hard", extra={"a_list": [1, 2, 3]})
        some_logger.info("informative!", extra={"some_key": "some_value"})
        some_logger.warning("uh-uh!")
        another_logger.info("a dict", extra={"a_dict": {"a": 42, "b": "foo"}})
        some_logger.error("omg")
        some_logger.critical("wtf")
        some_logger.info("what", extra={"what": SomeClass(x=1, y="z")})
        some_logger.info("where are the colors!?", extra={"colors": "gone"})
        some_logger.info("there they are!", extra={"colors": "back"})
        another_logger.error("poor me")

        # Now the headline: a real exception with the rich renderer.
        try:
            make_call_stack_more_impressive(some_logger)
        except KeyError:
            some_logger.error(
                "all better now!",
                exc_info=sys.exc_info(),
            )


if __name__ == "__main__":
    main()
