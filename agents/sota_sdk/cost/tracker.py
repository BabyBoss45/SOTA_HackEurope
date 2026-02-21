"""Per-job cost accumulator with pretty console logging."""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import ClassVar

logger = logging.getLogger(__name__)

# Cap how many job entries we keep to prevent unbounded memory growth.
_MAX_TRACKED_JOBS = 500


@dataclass
class CostEntry:
    vendor: str
    amount: float
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def is_llm(self) -> bool:
        return self.input_tokens > 0 or self.output_tokens > 0


class CostTracker:
    """Accumulates costs per job and logs to console.

    Thread-safe singleton — safe to call from async tasks and threads.
    """

    _instance: ClassVar[CostTracker | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._current_job_costs: OrderedDict[str, list[CostEntry]] = OrderedDict()
        self._entry_lock = threading.Lock()

    @classmethod
    def get(cls) -> CostTracker:
        """Return the singleton tracker instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append(self, job_id: str, entry: CostEntry) -> None:
        with self._entry_lock:
            self._current_job_costs.setdefault(job_id, []).append(entry)
            # Evict oldest tracked jobs if we exceed the cap
            while len(self._current_job_costs) > _MAX_TRACKED_JOBS:
                self._current_job_costs.popitem(last=False)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def log_llm_call(
        self,
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        job_id: str,
    ) -> None:
        entry = CostEntry(
            vendor="llm",
            amount=cost_usd,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self._append(job_id, entry)
        logger.info(
            "[%s] %s | %d+%d tokens | $%.4f | job #%s",
            agent_name, model, input_tokens, output_tokens, cost_usd, job_id,
        )

    def log_external_cost(
        self,
        agent_name: str,
        vendor: str,
        amount: float,
        job_id: str,
    ) -> None:
        entry = CostEntry(vendor=vendor, amount=amount)
        self._append(job_id, entry)
        logger.info("[%s] %s | $%.4f | job #%s", agent_name, vendor, amount, job_id)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def log_job_summary(
        self,
        agent_name: str,
        job_id: str,
        revenue_usdc: float,
        total_cost: float | None = None,
        duration_secs: float | None = None,
    ) -> None:
        with self._entry_lock:
            entries = self._current_job_costs.pop(job_id, [])

        if total_cost is None:
            total_cost = sum(e.amount for e in entries)

        llm_cost = sum(e.amount for e in entries if e.is_llm)
        external_entries = [e for e in entries if not e.is_llm]

        # Build cost breakdown string
        parts: list[str] = []
        if llm_cost > 0:
            parts.append(f"LLM ${llm_cost:.4f}")
        for ext in external_entries:
            parts.append(f"{ext.vendor} ${ext.amount:.4f}")
        breakdown = ", ".join(parts) if parts else "none"

        if revenue_usdc > 0:
            margin = (revenue_usdc - total_cost) / revenue_usdc * 100
        else:
            margin = -100.0 if total_cost > 0 else 0.0

        # Box content
        title = f" JOB #{job_id} COMPLETED "
        inner_lines = [
            f"Revenue:  ${revenue_usdc:.2f}",
            f"Cost:     ${total_cost:.4f} ({breakdown})",
            f"Margin:   {margin:.1f}%",
        ]
        if duration_secs is not None:
            inner_lines.append(f"Duration: {duration_secs:.1f}s")

        # Box width = widest content line + 2 (leading "| " and trailing " |")
        content_width = max(len(title) + 2, *(len(ln) + 2 for ln in inner_lines))

        # All lines are exactly content_width + 2 chars (for the border chars)
        border_top = f"┌─{title}{'─' * (content_width - len(title) - 1)}┐"
        border_bot = f"└{'─' * content_width}┘"

        box_lines = [border_top]
        for ln in inner_lines:
            box_lines.append(f"│ {ln}{' ' * (content_width - len(ln) - 1)}│")
        box_lines.append(border_bot)

        for line in box_lines:
            logger.info("[%s] %s", agent_name, line)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_job_total(self, job_id: str) -> float:
        with self._entry_lock:
            entries = self._current_job_costs.get(job_id, [])
            return sum(e.amount for e in entries)

    def reset(self) -> None:
        with self._entry_lock:
            self._current_job_costs.clear()
