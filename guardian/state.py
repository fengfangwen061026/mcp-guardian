from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class ToolState:
    consecutive_failures: int = 0
    failure_signatures: list[str] = field(default_factory=list)
    error_type_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_calls: int = 0
    total_successes: int = 0
    circuit_state: str = "CLOSED"
    last_signature: str = ""

    @property
    def failure_sigs(self) -> list[str]:
        return self.failure_signatures

    @failure_sigs.setter
    def failure_sigs(self, value: list[str]) -> None:
        self.failure_signatures = value


@dataclass
class SessionState:
    session_id: str
    model_hint: str = "_default"
    _tools: dict[str, ToolState] = field(default_factory=lambda: defaultdict(ToolState))
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    knowledge_hits: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_prechecks: int = 0
    ack_successes: int = 0
    pending_fallbacks: dict[str, dict] = field(default_factory=dict)

    def get_lock(self, tool_name: str) -> asyncio.Lock:
        if tool_name not in self._locks:
            self._locks[tool_name] = asyncio.Lock()
        return self._locks[tool_name]

    def get_state(self, tool_name: str) -> ToolState:
        return self._tools[tool_name]
