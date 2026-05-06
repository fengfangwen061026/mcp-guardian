from __future__ import annotations

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

_UNICODE_BYPASS = [
    ("\u200b", "零宽空格"),
    ("\u200c", "零宽非连接符"),
    ("\u200d", "零宽连接符"),
    ("\ufeff", "BOM 标记"),
    ("\r", "CR 字符(parser 差异攻击向量)"),
]

_SUBSHELL_NETWORK = [
    re.compile(r"\$\([^)]*\bcurl\b"),
    re.compile(r"\$\([^)]*\bwget\b"),
    re.compile(r"\$\([^)]*\bnc\b"),
    re.compile(r"`[^`]*\bcurl\b"),
    re.compile(r"`[^`]*\bwget\b"),
]

_HEREDOC_EVAL = re.compile(r"<<\s*['\"]?\w+['\"]?.*\beval\b", re.DOTALL)
_PROCESS_SUBST = re.compile(r"[<>]\(")
_ZSH_EQUALS = re.compile(r"(?:^|\s)=(curl|wget|nc|netcat|python\d?|bash|sh|zsh)\b")
_DANGEROUS_ENV_PREFIX = re.compile(r"(?:^|\s)(IFS|LD_PRELOAD|LD_LIBRARY_PATH|DYLD_INSERT_LIBRARIES|PATH|PYTHONPATH|NODE_PATH)\s*=")
_PIPE_DANGEROUS = re.compile(r"\|\s*(bash|sh|zsh|python\d?|perl|ruby|node|eval|exec)\b")
_BRACE_EXEC = re.compile(r"\{[^}]*;[^}]*\}")
_SUDO = re.compile(r"\bsudo\b")

_INTERACTIVE_REPLS = {
    "python", "python3", "python2", "node", "nodejs", "irb", "pry", "psql",
    "mysql", "sqlite3", "mongo", "bash", "sh", "zsh", "fish", "vim", "vi",
    "nano", "emacs", "less", "more", "htop", "top", "btop",
}


def is_interactive(command: str) -> bool:
    try:
        tokens = shlex.split(command.strip())
    except ValueError:
        return False
    if not tokens:
        return False
    cmd = tokens[0].split("/")[-1]
    if cmd not in _INTERACTIVE_REPLS:
        return False
    non_flag_args = [t for t in tokens[1:] if not t.startswith("-")]
    if non_flag_args:
        return False
    if "-c" in tokens or "-m" in tokens:
        return False
    return True


def check_bash_security(command: str) -> str | None:
    for char, desc in _UNICODE_BYPASS:
        if char in command:
            return f"安全拦截:检测到 {desc}(可能为注入攻击)"
    if _SUDO.search(command):
        return "安全拦截:禁止使用 sudo"
    for pattern, desc in _BLOCKED_COMMANDS:
        if re.search(pattern, command):
            return f"安全拦截:{desc}"
    for pat in _SUBSHELL_NETWORK:
        if pat.search(command):
            return "安全拦截:命令替换中包含网络命令(潜在数据外泄)"
    if _HEREDOC_EVAL.search(command):
        return "安全拦截:heredoc 配合 eval 可执行任意代码"
    if _PROCESS_SUBST.search(command):
        return "安全拦截:进程替换 <() / >() 不允许"
    if _ZSH_EQUALS.search(command):
        return "安全拦截:Zsh 等号扩展(=cmd)不允许"
    m = _DANGEROUS_ENV_PREFIX.search(command)
    if m:
        return f"安全拦截:修改 {m.group(1)} 可能影响运行时安全"
    if _PIPE_DANGEROUS.search(command):
        return "安全拦截:管道输出送入 shell/解释器(潜在代码注入)"
    if _BRACE_EXEC.search(command):
        return "安全拦截:大括号扩展中包含分号(可能执行多条命令)"
    return None
