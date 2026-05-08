from __future__ import annotations

import fnmatch
import shlex
from dataclasses import dataclass

from .policy_loader import load_policy


@dataclass(frozen=True)
class BashDecision:
    decision: str
    risk: float
    reasons: list[str]
    category: str
    safer_alternative: str | None = None

    def to_dict(self) -> dict:
        result = {"decision": self.decision, "risk": self.risk, "reasons": self.reasons, "category": self.category}
        if self.safer_alternative:
            result["safer_alternative"] = self.safer_alternative
        return result


def classify_command(command: str, policy_path: str | None = None) -> BashDecision:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return BashDecision("ask", 0.6, ["命令无法安全解析"], "UNKNOWN")
    return _classify(tokens, command, policy_path)


def classify_argv(argv: list[str], policy_path: str | None = None) -> BashDecision:
    return _classify(argv, " ".join(shlex.quote(part) for part in argv), policy_path)


def needs_description(decision: BashDecision) -> bool:
    return decision.decision == "ask" and decision.risk >= 0.6


def description_mismatch(description: str, decision: BashDecision) -> bool:
    desc = description.lower()
    if decision.category in {"DESTRUCTIVE", "PRIVILEGED"} and any(word in desc for word in ("test", "status", "diff", "read", "list")):
        return True
    return False


def _classify(tokens: list[str], command_repr: str, policy_path: str | None = None) -> BashDecision:
    if not tokens:
        return BashDecision("ask", 0.5, ["空命令"], "UNKNOWN")

    executable = tokens[0].split("/")[-1]
    text = command_repr.lower()

    hard_deny = _hard_deny(tokens)
    if hard_deny is not None:
        return hard_deny

    policy_decision = _policy_decision(command_repr, policy_path)
    if policy_decision is not None:
        return policy_decision

    if executable == "git" and len(tokens) >= 2:
        sub = tokens[1]
        if sub in {"status", "diff", "log", "show"}:
            return BashDecision("allow", 0.1, ["Git 只读操作"], "SAFE_READONLY")
        if sub == "clean" and any("f" in part and "d" in part for part in tokens[2:] if part.startswith("-")):
            return BashDecision("ask", 0.8, ["git clean 会删除未跟踪文件"], "DESTRUCTIVE", "先执行 git clean -ndx 预览。")
        if sub == "reset" and "--hard" in tokens:
            return BashDecision("ask", 0.85, ["git reset --hard 会丢弃本地修改"], "DESTRUCTIVE", "先查看 git status 和 git diff。")
        if sub == "push" and any(part in {"--force", "-f", "--force-with-lease"} for part in tokens[2:]):
            return BashDecision("ask", 0.85, ["force push 会改写远端历史"], "DESTRUCTIVE", "确认目标分支和远端状态。")

    if executable in {"pytest", "tox", "nox"} or tokens[:2] in (["python", "-m"], ["python3", "-m"]):
        return BashDecision("allow", 0.2, ["测试或 Python 开发命令"], "SAFE_DEV")
    if executable in {"npm", "pnpm", "yarn"} and len(tokens) >= 2 and tokens[1] in {"test", "run"}:
        return BashDecision("allow", 0.2, ["前端测试命令"], "SAFE_DEV")

    if executable in {"rm", "mv", "chmod", "chown"} or "rm -rf" in text:
        return BashDecision("ask", 0.75, ["文件系统破坏性或权限修改操作"], "DESTRUCTIVE", "先列出目标并缩小路径范围。")

    if executable in {"pwd", "ls", "true", "false", "echo", "printf", "date", "whoami"}:
        return BashDecision("allow", 0.05, ["低风险只读/输出命令"], "SAFE_READONLY")

    return BashDecision("allow", 0.35, ["未命中高风险规则"], "UNKNOWN")


def _hard_deny(tokens: list[str]) -> BashDecision | None:
    executable = tokens[0].split("/")[-1]
    if executable in {"sudo", "su"}:
        return BashDecision("deny", 0.95, ["禁止提权命令"], "PRIVILEGED")
    if "|" in tokens and _pipes_to_interpreter(tokens):
        return BashDecision("deny", 0.95, ["网络或文本输出通过管道进入解释器"], "DESTRUCTIVE", "先下载到文件并人工审查内容。")
    if ("curl" in tokens or "wget" in tokens) and any(part in {"bash", "sh", "zsh", "python", "python3", "node"} for part in tokens):
        return BashDecision("deny", 0.95, ["下载内容可能被直接执行"], "DESTRUCTIVE", "先保存脚本并审查 diff。")
    if executable == "docker" and ("--privileged" in tokens or "-v" in tokens and "/:/host" in tokens):
        return BashDecision("deny", 0.9, ["Docker 容器获得宿主高权限或挂载根目录"], "PRIVILEGED")
    return None


def _policy_decision(command_repr: str, policy_path: str | None = None) -> BashDecision | None:
    policy = load_policy(policy_path)
    for rule in policy.bash_rules:
        if not any(fnmatch.fnmatch(command_repr, pattern) for pattern in rule.patterns):
            continue
        return BashDecision(rule.decision, rule.risk, list(rule.reasons) or [f"项目 bash policy {rule.decision}"], rule.category, rule.safer_alternative)
    return None


def _pipes_to_interpreter(tokens: list[str]) -> bool:
    interpreters = {"bash", "sh", "zsh", "python", "python3", "node", "perl", "ruby"}
    return any(token == "|" and i + 1 < len(tokens) and tokens[i + 1] in interpreters for i, token in enumerate(tokens))
