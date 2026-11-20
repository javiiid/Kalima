"""Route ``print`` output to the job that owns the current thread.

The web server used to capture a job's output with ``redirect_stdout``, which
replaces ``sys.stdout`` for the whole process. That works only while one job
runs at a time. Once two books translate together, every ``print`` in every
worker thread would land in whichever job redirected last.

This module installs one process-wide router instead. Each job binds its own
sink to the threads it owns; worker threads created by the translation
executor are bound through ``ThreadPoolExecutor(initializer=...)``. Any thread
without a binding writes to the real stream, so server diagnostics still show
up on the console.

``install()`` must be called from the server entry point, never at import
time: pytest replaces ``sys.stdout`` for capture, and a router installed at
import would hide test output.
"""
from __future__ import annotations

import io
import sys
import threading
from contextlib import contextmanager


_lock = threading.RLock()
_write_lock = threading.Lock()
_sinks: dict[int, io.TextIOBase] = {}
_installed = False
_original_stdout: io.TextIOBase | None = None
_original_stderr: io.TextIOBase | None = None


def _sink_for_current_thread() -> io.TextIOBase | None:
    with _lock:
        return _sinks.get(threading.get_ident())


class _Router(io.TextIOBase):
    """A ``sys.stdout`` replacement that dispatches per thread."""

    def __init__(self, fallback: io.TextIOBase) -> None:
        self._fallback = fallback

    def write(self, text: str) -> int:
        target = _sink_for_current_thread() or self._fallback
        with _write_lock:
            return target.write(text)

    def flush(self) -> None:
        target = _sink_for_current_thread() or self._fallback
        try:
            target.flush()
        except Exception:
            pass

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self) -> str:
        return getattr(self._fallback, "encoding", "utf-8")

    @property
    def buffer(self):
        return getattr(self._fallback, "buffer", None)

    def fileno(self) -> int:
        return self._fallback.fileno()


def install() -> None:
    """Replace ``sys.stdout``/``sys.stderr`` with the router once."""
    global _installed, _original_stdout, _original_stderr
    with _lock:
        if _installed:
            return
        _original_stdout = sys.stdout
        _original_stderr = sys.stderr
        sys.stdout = _Router(_original_stdout)
        sys.stderr = _Router(_original_stderr)
        _installed = True


def uninstall() -> None:
    """Restore the original streams. Tests use this; the server never does."""
    global _installed, _original_stdout, _original_stderr
    with _lock:
        if not _installed:
            return
        stdout, stderr = _original_stdout, _original_stderr
        _sinks.clear()
        _installed = False
    # Swap outside the lock: dropping the router's last reference runs its
    # ``flush``/``close``, which must not re-enter the lock we just held.
    sys.stdout = stdout
    sys.stderr = stderr


def bind(sink: io.TextIOBase) -> None:
    """Send this thread's output to ``sink`` until ``unbind``."""
    with _lock:
        _sinks[threading.get_ident()] = sink


def unbind() -> None:
    with _lock:
        _sinks.pop(threading.get_ident(), None)


@contextmanager
def capture(sink: io.TextIOBase):
    bind(sink)
    try:
        yield sink
    finally:
        unbind()
