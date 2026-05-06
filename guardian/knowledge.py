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


EDIT_ENTRIES = [
    KnowledgeEntry("edit:spec:must_read_first", "guardian_edit_file", "spec", "编辑前必须先 Read", "调用 guardian_edit_file 前必须先调用 guardian_read_file 读取文件当前内容。old_str 必须从实际文件内容中精确复制。", 1, ("old_string_not_found",)),
    KnowledgeEntry("edit:spec:exact_match", "guardian_edit_file", "spec", "精确匹配规则", "old_str 必须与文件内容逐字符完全一致,包括空格、Tab、换行符、尾部空白、空行。", 2, ("old_string_not_found",)),
    KnowledgeEntry("edit:spec:unique_match", "guardian_edit_file", "spec", "唯一匹配要求", "old_str 在文件中必须恰好出现 1 次。若匹配到多处,扩展 old_str 范围直到唯一定位。", 2, ("appears_multiple_times",)),
    KnowledgeEntry("edit:anti:line_number_in_old", "guardian_edit_file", "antipattern", "行号混入 old_str", "guardian_read_file 返回带行号前缀。编辑时 old_str 不得包含行号前缀。", 2, ("old_string_not_found",)),
    KnowledgeEntry("edit:anti:stale_content", "guardian_edit_file", "antipattern", "使用过期内容", "文件被其他工具修改后,之前读取的内容已失效。每次 edit 前必须重新 read。", 2, ("old_string_not_found",)),
    KnowledgeEntry("edit:anti:invisible_chars", "guardian_edit_file", "antipattern", "不可见字符差异", "Tab vs 空格、全角空格、零宽字符、BOM 可能造成失败。从 read 结果中直接复制。", 3, ("old_string_not_found",)),
    KnowledgeEntry("edit:anti:crlf_mismatch", "guardian_edit_file", "antipattern", "CRLF/LF 换行符不一致", "Guardian 有 CRLF/LF 归一化容错,但混用换行符仍可能失败。", 3, ("old_string_not_found",)),
    KnowledgeEntry("edit:anti:infinite_retry", "guardian_edit_file", "antipattern", "无限重试循环", "同样的 old_str 失败后不应再次使用完全相同的参数重试。", 2, ("old_string_not_found",)),
    KnowledgeEntry("edit:example:correct_flow", "guardian_edit_file", "example", "正确的编辑流程", "1) read 当前内容;2) 精确复制片段;3) 构造 new_str;4) edit。", 3, ()),
    KnowledgeEntry("edit:recovery:fallback_to_write", "guardian_edit_file", "recovery", "降级为整体重写", "若 edit 连续失败 3 次,read 整个文件,在内存中修改,再用 write 整体重写。", 4, ()),
]

BASH_ENTRIES = [
    KnowledgeEntry("bash:spec:timeout_guide", "guardian_run_bash", "spec", "超时参数指南", "默认超时 30 秒。长时命令必须设置 timeout(毫秒):npm install 300000,pip install 180000,cargo build 600000。", 2, ("TimeoutError", "timeout")),
    KnowledgeEntry("bash:spec:output_truncation", "guardian_run_bash", "spec", "输出截断规则", "stdout 超过预算会截断。避免 cat 大文件、全盘搜索等大输出。", 3, ()),
    KnowledgeEntry("bash:spec:non_interactive", "guardian_run_bash", "spec", "非交互模式", "所有命令必须非交互执行。需要确认的加 -y,需要输入的用管道或 heredoc。", 2, ("TimeoutError",)),
    KnowledgeEntry("bash:anti:tool_assumption", "guardian_run_bash", "antipattern", "假设非标准工具已安装", "不得假设系统有 fd,bat,jq,rg,delta,exa。不确定时先 which 检查。", 2, ("command_not_found", "FileNotFoundError")),
    KnowledgeEntry("bash:anti:dangerous_commands", "guardian_run_bash", "antipattern", "被安全拦截的危险命令", "格式化、原始磁盘写入、删除根目录、写系统目录、管道进 shell 等会被拦截。", 1, ("SecurityError", "permission_denied")),
    KnowledgeEntry("bash:anti:windows_path", "guardian_run_bash", "antipattern", "Windows 风格路径", "禁止使用反斜杠路径。所有路径用 Unix 正斜杠。", 4, ("syntax_error", "FileNotFoundError")),
    KnowledgeEntry("bash:anti:unclosed_quotes", "guardian_run_bash", "antipattern", "引号未闭合", "单引号、双引号、反引号必须成对。heredoc 结束标记必须独占一行。", 3, ("syntax_error",)),
    KnowledgeEntry("bash:recovery:alternatives", "guardian_run_bash", "recovery", "常用替代命令映射", "fd→find, rg→grep -r, bat→cat, jq→python3 -m json.tool, exa→ls -la。", 3, ("command_not_found",)),
    KnowledgeEntry("bash:recovery:nonzero", "guardian_run_bash", "recovery", "非零退出排查", "先看 stderr 和 exit_code,不要原样重试。修正路径、依赖或参数后再运行。", 3, ("nonzero_exit",)),
]

