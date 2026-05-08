from __future__ import annotations

import asyncio
import os
import re
import shlex

_BLOCKED_COMMANDS = [
    (r"\bmkfs\b", "mkfs 格式化磁盘"),
    (r"\bdd\s+if=/dev/", "dd 原始磁盘写入"),
    (r":\(\)\s*\{.*\|.*\}", "fork bomb"),
    (r"\brm\s+(-\w*[rf]\w*\s+){1,2}\s*/$", "rm -rf /"),
    (r"\brm\s+(-\w*[rf]\w*\s+){1,2}\s*~/?$", "rm -rf ~/"),
    (r">\s*~?/?(etc|usr|bin|sbin|lib)/", "写入系统目录"),
    (r">\s*~/\.(bash|zsh|profile|bashrc|zshrc)", "覆写 shell 配置"),
]
_UNICODE_BYPASS = ["\u200b", "\u200c", "\u200d", "\ufeff", "\r"]
_SUBSHELL_PATTERNS = [
    re.compile(r"\$\([^)]*\bcurl\b"),
    re.compile(r"\$\([^)]*\bwget\b"),
    re.compile(r"\$\([^)]*\bnc\b"),
    re.compile(r"\$\([^)]*\bnetcat\b"),
    re.compile(r"`[^`]*\bcurl\b"),
    re.compile(r"`[^`]*\bwget\b"),
    re.compile(r"`[^`]*\bnc\b"),
    re.compile(r"`[^`]*\bnetcat\b"),
]
_HEREDOC_EVAL = re.compile(r"<<\s*['\"]?\w+['\"]?.*\b(eval|curl|wget|bash|sh|zsh|python\d?)\b", re.DOTALL)
_PROCESS_SUBST = re.compile(r"[<>]\(")
_ZSH_EQUALS = re.compile(r"(?:^|\s)=(curl|wget|nc|netcat|python\d?|bash|sh|zsh)\b")
_DANGEROUS_ENV_PREFIX = re.compile(r"(?:^|\s)(IFS|LD_PRELOAD|LD_LIBRARY_PATH|DYLD_INSERT_LIBRARIES|PATH|PYTHONPATH|NODE_PATH)\s*=")
_PIPE_DANGEROUS = re.compile(r"\|\s*(bash|sh|zsh|python\d?|perl|ruby|node|eval|exec)\b")
_NETCAT_LISTEN = re.compile(r"(?:^|\s)(nc|netcat)\s+[^\n;]*-(?:[A-Za-z]*l|[A-Za-z]*l[A-Za-z]*)\b")
_BRACE_EXEC = re.compile(r"\{[^}]*;[^}]*\}")
_PRIVILEGE = re.compile(r"\b" + "su" + r"do\b")
_INTERACTIVE_REPLS = {"python", "python3", "python2", "node", "nodejs", "irb", "pry", "psql", "mysql", "sqlite3", "mongo", "bash", "sh", "zsh", "fish", "vim", "vi", "nano", "emacs", "less", "more", "htop", "top", "btop"}
_LONG_RUNNING = {"npm install": 300_000, "npm ci": 300_000, "yarn": 300_000, "yarn install": 300_000, "pnpm install": 300_000, "pip install": 180_000, "pip3 install": 180_000, "uv pip": 120_000, "cargo build": 600_000, "cargo test": 300_000, "make": 300_000, "cmake": 300_000, "go build": 120_000, "go test": 120_000, "apt-get": 120_000, "apt ": 120_000, "mvn": 300_000, "gradle": 300_000, "docker build": 600_000}
_NON_INTERACTIVE_FLAGS = {"-V", "--version", "-v", "--help", "-h"}


def _is_interactive(cmd: str) -> bool:
    # Interactive means a known REPL/editor/pager with no script/target args and no -c/-m one-shot flags.
    try:
        tokens = shlex.split(cmd.strip())
    except ValueError:
        return False
    if not tokens:
        return False
    name = tokens[0].split("/")[-1]
    if name not in _INTERACTIVE_REPLS:
        return False
    if "-c" in tokens or "-m" in tokens:
        return False
    if any(t in _NON_INTERACTIVE_FLAGS for t in tokens[1:]):
        return False
    return not [t for t in tokens[1:] if not t.startswith("-")]


