"""Chrome Trace Event Format recording for build edge timings.

Format: https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "TraceRecorder",
    "edge_category",
    "write_trace",
]


def edge_category(edge_id: str) -> str:
    """Category from an edge id prefix (``compile:…``, ``wheel:…``, ``link:…``)."""
    prefix, sep, _ = edge_id.partition(":")
    return prefix if sep else "build"


@dataclass
class TraceRecorder:
    """Collects complete (``ph: X``) events for Chrome / Perfetto viewers."""

    pid: int = 1
    process_name: str = "rosetta-build"
    _origin_s: float = field(default_factory=time.perf_counter, init=False, repr=False)
    _events: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _named_tids: set[int] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        self._events.append({
            "name": "process_name",
            "ph": "M",
            "pid": self.pid,
            "args": {"name": self.process_name},
        })

    def now_us(self) -> float:
        """Tracing-clock microseconds since this recorder was created."""
        return (time.perf_counter() - self._origin_s) * 1_000_000.0

    def complete(
        self,
        *,
        name: str,
        cat: str,
        tid: int,
        ts: float,
        dur: float,
        args: dict[str, Any] | None = None,
    ) -> None:
        """Record a complete duration event (phase ``X``)."""
        self._ensure_thread_name(tid)
        event: dict[str, Any] = {
            "name": name,
            "cat": cat,
            "ph": "X",
            "ts": ts,
            "dur": max(dur, 0.0),
            "pid": self.pid,
            "tid": tid,
        }
        if args:
            event["args"] = args
        self._events.append(event)

    def events(self) -> list[dict[str, Any]]:
        """Return a copy of recorded events (metadata + complete slices)."""
        return list(self._events)

    def to_json(self) -> str:
        """Serialize as a JSON array (Chrome Trace Event Format)."""
        return json.dumps(self._events, indent=2) + "\n"

    def write(self, path: Path) -> None:
        """Write the JSON array to ``path``."""
        write_trace(self, path)

    def _ensure_thread_name(self, tid: int) -> None:
        if tid in self._named_tids:
            return
        self._named_tids.add(tid)
        self._events.append({
            "name": "thread_name",
            "ph": "M",
            "pid": self.pid,
            "tid": tid,
            "args": {"name": f"job {tid}"},
        })


def write_trace(recorder: TraceRecorder, path: Path) -> None:
    """Write ``recorder`` as Chrome Trace Event JSON to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(recorder.to_json(), encoding="utf-8")
