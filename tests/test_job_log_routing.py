"""Per-job log routing: two jobs must never share a log buffer."""
import io
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from app.core import job_log


def _with_router(test):
    fallback = io.StringIO()
    original = sys.stdout
    sys.stdout = fallback
    job_log.install()
    try:
        test(fallback)
    finally:
        job_log.uninstall()
        sys.stdout = original


def test_each_thread_writes_to_its_own_sink():
    def run(fallback):
        first, second = io.StringIO(), io.StringIO()

        def worker(sink, text):
            job_log.bind(sink)
            try:
                print(text)
            finally:
                job_log.unbind()

        threads = [
            threading.Thread(target=worker, args=(first, "alpha")),
            threading.Thread(target=worker, args=(second, "beta")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert first.getvalue() == "alpha\n"
        assert second.getvalue() == "beta\n"
        assert fallback.getvalue() == ""

    _with_router(run)


def test_unbound_thread_uses_the_real_stream():
    def run(fallback):
        print("console line")
        assert "console line" in fallback.getvalue()

    _with_router(run)


def test_executor_workers_are_bound_through_the_initializer():
    def run(fallback):
        sink = io.StringIO()
        with ThreadPoolExecutor(
            max_workers=2,
            initializer=job_log.bind,
            initargs=(sink,),
        ) as pool:
            list(pool.map(lambda _: print("worker line"), range(2)))
        assert sink.getvalue().count("worker line") == 2
        assert fallback.getvalue() == ""

    _with_router(run)


def test_capture_binds_and_unbinds_the_current_thread():
    def run(fallback):
        sink = io.StringIO()
        with job_log.capture(sink):
            print("inside")
        print("outside")
        assert "inside" in sink.getvalue()
        assert "outside" in fallback.getvalue()

    _with_router(run)


def test_stderr_is_routed_too():
    def run(fallback):
        sink = io.StringIO()
        with job_log.capture(sink):
            print("to stderr", file=sys.stderr)
        assert "to stderr" in sink.getvalue()

    _with_router(run)