READ_ENTRIES = [
    KnowledgeEntry("read:spec:line_format", "guardian_read_file", "spec", "返回格式说明", "返回内容每行带行号前缀,N 从 1 开始。start_line/end_line 是行号。", 2, ()),
    KnowledgeEntry("read:spec:large_file", "guardian_read_file", "spec", "大文件处理", "超过 500 行建议分段读取,避免一次读整个大文件。", 3, ()),
    KnowledgeEntry("read:anti:offset_as_bytes", "guardian_read_file", "antipattern", "误把行号当字节偏移", "start_line=100 表示从第 100 行开始,不是第 100 字节。", 3, ()),
]

WRITE_ENTRIES = [
    KnowledgeEntry("write:spec:full_overwrite", "guardian_write_file", "spec", "整体覆写语义", "content 是文件完整内容,不是追加。追加应先 read、拼接、write。", 2, ()),
    KnowledgeEntry("write:spec:auto_mkdir", "guardian_write_file", "spec", "自动创建目录", "父目录不存在时自动创建。", 5, ()),
    KnowledgeEntry("write:anti:empty_content", "guardian_write_file", "antipattern", "content 不可省略", "content 参数必传、不可为 null。创建空文件请传空字符串。", 2, ("ValidationError", "TypeError")),
    KnowledgeEntry("write:recovery:permission", "guardian_write_file", "recovery", "写入失败排查", "遇到权限或系统目录错误时,改写项目目录内文件,不要绕过权限。", 3, ("PermissionError",)),
]

GLOB_ENTRIES = [
    KnowledgeEntry("glob:spec:syntax", "guardian_glob", "spec", "glob 语法要点", "* 匹配单层文件名,** 匹配任意深度目录。不支持正则。", 3, ()),
    KnowledgeEntry("glob:anti:param_swap", "guardian_glob", "antipattern", "参数混淆", "pattern 是 glob 模式,path 是搜索根目录。", 3, ("ValidationError",)),
    KnowledgeEntry("glob:recovery:empty", "guardian_glob", "recovery", "无结果时缩放范围", "无结果时先确认 path,再把 pattern 从精确文件名放宽到 **/*.ext。", 4, ()),
]

GREP_ENTRIES = [
    KnowledgeEntry("grep:spec:regex_syntax", "guardian_grep", "spec", "正则语法", "pattern 使用 Python re 兼容正则。简单模式优先。", 4, ()),
    KnowledgeEntry("grep:anti:too_broad", "guardian_grep", "antipattern", "模式过于宽泛", "避免 .*、. 等超宽模式。用 include 限定文件类型。", 3, ("regex_error",)),
    KnowledgeEntry("grep:recovery:no_match", "guardian_grep", "recovery", "无匹配排查", "无匹配时检查大小写、转义和 include 限制,必要时先 glob 定位文件。", 4, ()),
]

ALL_ENTRIES = EDIT_ENTRIES + BASH_ENTRIES + READ_ENTRIES + WRITE_ENTRIES + GLOB_ENTRIES + GREP_ENTRIES
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
