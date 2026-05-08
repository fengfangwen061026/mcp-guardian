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

_INTERACTIVE_REPLS = {
    "python", "python3", "python2", "node", "nodejs", "irb", "pry", "psql",
    "mysql", "sqlite3", "mongo", "bash", "sh", "zsh", "fish", "vim", "vi",
    "nano", "emacs", "less", "more", "htop", "top", "btop",
}
_NON_INTERACTIVE_FLAGS = {"-V", "--version", "-v", "--help", "-h"}
_BLOCKED_ARGV_EXECUTABLES = {"sudo", "su", "mkfs", "dd"}


def is_interactive(command: str) -> bool:
    try:
        tokens = shlex.split(command.strip())
    except ValueError:
        return False
    return is_interactive_argv(tokens)


def is_interactive_argv(argv: list[str]) -> bool:
    if not argv:
        return False
    name = argv[0].split("/")[-1]
    if name not in _INTERACTIVE_REPLS:
        return False
    if "-c" in argv or "-m" in argv:
        return False
    if any(t in _NON_INTERACTIVE_FLAGS for t in argv[1:]):
        return False
    return not [t for t in argv[1:] if not t.startswith("-")]


def check_bash_security(command: str) -> str | None:
    for char, desc in _UNICODE_BYPASS:
        if char in command:
            return f"安全拦截:检测到 {desc}(可能为注入攻击)"
    if _PRIVILEGE.search(command):
        return "安全拦截:禁止使用提权命令"
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
    if m := _DANGEROUS_ENV_PREFIX.search(command):
        return f"安全拦截:修改 {m.group(1)} 可能影响运行时安全"
    if _PIPE_DANGEROUS.search(command):
        return "安全拦截:管道输出送入 shell/解释器(潜在代码注入)"
    if _NETCAT_LISTEN.search(command):
        return "安全拦截:netcat 监听端口可能建立反连通道"
    if _BRACE_EXEC.search(command):
        return "安全拦截:大括号扩展中包含分号(可能执行多条命令)"
    return None


def check_argv_security(argv: list[str]) -> str | None:
    if not argv:
        return "argv 不能为空"
    executable = argv[0].strip()
    if not executable:
        return "argv[0] 不能为空"
    name = executable.split("/")[-1]
    if name in _BLOCKED_ARGV_EXECUTABLES:
        return f"安全拦截:禁止执行 {name}"
    for arg in argv:
        for char, desc in _UNICODE_BYPASS:
            if char in arg:
                return f"安全拦截:检测到 {desc}(可能为注入攻击)"
    return None


_check_bash_security = check_bash_security
_is_interactive = is_interactive
