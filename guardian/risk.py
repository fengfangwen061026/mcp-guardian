from __future__ import annotations

import re

PRESET_PATTERNS = {
    "dangerous_bash": [re.compile(r"\brm\s+-rf\b"), re.compile(r"\bdd\s+if=/dev/")],
    "privileged_shell": [re.compile(r"\b" + "su" + r"do\b")],
    "network_subshell": [re.compile(r"\$\([^)]*\b(curl|wget|nc|netcat)\b")],
    "system_write": [re.compile(r"^/(etc|usr|bin|sbin|lib)/")],
}


def compute_risk(tool_name: str, params: dict) -> float:
    if tool_name == "guardian_run_bash":
        cmd = params.get("command", "") or ""
        if any(p.search(cmd) for p in PRESET_PATTERNS["dangerous_bash"] + PRESET_PATTERNS["privileged_shell"]):
            return 0.95
        if any(p.search(cmd) for p in PRESET_PATTERNS["network_subshell"]):
            return 0.9
        return 0.25 if any(x in cmd for x in [">", "|", ";", "$(", "`"]) else 0.1
    if tool_name in {"guardian_write_file", "guardian_edit_file"}:
        path = params.get("path", "") or ""
        if any(p.search(path) for p in PRESET_PATTERNS["system_write"]):
            return 0.9
        return 0.45
    return 0.05
