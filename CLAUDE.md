# MCP Guardian 项目说明

文件创建、编辑、命令执行优先使用 guardian_* 系列 MCP 工具：

- 读文件 → `guardian_read_file(path, start_line?, end_line?)`
- 写文件 → `guardian_write_file(path, content)`
- 编辑文件 → `guardian_edit_file(path, old_str, new_str)`
- 执行命令 → `guardian_run_bash(command, cwd?, timeout?)`
- 搜索文件 → `guardian_glob(pattern, path?)`
- 搜索内容 → `guardian_grep(pattern, path?, include?)`

## 错误处理协议

1. 先读 `error` 字段了解原因。
2. 读 `guidance` 字段获取修复建议。
3. edit 失败若返回 `file_content`，从其中精确复制新的 `old_str`。
4. 出现连续失败 warning 时必须调整参数，不要原样重试。
5. `HARD_BLOCKED` 时修改参数模式，或调用 `guardian_get_spec(tool_name)`。

## 强制规则

1. 编辑文件前先 `guardian_read_file`。
2. `old_str` 必须逐字符精确复制，包含缩进和换行。
3. 不允许相同工具用完全相同参数连续调用两次以上。
4. 长时命令显式设置 timeout。

## 本地验证

```bash
.venv/bin/python -m pytest tests/ -v
```