def _check_bash_security(command: str) -> str | None:
    for char in _UNICODE_BYPASS:
        if char in command:
            return "安全拦截:检测到 unicode 绕过字符(可能为注入攻击)"
    if _PRIVILEGE.search(command):
        return "安全拦截:禁止使用提权命令"
    for pattern, desc in _BLOCKED_COMMANDS:
        if re.search(pattern, command):
            return f"安全拦截:{desc}"
    for pat in _SUBSHELL_PATTERNS:
        if pat.search(command):
            return "安全拦截:命令替换中包含网络命令(潜在数据外泄)"
    if _HEREDOC_EVAL.search(command):
        return "安全拦截:heredoc 配合 eval 可执行任意代码"
    if _PROCESS_SUBST.search(command):
        return "安全拦截:进程替换 <() / >() 不允许"
    if _ZSH_EQUALS.search(command):
        return "安全拦截:Zsh 等号扩展(=cmd)不允许"
    if (m := _DANGEROUS_ENV_PREFIX.search(command)):
        return f"安全拦截:修改 {m.group(1)} 可能影响运行时安全"
    if _PIPE_DANGEROUS.search(command):
        return "安全拦截:管道输出送入 shell/解释器(潜在代码注入)"
    if _NETCAT_LISTEN.search(command):
        return "安全拦截:netcat 监听端口可能建立反连通道"
    if _BRACE_EXEC.search(command):
        return "安全拦截:大括号扩展中包含分号(可能执行多条命令)"
    return None


def get_adjusted_timeout(command: str, requested: int) -> int:
    for pattern, minimum in _LONG_RUNNING.items():
        if pattern in command:
            return max(requested, minimum)
    return requested


def pre_validate_bash(command: str, timeout: int = 30_000) -> dict | None:
    blocked = _check_bash_security(command)
    if blocked:
        return {"success": False, "error": blocked, "error_class": "SECURITY", "error_type": "SecurityError"}
    if _is_interactive(command):
        cmd_name = shlex.split(command.strip())[0].split("/")[-1]
        return {"success": False, "error": f"{cmd_name} 无参数时进入交互模式,无法在非 TTY 环境执行", "error_class": "MODEL_ERROR", "error_type": "interactive_command", "hint": f"替代:{cmd_name} -c '代码'(单次执行),或将代码写入文件后执行"}
    return None


def truncate_output(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    head = max_chars * 2 // 3
    tail = max_chars - head - 60
    return text[:head] + f"\n\n... [{len(text) - head - tail} chars truncated] ...\n\n" + text[-tail:]


async def execute_run_bash(command: str, cwd: str | None = None, timeout: int = 30_000) -> dict:
    try:
        proc = await asyncio.create_subprocess_shell(command, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"})
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout / 1000)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except (ProcessLookupError, UnboundLocalError):
            pass
        return {"success": False, "error": f"命令超时({timeout}ms)", "error_class": "TRANSIENT", "error_type": "TimeoutError", "hint": f"重试时将 timeout 设为 {timeout * 2}"}
    stdout_str = truncate_output(stdout_b.decode(errors="replace"))
    stderr_str = truncate_output(stderr_b.decode(errors="replace"), max_chars=1000)
    result: dict = {"success": proc.returncode == 0, "exit_code": proc.returncode, "stdout": stdout_str}
    if stderr_str.strip():
        result["stderr"] = stderr_str
    if proc.returncode != 0:
        result["error_class"] = "ENV_ERROR" if proc.returncode == 127 else "MODEL_ERROR"
        result["error_type"] = "command_not_found" if proc.returncode == 127 else "nonzero_exit"
        result["error"] = "命令不存在" if proc.returncode == 127 else f"exit code {proc.returncode}"
        if proc.returncode == 127:
            result["hint"] = "常用替代:fd→find, rg→grep -r, bat→cat, jq→python3 -m json.tool"
    return result
