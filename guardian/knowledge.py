from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeEntry:
    id: str
    tool_name: str
    category: str
    title: str
    content: str
    base_priority: int
    error_types: tuple[str, ...] = ()


KNOWLEDGE_BASE = [
    {
        "id": "edit:spec:must_read_first",
        "tool_name": "guardian_edit_file",
        "category": "spec",
        "title": "编辑前必须 Read",
        "content": "调用 guardian_edit_file 前必须先调用 guardian_read_file 读取文件当前内容。old_str 必须从实际返回的 content 字段中精确复制，不得凭记忆或上下文推测。文件被其他工具修改后之前读取的内容立即失效。",
        "base_priority": 1,
        "error_types": "old_string_not_found",
    },
    {
        "id": "edit:spec:exact_match",
        "tool_name": "guardian_edit_file",
        "category": "spec",
        "title": "精确匹配规则",
        "content": "old_str 必须与文件内容逐字符完全一致，包括：空格/Tab 缩进、换行符（LF vs CRLF）、尾部空白、空行数量。一个字符不匹配即报 old_string_not_found。guardian_read_file 返回的 content 带行号前缀（如 '1: xxx'），old_str 中不得包含行号前缀。",
        "base_priority": 1,
        "error_types": "old_string_not_found",
    },
    {
        "id": "edit:spec:unique_match",
        "tool_name": "guardian_edit_file",
        "category": "spec",
        "title": "唯一匹配要求",
        "content": "old_str 在文件中必须恰好出现 1 次。出现多次时返回 appears_multiple_times。修复：扩展 old_str 范围，加入前后各 2-3 行上下文，直到在文件中唯一定位。不要截短 old_str，截短反而增加碰撞概率。",
        "base_priority": 2,
        "error_types": "appears_multiple_times",
    },
    {
        "id": "edit:anti:stale_content",
        "tool_name": "guardian_edit_file",
        "category": "antipattern",
        "title": "使用过期内容",
        "content": "多次编辑同一文件时，每次 guardian_edit_file 成功后文件内容已变。下一次编辑前必须重新 guardian_read_file，不能复用上次读取的内容。",
        "base_priority": 2,
        "error_types": "old_string_not_found",
    },
    {
        "id": "edit:anti:invisible_chars",
        "tool_name": "guardian_edit_file",
        "category": "antipattern",
        "title": "不可见字符差异",
        "content": "Tab vs 空格、全角 vs 半角空格、零宽字符（U+200B/200C/200D）、BOM 标记（U+FEFF）——肉眼看相同但字节不同。唯一可靠方法：从 guardian_read_file 的 content 字段直接复制，不手动重新输入。",
        "base_priority": 3,
        "error_types": "old_string_not_found",
    },
    {
        "id": "edit:anti:infinite_retry",
        "tool_name": "guardian_edit_file",
        "category": "antipattern",
        "title": "无限重试循环",
        "content": "同样的 old_str 连续失败后不应再次使用完全相同参数重试。正确流程：重新 read 文件 → 确认实际内容 → 构造新的精确 old_str。连续 3 次相同失败后改用 guardian_write_file 整体重写。",
        "base_priority": 2,
        "error_types": "old_string_not_found",
    },
    {
        "id": "edit:anti:no_context",
        "tool_name": "guardian_edit_file",
        "category": "antipattern",
        "title": "old_str 过短缺乏上下文",
        "content": "old_str 只包含 1-2 行容易重复的内容（如 'pass'、'return None'、空行），导致 appears_multiple_times。应包含足够上下文（函数签名+函数体，或类名+方法名）使 old_str 在整个文件中唯一。",
        "base_priority": 2,
        "error_types": "appears_multiple_times",
    },
    {
        "id": "edit:example:correct_flow",
        "tool_name": "guardian_edit_file",
        "category": "example",
        "title": "正确的编辑流程",
        "content": "1) guardian_read_file('src/app.py') → 获得带行号的 content  2) 从 content 中找到目标行，去掉行号前缀，精确复制需修改的片段（含缩进/换行）作为 old_str  3) 构造 new_str  4) guardian_edit_file('src/app.py', old_str, new_str)。多处修改时每次 edit 后重新 read。",
        "base_priority": 3,
        "error_types": None,
    },
    {
        "id": "edit:recovery:fallback_write",
        "tool_name": "guardian_edit_file",
        "category": "recovery",
        "title": "精确编辑失败后降级为整体重写",
        "content": "guardian_edit_file 连续失败 3 次后：1) guardian_read_file 读取完整文件  2) 在内存中构造修改后的完整内容  3) guardian_write_file 整体覆写。适用于文件较小（< 500 行）且修改范围较大的场景。",
        "base_priority": 4,
        "error_types": "old_string_not_found,appears_multiple_times",
    },
    {
        "id": "edit:recovery:verify_after_edit",
        "tool_name": "guardian_edit_file",
        "category": "recovery",
        "title": "编辑后验证",
        "content": "guardian_edit_file 返回 success: true 不代表修改语义正确。对关键修改应在 edit 后调用 guardian_read_file 验证目标行已按预期修改，或用 guardian_run_bash 运行相关测试。",
        "base_priority": 5,
        "error_types": None,
    },
    {
        "id": "bash:spec:timeout",
        "tool_name": "guardian_run_bash",
        "category": "spec",
        "title": "长时命令必须指定 timeout",
        "content": "默认 timeout 30000ms 不够。必须手动指定（单位毫秒）：npm install/yarn → 300000，pip install → 180000，cargo build/docker build → 600000，go build/go test → 120000，make/mvn/gradle → 300000。",
        "base_priority": 1,
        "error_types": "TimeoutError",
    },
    {
        "id": "bash:spec:noninteractive",
        "tool_name": "guardian_run_bash",
        "category": "spec",
        "title": "交互式命令必须添加非交互参数",
        "content": "等待 stdin 的命令会卡死直到超时。常用非交互参数：apt-get/apt → -y，npm init → -y，pip → --yes，rm → -f，git merge → --no-edit。检测方法：命令是否需要用户手动输入才能继续。",
        "base_priority": 2,
        "error_types": "TimeoutError",
    },
    {
        "id": "bash:spec:cwd",
        "tool_name": "guardian_run_bash",
        "category": "spec",
        "title": "使用 cwd 参数而非 cd &&",
        "content": "需要在特定目录执行命令时，优先使用 cwd 参数而非 'cd /path && command'。cwd 参数更清晰、不受 shell 转义影响。",
        "base_priority": 3,
        "error_types": None,
    },
    {
        "id": "bash:anti:security_block",
        "tool_name": "guardian_run_bash",
        "category": "antipattern",
        "title": "触发安全拦截",
        "content": "Guardian 拦截以下类别：rm -rf /、mkfs、dd if=/dev/、fork bomb、sudo rm、写入 /etc/ 或 ~/.bashrc、命令替换中的网络下载（eval $(curl ...)）、nc/netcat 监听端口、heredoc 中的网络请求。被拦截时查看 error 字段的具体原因重构命令。",
        "base_priority": 1,
        "error_types": "SECURITY",
    },
    {
        "id": "bash:anti:large_output",
        "tool_name": "guardian_run_bash",
        "category": "antipattern",
        "title": "命令输出过大",
        "content": "stdout 超出预算时会被截断。解决方法：用 head/tail 限制行数，用 grep 过滤关键信息，用 > file.txt 重定向后再 guardian_read_file，或用 | wc -l 先确认行数。",
        "base_priority": 3,
        "error_types": "output_truncated",
    },
    {
        "id": "bash:example:test_run",
        "tool_name": "guardian_run_bash",
        "category": "example",
        "title": "运行测试的正确方式",
        "content": "guardian_run_bash('pytest tests/ -x --tb=short', timeout=120000)。-x 遇到第一个失败停止，--tb=short 减少输出。大型测试套件：先 guardian_run_bash('pytest tests/ --collect-only -q') 了解规模，再针对性运行子集。",
        "base_priority": 3,
        "error_types": None,
    },
    {
        "id": "bash:recovery:timeout_retry",
        "tool_name": "guardian_run_bash",
        "category": "recovery",
        "title": "超时后的处理策略",
        "content": "TimeoutError 时：1) 是长时命令则按 spec:timeout 增加 timeout 值  2) 检查命令是否卡在等待输入（添加 -y 等非交互参数）  3) 是网络操作则检查连通性  4) 复杂命令拆分为多个子步骤分别执行。",
        "base_priority": 3,
        "error_types": "TimeoutError",
    },
    {
        "id": "bash:recovery:nonzero_exit",
        "tool_name": "guardian_run_bash",
        "category": "recovery",
        "title": "非零退出码处理",
        "content": "exit_code != 0 不一定是严重错误。步骤：1) 阅读 stdout 和 stderr 定位实际错误  2) 可忽略：grep 未找到匹配（exit 1）、diff 有差异（exit 1）  3) 需处理：编译错误、测试失败、文件不存在  4) 不要用 || true 掩盖所有错误。",
        "base_priority": 3,
        "error_types": "nonzero_exit",
    },
    {
        "id": "read:spec:line_numbers",
        "tool_name": "guardian_read_file",
        "category": "spec",
        "title": "content 字段包含行号前缀",
        "content": "guardian_read_file 返回的 content 每行带行号前缀，格式为 'N: 实际内容'。将 content 用于 guardian_edit_file 的 old_str 时，必须去掉行号前缀（'1: '、'2: ' 等），只保留冒号后的内容。start_line/end_line 使用 1-indexed 行号。",
        "base_priority": 1,
        "error_types": "old_string_not_found",
    },
    {
        "id": "read:spec:range",
        "tool_name": "guardian_read_file",
        "category": "spec",
        "title": "大文件使用行范围",
        "content": "大文件（> 500 行）应使用 start_line/end_line 只读取需要修改的区域。先用 guardian_grep 定位目标内容的行号，再用 start_line/end_line 精确读取上下文（目标行前后各 5-10 行）。",
        "base_priority": 3,
        "error_types": None,
    },
    {
        "id": "read:recovery:not_found",
        "tool_name": "guardian_read_file",
        "category": "recovery",
        "title": "文件不存在时的处理",
        "content": "返回 ENV_ERROR + file_not_found 时：1) 用 guardian_glob 确认路径  2) 检查大小写（Linux 区分大小写）  3) 确认是否需要先 guardian_write_file 创建  4) 用 guardian_run_bash('pwd') 确认工作目录。",
        "base_priority": 2,
        "error_types": "file_not_found",
    },
    {
        "id": "glob:spec:patterns",
        "tool_name": "guardian_glob",
        "category": "spec",
        "title": "glob 模式语法",
        "content": "* 匹配单层文件名中的任意字符，** 匹配任意层目录，? 匹配单个字符，{a,b} 匹配 a 或 b。常用示例：'**/*.py' 递归所有 Python 文件，'src/**/*.{ts,tsx}'，'tests/test_*.py'。path 参数指定搜索根目录。",
        "base_priority": 2,
        "error_types": None,
    },
    {
        "id": "glob:anti:too_broad",
        "tool_name": "guardian_glob",
        "category": "antipattern",
        "title": "模式过宽",
        "content": "'**/*' 会返回所有文件，结果可能被截断。应加文件扩展名过滤、限制目录层级、使用 path 参数限制搜索范围。了解项目结构时优先用 guardian_run_bash('find . -type f -name \"*.py\" | head -50') 控制输出量。",
        "base_priority": 3,
        "error_types": "output_truncated",
    },
    {
        "id": "glob:example:find_file",
        "tool_name": "guardian_glob",
        "category": "example",
        "title": "定位文件的推荐流程",
        "content": "不确定路径时：1) guardian_glob('**/<filename>') 按文件名搜索  2) guardian_grep('<function_name>', path='.') 按内容搜索  3) guardian_run_bash('find . -name \"<pattern>\" -type f') 用 find 命令。三种方式互补：glob 最快，grep 最精确，find 最灵活。",
        "base_priority": 3,
        "error_types": None,
    },
    {
        "id": "grep:spec:usage",
        "tool_name": "guardian_grep",
        "category": "spec",
        "title": "grep 参数说明",
        "content": "pattern：Python re 语法正则。path：搜索根目录。include：文件名过滤（如 '*.py'）。返回匹配行、文件路径和行号，可直接用于 guardian_read_file 的 start_line 参数。",
        "base_priority": 2,
        "error_types": None,
    },
    {
        "id": "grep:anti:regex_escape",
        "tool_name": "guardian_grep",
        "category": "antipattern",
        "title": "正则特殊字符需转义",
        "content": "pattern 是正则，. * + ? ( ) [ ] { } ^ $ | 有特殊含义。搜索字面字符串时需转义：搜索 'func()' 应写 'func\\(\\)'。或用 guardian_run_bash('grep -F \"func()\" file.py') 的 -F 固定字符串模式。",
        "base_priority": 3,
        "error_types": "regex_error",
    },
    {
        "id": "write:spec:overwrite",
        "tool_name": "guardian_write_file",
        "category": "spec",
        "title": "write_file 是整体覆写",
        "content": "guardian_write_file 完全覆盖目标文件。用于：创建新文件、guardian_edit_file 连续失败后的降级重写、生成配置文件。不要用于局部修改。写入前建议先 guardian_read_file 确认要保留的内容。",
        "base_priority": 2,
        "error_types": None,
    },
    {
        "id": "write:anti:encoding",
        "tool_name": "guardian_write_file",
        "category": "antipattern",
        "title": "编码注意事项",
        "content": "guardian_write_file 使用 UTF-8 写入。原文件是其他编码（GBK、Latin-1）时写入后编码会变化。处理非 UTF-8 文件时先用 guardian_run_bash('file <path>') 确认编码，再决定是否用 iconv 预处理。",
        "base_priority": 4,
        "error_types": "encoding_error",
    },
]


