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

from app.core import usage as usage_ledger


_lock = threading.RLock()
_write_lock = threading.Lock()
_sinks: dict[int, io.TextIOBase] = {}
# One event callback per job buffer. Worker threads are bound to the same
# buffer by ``ThreadPoolExecutor(initializer=bind, initargs=(sink,))``, so the
# callback is looked up by sink identity rather than by thread id.
_event_sinks: dict[int, object] = {}
# The usage ledger needs the same per-job identity, so it rides along with the
# sink: ``bind()`` applies it to whichever thread the sink is bound to.
_usage_contexts: dict[int, dict] = {}
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
        _event_sinks.clear()
        _usage_contexts.clear()
        _installed = False
    # Swap outside the lock: dropping the router's last reference runs its
    # ``flush``/``close``, which must not re-enter the lock we just held.
    sys.stdout = stdout
    sys.stderr = stderr


def bind(sink: io.TextIOBase) -> None:
    """Send this thread's output to ``sink`` until ``unbind``."""
    with _lock:
        _sinks[threading.get_ident()] = sink
        context = _usage_contexts.get(id(sink))
    if context:
        usage_ledger.bind(**context)


def unbind() -> None:
    with _lock:
        _sinks.pop(threading.get_ident(), None)
    usage_ledger.unbind()


def register_events(sink: io.TextIOBase, callback, usage: dict | None = None) -> None:
    """Route ``emit_event`` calls from any thread bound to ``sink``.

    ``usage`` is the job identity (``user_id``, ``job_id``, ``stage``) handed to
    :mod:`app.core.usage` whenever a thread binds this sink, so every provider
    call made on behalf of the job is attributed to it.
    """
    with _lock:
        _event_sinks[id(sink)] = callback
        if usage:
            _usage_contexts[id(sink)] = dict(usage)
        else:
            _usage_contexts.pop(id(sink), None)


def unregister_events(sink: io.TextIOBase) -> None:
    with _lock:
        _event_sinks.pop(id(sink), None)
        _usage_contexts.pop(id(sink), None)


def emit_event(event: str, message: str = "", level: str = "INFO", **data) -> None:
    """Emit a structured job event from the current thread's job, if any.

    The translator calls this from retry paths. A thread with no job binding
    (CLI, tests) is a no-op: logging must never become a reason a translation
    fails.
    """
    with _lock:
        sink = _sinks.get(threading.get_ident())
        callback = _event_sinks.get(id(sink)) if sink is not None else None
    if callback is None:
        return
    try:
        callback(event, message, level, data)
    except Exception:
        pass


@contextmanager
def capture(sink: io.TextIOBase):
    bind(sink)
    try:
        yield sink
    finally:
        unbind()
