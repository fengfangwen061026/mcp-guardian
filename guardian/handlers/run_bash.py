from __future__ import annotations

import asyncio
import os
import shlex

from ..security import check_argv_security, check_bash_security, is_interactive, is_interactive_argv

_LONG_RUNNING = {
    "npm install": 300_000,
    "npm ci": 300_000,
    "yarn": 300_000,
    "yarn install": 300_000,
    "pnpm install": 300_000,
    "pip install": 180_000,
    "pip3 install": 180_000,
    "uv pip": 120_000,
    "cargo build": 600_000,
    "cargo test": 300_000,
    "make": 300_000,
    "cmake": 300_000,
    "go build": 120_000,
    "go test": 120_000,
    "apt-get": 120_000,
    "apt ": 120_000,
    "mvn": 300_000,
    "gradle": 300_000,
    "docker build": 600_000,
}

_check_bash_security = check_bash_security
_is_interactive = is_interactive


def get_adjusted_timeout(command: str, requested: int) -> int:
    for pattern, minimum in _LONG_RUNNING.items():
        if pattern in command:
            return max(requested, minimum)
    return requested


def pre_validate_bash(command: str, timeout: int = 30_000) -> dict | None:
    blocked = check_bash_security(command)
    if blocked:
        return {"success": False, "error": blocked, "error_class": "SECURITY", "error_type": "SecurityError"}
    if is_interactive(command):
        cmd_name = shlex.split(command.strip())[0].split("/")[-1]
        return {"success": False, "error": f"{cmd_name} 无参数时进入交互模式,无法在非 TTY 环境执行", "error_class": "MODEL_ERROR", "error_type": "interactive_command", "hint": f"替代:{cmd_name} -c '代码'(单次执行),或将代码写入文件后执行"}
    return None


def pre_validate_argv(argv: list[str]) -> dict | None:
    blocked = check_argv_security(argv)
    if blocked:
        return {"success": False, "error": blocked, "error_class": "SECURITY", "error_type": "SecurityError"}
    if is_interactive_argv(argv):
        cmd_name = argv[0].split("/")[-1]
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
        proc = await asyncio.create_subprocess_shell(command, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=_env())
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout / 1000)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except (ProcessLookupError, UnboundLocalError):
            pass
        return _timeout_result(timeout, "shell")
    return _process_result(proc.returncode, stdout_b, stderr_b, "shell")


async def execute_run_argv(argv: list[str], cwd: str | None = None, timeout: int = 30_000) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(*argv, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=_env())
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout / 1000)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except (ProcessLookupError, UnboundLocalError):
            pass
        return _timeout_result(timeout, "argv")
    except FileNotFoundError:
        return {"success": False, "exit_code": 127, "stdout": "", "execution_mode": "argv", "error_class": "ENV_ERROR", "error_type": "command_not_found", "error": "命令不存在", "hint": "检查 argv[0] 是否为可执行文件或绝对路径"}
    return _process_result(proc.returncode, stdout_b, stderr_b, "argv")


def _env() -> dict[str, str]:
    return {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}


def _timeout_result(timeout: int, execution_mode: str) -> dict:
    return {"success": False, "execution_mode": execution_mode, "error": f"命令超时({timeout}ms)", "error_class": "TRANSIENT", "error_type": "TimeoutError", "hint": f"重试时将 timeout 设为 {timeout * 2}"}


def _process_result(returncode: int, stdout_b: bytes, stderr_b: bytes, execution_mode: str) -> dict:
    stdout_str = truncate_output(stdout_b.decode(errors="replace"))
    stderr_str = truncate_output(stderr_b.decode(errors="replace"), max_chars=1000)
    result: dict = {"success": returncode == 0, "exit_code": returncode, "stdout": stdout_str, "execution_mode": execution_mode}
    if stderr_str.strip():
        result["stderr"] = stderr_str
    if returncode != 0:
        result["error_class"] = "ENV_ERROR" if returncode == 127 else "MODEL_ERROR"
        result["error_type"] = "command_not_found" if returncode == 127 else "nonzero_exit"
        result["error"] = "命令不存在" if returncode == 127 else f"exit code {returncode}"
        if returncode == 127:
            result["hint"] = "常用替代:fd→find, rg→grep -r, bat→cat, jq→python3 -m json.tool"
    return result
