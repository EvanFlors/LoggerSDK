"""Tests for the queue pipeline."""
from __future__ import annotations

import contextlib
import logging
import time
from pathlib import Path

from obserlog.config import LoggerConfig
from obserlog.handlers.queue import build_queue_pipeline


def test_build_queue_pipeline_returns_handler_and_listener():
    cfg = LoggerConfig(directory=str(Path("/tmp")))
    qh, listener = build_queue_pipeline(cfg, [])
    assert qh is not None
    assert listener is not None
    assert qh.filters  # OverflowFilter attached


def test_pipeline_actually_drains_records(tmp_path: Path):
    """
    Wire a real rotating-file sink through the pipeline and verify that
    a `log.info()` call lands in the file (proving the listener thread
    picked it up and the queue drained).
    """
    from obserlog.handlers.rotating_file import make_rotating_file_handler

    cfg = LoggerConfig(service_name="pipe", directory=str(tmp_path))
    sink = make_rotating_file_handler(cfg)
    qh, listener = build_queue_pipeline(cfg, [sink])

    root = logging.getLogger("pipe")
    root.setLevel(logging.INFO)
    root.addHandler(qh)
    listener.start()
    try:
        root.info("hello")
        # Give the listener a moment to drain.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            files = list(tmp_path.glob("pipe.log*"))
            if any(f.stat().st_size > 0 for f in files):
                break
            time.sleep(0.05)
        content = (tmp_path / "pipe.log").read_text()
        assert "hello" in content
    finally:
        listener.stop()
        for h in list(root.handlers):
            with contextlib.suppress(Exception):
                h.close()
            root.removeHandler(h)
