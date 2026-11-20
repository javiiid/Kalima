"""Unit tests for the fair job scheduler.

These tests use a controlled runner instead of the translation pipeline: the
scheduler is about queueing and slots, so the fake blocks on events and lets
each test decide when a job finishes.
"""
import threading
import time

from app.jobs.scheduler import JobScheduler


class FakeJob:
    def __init__(self, job_id, user_id=1):
        self.id = job_id
        self.user_id = user_id
        self.queued_at = None


class ControlledRunner:
    def __init__(self):
        self._lock = threading.Lock()
        self._started = []
        self._finished = []
        self.release = {}

    def __call__(self, job, *, resume=False):
        with self._lock:
            self._started.append((job.id, resume))
            event = self.release.setdefault(job.id, threading.Event())
        event.wait(5)
        with self._lock:
            self._finished.append(job.id)

    def started(self):
        with self._lock:
            return list(self._started)

    def finished(self):
        with self._lock:
            return list(self._finished)

    def release_all(self):
        with self._lock:
            events = list(self.release.values())
        for event in events:
            event.set()


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_submit_is_idempotent_and_stamps_queued_at():
    runner = ControlledRunner()
    scheduler = JobScheduler(slots=1, per_user_limit=1, runner=runner)
    job = FakeJob("a")
    try:
        assert scheduler.submit(job) is True
        assert scheduler.submit(job) is False
        assert wait_for(lambda: runner.started() == [("a", False)])
        assert job.queued_at
    finally:
        runner.release_all()
        scheduler.shutdown()


def test_resume_flag_reaches_the_runner():
    runner = ControlledRunner()
    scheduler = JobScheduler(slots=1, per_user_limit=1, runner=runner)
    try:
        scheduler.submit(FakeJob("a"), resume=True)
        assert wait_for(lambda: runner.started() == [("a", True)])
    finally:
        runner.release_all()
        scheduler.shutdown()


def test_per_user_limit_keeps_the_second_job_queued():
    runner = ControlledRunner()
    scheduler = JobScheduler(slots=2, per_user_limit=1, runner=runner)
    try:
        scheduler.submit(FakeJob("a1"))
        scheduler.submit(FakeJob("a2"))
        assert wait_for(lambda: runner.started() == [("a1", False)])
        time.sleep(0.05)
        assert runner.started() == [("a1", False)]
        assert scheduler.stats()["queued"] == 1
        runner.release["a1"].set()
        assert wait_for(lambda: runner.started() == [("a1", False), ("a2", False)])
    finally:
        runner.release_all()
        scheduler.shutdown()


def test_round_robin_is_fair_across_users():
    runner = ControlledRunner()
    scheduler = JobScheduler(slots=1, per_user_limit=1, runner=runner)
    jobs = [
        FakeJob("a1", 1),
        FakeJob("a2", 1),
        FakeJob("b1", 2),
        FakeJob("b2", 2),
    ]
    try:
        for job in jobs:
            scheduler.submit(job)
        order = []
        for _ in jobs:
            assert wait_for(lambda: len(runner.started()) > len(order))
            order.append(runner.started()[len(order)][0])
            runner.release[order[-1]].set()
        # FIFO inside a user, round-robin between users: A1, B1, A2, B2.
        assert order == ["a1", "b1", "a2", "b2"]
    finally:
        runner.release_all()
        scheduler.shutdown()


def test_cancel_removes_a_queued_job_but_not_a_running_one():
    runner = ControlledRunner()
    scheduler = JobScheduler(slots=1, per_user_limit=1, runner=runner)
    try:
        scheduler.submit(FakeJob("running"))
        scheduler.submit(FakeJob("queued"))
        assert wait_for(lambda: runner.started() == [("running", False)])
        assert scheduler.cancel("queued") is True
        assert scheduler.cancel("running") is False
        runner.release["running"].set()
        assert wait_for(lambda: runner.finished() == ["running"])
        time.sleep(0.05)
        assert runner.started() == [("running", False)]
        assert scheduler.stats()["queued"] == 0
    finally:
        runner.release_all()
        scheduler.shutdown()


def test_two_users_run_at_the_same_time():
    runner = ControlledRunner()
    scheduler = JobScheduler(slots=2, per_user_limit=1, runner=runner)
    try:
        scheduler.submit(FakeJob("a", 1))
        scheduler.submit(FakeJob("b", 2))
        assert wait_for(lambda: len(runner.started()) == 2)
        assert {job_id for job_id, _ in runner.started()} == {"a", "b"}
        assert scheduler.stats()["running"] == 2
    finally:
        runner.release_all()
        scheduler.shutdown()


def test_stats_reports_queued_and_running_per_user():
    runner = ControlledRunner()
    scheduler = JobScheduler(slots=1, per_user_limit=1, runner=runner)
    try:
        scheduler.submit(FakeJob("a1", 1))
        scheduler.submit(FakeJob("a2", 1))
        scheduler.submit(FakeJob("b1", 2))
        assert wait_for(lambda: scheduler.stats()["running"] == 1)
        stats = scheduler.stats()
        assert stats["slots"] == 1
        assert stats["per_user_limit"] == 1
        assert stats["queued_by_user"] == {1: 1, 2: 1}
        assert stats["running_by_user"] == {1: 1}
    finally:
        runner.release_all()
        scheduler.shutdown()
