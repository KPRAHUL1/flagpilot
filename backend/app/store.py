from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import ExperimentRun


class RunStore:
    """Thread-safe JSON persistence for FlagPilot experiment runs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def list_runs(self) -> list[ExperimentRun]:
        with self._lock:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            runs = [ExperimentRun(**item) for item in raw]
            runs.sort(key=lambda r: r.created_at, reverse=True)
            return runs

    def get_run(self, run_id: str) -> ExperimentRun | None:
        return next((r for r in self.list_runs() if r.id == run_id), None)

    def save_run(self, run: ExperimentRun) -> ExperimentRun:
        with self._lock:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            updated = [item for item in raw if item.get("id") != run.id]
            updated.insert(0, run.model_dump())
            self.path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
            return run
