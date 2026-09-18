from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TurnMetrics:
    started_at: float = field(default_factory=time.perf_counter)
    marks: dict[str, float] = field(default_factory=dict)

    def mark(self, name: str) -> None:
        self.marks[name] = (time.perf_counter() - self.started_at) * 1000

    def snapshot(self) -> dict[str, float]:
        return {key: round(value, 2) for key, value in self.marks.items()}

