from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PolicyConfigError(Exception):
    pass


@dataclass(frozen=True)
class SensitiveRule:
    action: str
    patterns: tuple[str, ...]
    risk: float = 0.86
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class BashRule:
    decision: str
    patterns: tuple[str, ...]
    risk: float = 0.6
    reasons: tuple[str, ...] = ()
    category: str = "POLICY"
    safer_alternative: str | None = None


@dataclass(frozen=True)
class GuardianPolicy:
    roots: tuple[Path, ...] = ()
    sensitive_rules: tuple[SensitiveRule, ...] = ()
    bash_rules: tuple[BashRule, ...] = ()
    source_files: tuple[str, ...] = field(default_factory=tuple)


def load_policy(start_path: str | Path | None = None) -> GuardianPolicy:
    roots = _env_roots()
    files = _policy_files(start_path)
    data: dict[str, Any] = {}
    loaded: list[str] = []
    for path in files:
        if not path.exists():
            continue
        loaded.append(str(path))
        data = _deep_merge(data, _read_json(path), replace_policy_lists=path.name == "policy.local.json")
    file_roots = _parse_roots(data.get("roots", []), files[-1].parent.parent if files else Path.cwd())
    return GuardianPolicy(
        roots=roots or file_roots,
        sensitive_rules=tuple(_parse_sensitive(data.get("sensitive_paths", []))),
        bash_rules=tuple(_parse_bash(data.get("bash", {}))),
        source_files=tuple(loaded),
    )


def policy_error(error: Exception) -> dict:
    return {"success": False, "error": f"PolicyConfigError:{error}", "error_class": "MODEL_ERROR", "error_type": "PolicyConfigError"}


def _env_roots() -> tuple[Path, ...]:
    raw = os.environ.get("GUARDIAN_ROOTS") or os.environ.get("GUARDIAN_ROOT", "")
    roots = []
    for item in raw.split(os.pathsep):
        if item.strip():
            roots.append(Path(item).expanduser().resolve())
    return tuple(roots)


def _policy_files(start_path: str | Path | None) -> list[Path]:
    candidates: list[Path] = []
    if start_path is not None:
        candidates.append(Path(start_path).expanduser())
    candidates.append(Path(os.getcwd()).expanduser())
    for candidate in candidates:
        base = candidate.parent if candidate.is_file() else candidate
        base = base.resolve()
        for current in (base, *base.parents):
            guardian_dir = current / ".guardian"
            if guardian_dir.exists():
                return [guardian_dir / "policy.json", guardian_dir / "policy.local.json"]
    base = candidates[-1].resolve()
    return [base / ".guardian" / "policy.json", base / ".guardian" / "policy.local.json"]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyConfigError(f"{path}:{exc.msg}") from exc
    if not isinstance(data, dict):
        raise PolicyConfigError(f"{path}:root must be object")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any], replace_policy_lists: bool = False) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if replace_policy_lists and key in {"sensitive_paths", "bash"}:
            merged[key] = value
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value, replace_policy_lists)
        else:
            merged[key] = value
    return merged


def _parse_roots(value: Any, base_dir: Path) -> tuple[Path, ...]:
    if value in (None, []):
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PolicyConfigError("roots must be a string array")
    return tuple((base_dir / item).expanduser().resolve() if not Path(item).expanduser().is_absolute() else Path(item).expanduser().resolve() for item in value)


def _parse_sensitive(value: Any) -> list[SensitiveRule]:
    if value in (None, []):
        return []
    if isinstance(value, dict):
        items = []
        for action in ("deny", "ask", "allow"):
            for pattern in _string_list(value.get(action, []), f"sensitive_paths.{action}"):
                items.append({"action": action, "patterns": [pattern]})
        value = items
    if not isinstance(value, list):
        raise PolicyConfigError("sensitive_paths must be an array or object")
    rules = []
    for item in value:
        if not isinstance(item, dict):
            raise PolicyConfigError("sensitive_paths entries must be objects")
        action = item.get("action")
        if action not in {"allow", "ask", "deny"}:
            raise PolicyConfigError("sensitive path action must be allow, ask, or deny")
        rules.append(SensitiveRule(action, tuple(_string_list(item.get("patterns", []), "sensitive_paths.patterns")), _float_value(item.get("risk", 0.86), "sensitive_paths.risk"), tuple(_string_list(item.get("reasons", []), "sensitive_paths.reasons"))))
    return rules


def _parse_bash(value: Any) -> list[BashRule]:
    if value in (None, {}):
        return []
    if not isinstance(value, dict):
        raise PolicyConfigError("bash must be an object")
    rules = []
    for decision in ("allow", "ask", "deny"):
        for item in _bash_items(value.get(decision, []), f"bash.{decision}"):
            rules.append(BashRule(decision, tuple(_string_list(item.get("patterns", []), f"bash.{decision}.patterns")), _float_value(item.get("risk", _default_risk(decision)), f"bash.{decision}.risk"), tuple(_string_list(item.get("reasons", []), f"bash.{decision}.reasons")), str(item.get("category", "POLICY")), item.get("safer_alternative")))
    return rules


def _bash_items(value: Any, label: str) -> list[dict[str, Any]]:
    if value in (None, []):
        return []
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return [{"patterns": [item]} for item in value]
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    raise PolicyConfigError(f"{label} must be string array or object array")


def _string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise PolicyConfigError(f"{label} must be string or string array")


def _float_value(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise PolicyConfigError(f"{label} must be numeric") from exc


def _default_risk(decision: str) -> float:
    return {"allow": 0.1, "ask": 0.75, "deny": 0.95}[decision]