def _error_types(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


ALL_ENTRIES = [
    KnowledgeEntry(
        id=e["id"],
        tool_name=e["tool_name"],
        category=e["category"],
        title=e["title"],
        content=e["content"],
        base_priority=e["base_priority"],
        error_types=_error_types(e.get("error_types")),
    )
    for e in KNOWLEDGE_BASE
]
ALL_ENTRIES.extend([
    KnowledgeEntry("bash:recovery:command_not_found", "guardian_run_bash", "recovery", "命令不存在处理", "command_not_found 时先确认工具是否安装，优先使用系统自带替代命令。", 4, ("command_not_found",)),
    KnowledgeEntry("write:recovery:permission", "guardian_write_file", "recovery", "写入失败排查", "遇到权限或系统目录错误时，改写项目目录内文件，不要绕过权限。", 3, ("PermissionError",)),
    KnowledgeEntry("grep:recovery:no_match", "guardian_grep", "recovery", "无匹配排查", "无匹配时检查大小写、转义和 include 限制，必要时先 glob 定位文件。", 4, ()),
])
KNOWLEDGE_BY_ID = {e.id: e for e in ALL_ENTRIES}
KNOWLEDGE_BY_TOOL: dict[str, list[KnowledgeEntry]] = {}
for e in ALL_ENTRIES:
    KNOWLEDGE_BY_TOOL.setdefault(e.tool_name, []).append(e)
KNOWLEDGE_BY_ERROR: dict[tuple[str, str], list[KnowledgeEntry]] = {}
for e in ALL_ENTRIES:
    for et in e.error_types:
        KNOWLEDGE_BY_ERROR.setdefault((e.tool_name, et), []).append(e)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _offset_from_session(session, entry_id: str) -> float:
    hits = getattr(session, "knowledge_hits", {}).get(entry_id, 0)
    return -0.3 * hits


def select_guidance(tool_name: str, error_type: str | None, offset_lookup=None, max_tokens: int = 200, max_entries: int = 3) -> list[dict]:
    candidates = list(KNOWLEDGE_BY_TOOL.get(tool_name, []))
    scored = []
    for entry in candidates:
        offset = offset_lookup(entry.id) if offset_lookup else 0.0
        eff = float(entry.base_priority) + offset
        if error_type and error_type in entry.error_types:
            eff -= 5.0
        elif error_type and entry.category == "recovery":
            eff -= 1.5
        scored.append((eff, entry))
    scored.sort(key=lambda x: x[0])

    out = []
    used = 0
    for _, entry in scored:
        body = f"[{entry.category}] {entry.title}: {entry.content}"
        t = _estimate_tokens(body)
        if used + t > max_tokens:
            remaining = max_tokens - used
            if remaining > 30:
                out.append({"id": entry.id, "category": entry.category, "title": entry.title, "content": body[: remaining * 4 - 20] + "...[truncated]"})
            break
        out.append({"id": entry.id, "category": entry.category, "title": entry.title, "content": entry.content})
        used += t
        if len(out) >= max_entries:
            break
    return out


def get_static_guidance(tool_name: str, error_type: str | None = None, session=None, max_tokens: int = 150) -> list[dict]:
    def lookup(entry_id: str) -> float:
        return _offset_from_session(session, entry_id) if session else 0.0
    return select_guidance(tool_name, error_type, offset_lookup=lookup, max_tokens=max_tokens)


def get_knowledge_by_tool(tool_name: str) -> list[dict]:
    return [e for e in KNOWLEDGE_BASE if e["tool_name"] == tool_name]


def get_knowledge_by_error_type(error_type: str) -> list[dict]:
    return [
        e for e in KNOWLEDGE_BASE
        if e.get("error_types") and error_type in e["error_types"]
    ]
