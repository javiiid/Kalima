"""Small dependency-free JSONL logger used by translation jobs."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc


class StructuredLogger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def emit(
        self,
        event: str,
        message: str = "",
        level: str = "INFO",
        *,
        durable: bool = True,
        **fields: Any,
    ) -> dict[str, Any]:
        """Append one JSONL record.

        ``durable`` fsyncs after the write. Job events keep it (a crash must
        not lose committed progress); high-volume access logs pass
        ``durable=False`` so a per-request fsync never becomes the bottleneck.
        """
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level.upper(),
            "event": event,
            "message": message,
            **fields,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                if durable:
                    os.fsync(handle.fileno())
        return record


def get_job_logger(paths: dict) -> StructuredLogger:
    return StructuredLogger(paths.get("events_log") or Path(paths["job_dir"]) / "events.jsonl")


def get_app_logger(path: str | Path | None = None) -> StructuredLogger:
    """Application-level JSONL log (HTTP access + server errors)."""
    if path is None:
        from app.core.paths import ensure_dir

        path = ensure_dir("data") / "logs" / "app.jsonl"
    return StructuredLogger(path)
