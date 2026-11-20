"""Capacity-limited, fair scheduling for web translation jobs.

The web server used to wrap every run in one process-wide ``RUN_LOCK``: a
single book occupied the whole product, and a second user's job waited behind
it no matter how small it was. This scheduler replaces that lock with a fixed
number of worker slots.

Fairness is round-robin across users, not FIFO across jobs. A user with a
backlog cannot starve another user, and ``per_user_limit`` keeps one account
from owning every slot. Order inside one user is FIFO.

The scheduler owns the queue only. It never touches job state files, the
database, or the provider; ``runner`` is the existing job function, so the
translation engine stays exactly as it is.
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _user_id(job) -> int:
    return int(getattr(job, "user_id", 1) or 1)


class JobScheduler:
    """Run jobs on a fixed number of slots with per-user fairness.

    ``slots`` is the total number of jobs that may run at once. With the
    default of one, the scheduler reproduces the old serial behavior while the
    rest of the concurrency work lands. ``per_user_limit`` caps how many slots
    one account may hold; the default of one means a user never runs two books
    at the same time, which is the current product rule.
    """

    def __init__(self, slots: int = 1, per_user_limit: int = 1, runner=None) -> None:
        if runner is None:
            raise ValueError("JobScheduler requires a runner callable.")
        self._slots = max(1, int(slots))
        self._per_user_limit = max(1, int(per_user_limit))
        self._runner = runner
        self._cond = threading.Condition()
        self._queues: dict[int, deque[tuple[object, bool]]] = {}
        self._order: deque[int] = deque()
        self._running: dict[str, object] = {}
        self._running_by_user: dict[int, int] = {}
        self._queued_ids: set[str] = set()
        self._closed = False
        self._threads = [
            threading.Thread(
                target=self._worker,
                name=f"job-slot-{index + 1}",
                daemon=True,
            )
            for index in range(self._slots)
        ]
        for thread in self._threads:
            thread.start()

    # -- public API --------------------------------------------------------

    def submit(self, job, *, resume: bool = False) -> bool:
        """Queue one job. Returns False when it is already queued or running.

        Idempotence matters because a browser retry or a double-click must not
        start a second paid translation of the same book.
        """
        uid = _user_id(job)
        with self._cond:
            if self._closed or job.id in self._running or job.id in self._queued_ids:
                return False
            if not getattr(job, "queued_at", None):
                job.queued_at = _timestamp()
            queue = self._queues.get(uid)
            if queue is None:
                queue = self._queues[uid] = deque()
            if uid not in self._order:
                self._order.append(uid)
            queue.append((job, bool(resume)))
            self._queued_ids.add(job.id)
            self._cond.notify_all()
            return True

    def cancel(self, job_id: str) -> bool:
        """Remove a queued job. Returns False if it is already running."""
        with self._cond:
            if job_id in self._running:
                return False
            for uid, queue in list(self._queues.items()):
                for index, (job, _resume) in enumerate(queue):
                    if job.id != job_id:
                        continue
                    del queue[index]
                    self._queued_ids.discard(job_id)
                    if not queue:
                        self._queues.pop(uid, None)
                        try:
                            self._order.remove(uid)
                        except ValueError:
                            pass
                    self._cond.notify_all()
                    return True
            return False

    def stats(self) -> dict:
        with self._cond:
            queued_by_user = {
                uid: len(queue) for uid, queue in self._queues.items() if queue
            }
            return {
                "slots": self._slots,
                "per_user_limit": self._per_user_limit,
                "queued": sum(queued_by_user.values()),
                "running": len(self._running),
                "queued_by_user": queued_by_user,
                "running_by_user": dict(self._running_by_user),
            }

    def active_jobs(self, user_id: int | None = None) -> list:
        """Snapshot of jobs the scheduler is holding, queued or running.

        The caller gets the job objects themselves so it can apply its own
        notion of "still active" (the job's own ``status``) instead of trusting
        the queue alone: a job whose runner already wrote a terminal status but
        has not been reaped yet must not keep a user blocked.
        """
        with self._cond:
            jobs = list(self._running.values())
            for queue in self._queues.values():
                jobs.extend(job for job, _resume in queue)
        if user_id is None:
            return jobs
        return [job for job in jobs if _user_id(job) == int(user_id)]

    def shutdown(self, wait: bool = True) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        if wait:
            for thread in self._threads:
                thread.join(timeout=5)

    # -- internals ---------------------------------------------------------

    def _pick_locked(self):
        """Pop the next runnable job, rotating users for fairness.

        Every user is considered at most once per call, so a user with a long
        queue cannot be picked twice while another user waits.
        """
        scan = len(self._order)
        for _ in range(scan):
            uid = self._order.popleft()
            queue = self._queues.get(uid)
            if not queue:
                self._queues.pop(uid, None)
                continue
            if self._running_by_user.get(uid, 0) >= self._per_user_limit:
                self._order.append(uid)
                continue
            job, resume = queue.popleft()
            if queue:
                self._order.append(uid)
            else:
                self._queues.pop(uid, None)
            self._queued_ids.discard(job.id)
            self._running[job.id] = job
            self._running_by_user[uid] = self._running_by_user.get(uid, 0) + 1
            return job, resume
        return None

    def _take(self):
        with self._cond:
            while not self._closed:
                picked = self._pick_locked()
                if picked is not None:
                    return picked
                self._cond.wait()
        return None

    def _finish(self, job) -> None:
        uid = _user_id(job)
        with self._cond:
            self._running.pop(job.id, None)
            remaining = self._running_by_user.get(uid, 1) - 1
            if remaining > 0:
                self._running_by_user[uid] = remaining
            else:
                self._running_by_user.pop(uid, None)
            self._cond.notify_all()

    def _worker(self) -> None:
        while True:
            picked = self._take()
            if picked is None:
                return
            job, resume = picked
            try:
                self._runner(job, resume=resume)
            except BaseException:
                # The runner records its own failure on the job. A slot must
                # never die because one book raised.
                pass
            finally:
                self._finish(job)
