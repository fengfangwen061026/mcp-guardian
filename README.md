# MCP Guardian

**MCP Guardian 是一个面向 Claude Code 的 MCP 工具中间层，用来让第三方 LLM 更稳定、更安全地使用文件、搜索和命令执行能力。**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)

## 它解决什么问题

Claude Code 的原生工具非常强，但它们的调用习惯、错误恢复方式和安全边界主要围绕 Claude 模型训练。第三方模型接入 Claude Code 时，常见问题不是“不会写代码”，而是“不会正确使用工具”。

典型表现包括：

| 问题 | 常见表现 | 后果 |
| --- | --- | --- |
| 不读文件就编辑 | 凭上下文猜 `old_str` | `old_string_not_found`，反复失败 |
| 复制内容不精确 | 缩进、空格、换行、行号混入 | 编辑无法命中或误改 |
| 失败后原样重试 | 同一组参数连续调用 | 消耗 token，污染上下文 |
| Bash 命令过于随意 | 超时过短、交互命令、危险操作 | 卡住、失败或产生高风险副作用 |
| 错误信息缺乏下一步 | 模型只看到失败，不知道怎么修 | 进入循环，越修越乱 |

MCP Guardian 的目标是：**把这些高频工具错误拦在执行前、解释在失败处、熔断在循环中。**

## 它和 Claude Code 原生工具是什么关系

MCP Guardian 不会删除 Claude Code 的原生工具，也不是修改 Claude Code 源码。它通过 MCP 暴露一组 `guardian_*` 工具，作为原生工具的受控包装层。

推荐用法是：

- 读文件时用 `guardian_read_file`，而不是直接用 `Read`
- 写文件时用 `guardian_write_file`，而不是直接用 `Write`
- 精确替换时用 `guardian_edit_file`，而不是直接用 `Edit`
- 执行命令时用 `guardian_run_bash`，而不是直接用 `Bash`
- 搜索文件时用 `guardian_glob` / `guardian_grep`

这样做的意义不是“功能更多”，而是让工具调用多一层规则、状态和恢复指导。

## 核心能力

### 1. 精确编辑守卫

`guardian_edit_file` 要求模型先读取文件，再从真实文件内容中复制 `old_str`。如果 `old_str` 不存在、出现多次、路径无效或内容过期，Guardian 会返回结构化错误和修复建议。

它重点防止：

- 没有读取文件就编辑
- 把带行号的内容塞进 `old_str`
- 使用过短的 `old_str` 导致多处匹配
- 文件已被修改后继续复用旧内容
- 同一个失败编辑原样重试

### 2. Bash 安全与超时控制

`guardian_run_bash` 在执行命令前做预检，并对常见长时命令调整超时预期。它适合把模型从“直接扔一条 shell 命令”约束到更可控的执行路径。

它重点关注：

- 非交互式命令优先
- 长时命令显式设置 timeout
- 对危险模式进行阻断或要求确认
- 返回 stdout、stderr、退出码和错误分类

### 3. 熔断器

对容易循环失败的工具，Guardian 会记录连续失败次数、失败参数签名和错误类型。

当前重点保护：

- `guardian_edit_file`
- `guardian_run_bash`

状态分为：

| 状态 | 含义 |
| --- | --- |
| `CLOSED` | 正常执行 |
| `WARNING` | 连续失败，要求模型调整参数 |
| `HALF_OPEN` | 参数模式变化或主动解锁后允许重试 |
| `TRIPPED` | 硬熔断，拒绝相同失败模式继续执行 |

硬熔断后可以：

1. 改变参数签名后自动进入 `HALF_OPEN`
2. 调用 `guardian_get_spec(tool_name)` 获取规范并主动解锁

### 4. 风险预检与确认 token

对高风险写入或编辑，Guardian 会根据风险分数返回 `PRE_CHECK_REQUIRED`，并给出一个短期有效的 `ack_token`。

模型必须显式把 token 放进 `_ack` 字段重试，才会继续执行。这让高风险行为从“直接发生”变成“先被看见”。

### 5. 内置知识库指导

Guardian 内置工具使用规范、反模式、恢复流程和示例。失败时会根据工具名与错误类型返回 `guidance`，帮助模型立刻调整，而不是继续盲试。

示例指导包括：

- 编辑前必须 read
- `old_str` 必须逐字符精确匹配
- 多次编辑同一文件后要重新 read
- 长时命令 timeout 建议
- `grep` / `glob` 的结果截断策略

### 6. 会话状态与日志

Guardian 每个 stdio MCP 服务进程维护一个 session，并记录工具状态、熔断状态、失败类型和知识命中情况。

日志默认写入：

```text
~/.claude/guardian/logs/
```

可以用 `guardian_status` 查看当前 session 的模式、工具调用计数和熔断状态。

## 工具列表

| Guardian 工具 | 对应能力 | 主要用途 |
| --- | --- | --- |
| `guardian_read_file` | Read | 读取文件，返回带行号的文本，可指定起止行 |
| `guardian_write_file` | Write | 创建或完整覆写文件，父目录不存在时自动创建 |
| `guardian_edit_file` | Edit | 精确字符串替换，带前置检查、错误指导和熔断 |
| `guardian_run_bash` | Bash | 执行 shell 命令，带安全检查、超时控制和结果结构化 |
| `guardian_glob` | Glob | 按 glob 模式搜索文件 |
| `guardian_grep` | Grep | 优先用 `rg` 搜索文件内容，支持 fallback Python、context、include/exclude、literal、大小写和 max_matches |
| `guardian_get_spec` | Guardian spec | 查询某个 Guardian 工具的规范和最佳实践，并解锁熔断 |
| `guardian_pending_approvals` | Approval queue | 只读列出当前 session 待外部审批的高风险操作 |
| `guardian_status` | Guardian status | 查看当前 session 模式、熔断器和计数状态 |

## 快速开始

### 1. 一条命令安装 MCP + Skill

从 GitHub 安装到当前项目：

```bash
git clone https://github.com/fengfangwen061026/mcp-guardian.git
cd mcp-guardian
./scripts/install.sh
```

如果使用 `pipx` / 全局命令安装，也可以：

```bash
pipx install git+https://github.com/fengfangwen061026/mcp-guardian.git
guardian-install --project /path/to/your/project
```

脚本会自动完成：

- 创建 `.venv`
- 安装 `guardian-mcp`
- 把 `skills/guardian-mcp` 复制到 `~/.claude/skills/guardian-mcp`
- 生成项目 `.mcp.json`
- 提供 `guardian-install` 命令，便于 pipx/全局安装后写入任意项目配置
- 运行测试确认可用

安装后重启 Claude Code，让它重新加载项目 `.mcp.json` 和 skill。

### 2. 手动安装

如果不想使用脚本，可以手动执行：

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
mkdir -p ~/.claude/skills
cp -R skills/guardian-mcp ~/.claude/skills/guardian-mcp
```

然后在项目根目录 `.mcp.json` 写入：

```json
{
  "mcpServers": {
    "guardian": {
      "command": "/absolute/path/to/mcp-guardian/.venv/bin/guardian-mcp",
      "env": {
        "GUARDIAN_MODEL_HINT": "_default"
      }
    }
  }
}
```

如果你希望强制模型走 Guardian 包装层，可以在 Claude Code 设置中拒绝部分原生写入工具：

```json
{
  "permissions": {
    "deny": ["Edit", "Write", "MultiEdit"]
  }
}
```

是否 deny 原生工具取决于你的使用场景。Guardian 本身不要求你禁用原生工具，但禁用后更能保证第三方模型遵守 Guardian 工作流。

### 3. 给模型的项目说明

建议在项目 `CLAUDE.md` 中加入类似规则：

```markdown
文件创建、编辑、命令执行优先使用 guardian_* 系列 MCP 工具：

- 读文件 → guardian_read_file(path, start_line?, end_line?)
- 写文件 → guardian_write_file(path, content)
- 编辑文件 → guardian_edit_file(path, old_str, new_str)
- 执行命令 → guardian_run_bash(command, cwd?, timeout?)
- 搜索文件 → guardian_glob(pattern, path?)
- 搜索内容 → guardian_grep(pattern, path?, include?, exclude?, context_lines?, literal?, case_sensitive?, max_matches?)

编辑文件前必须先 read；old_str 必须从文件实际内容中逐字符复制。
```

本仓库也提供了示例：[`CLAUDE.md`](CLAUDE.md)。

## 推荐工作流

### 修改文件

1. `guardian_read_file` 读取目标文件
2. 从返回内容中复制要替换的片段，去掉行号前缀
3. 调用 `guardian_edit_file`
4. 修改成功后再次 `guardian_read_file` 验证关键内容
5. 如果连续精确替换失败，改为读取完整文件后用 `guardian_write_file` 整体覆写

### 执行命令

1. 优先使用非交互式命令
2. 用户输入或动态参数优先使用 `argv` 模式，例如 `{ "argv": ["python3", "script.py"] }`
3. 只有需要管道、重定向、通配符等 shell 语法时才使用 `command` 字符串
4. 对安装、构建、测试等长时任务设置 timeout
5. 出现失败时先读 `error`、`error_type` 和 `guidance`
6. 不要用完全相同命令无限重试
7. 遇到硬熔断时调用 `guardian_get_spec("guardian_run_bash")`

### 搜索代码

1. 文件名匹配用 `guardian_glob`
2. 内容搜索用 `guardian_grep`
3. 搜索结果过多时缩小 `path` 或 `include`
4. 找到目标文件后再用 `guardian_read_file` 精读

## 返回结构

Guardian 工具会继续返回人类和模型易读的 JSON text，同时在支持的 MCP client 中提供同一份 structured content。

成功示例：

```json
{
  "success": true,
  "content": "1: ...",
  "total_lines": 120,
  "truncated": false
}
```

失败示例：

```json
{
  "success": false,
  "error": "old_str not found",
  "error_class": "MODEL_ERROR",
  "error_type": "old_string_not_found",
  "guidance": [
    {
      "title": "编辑前必须 Read",
      "content": "调用 guardian_edit_file 前必须先调用 guardian_read_file..."
    }
  ]
}
```

常见字段：

| 字段 | 含义 |
| --- | --- |
| `success` | 工具是否成功完成 |
| `error` | 人类可读错误信息 |
| `error_class` | 错误大类，例如模型错误、环境错误、预检失败 |
| `error_type` | 具体错误类型 |
| `guidance` | 针对当前错误的修复建议 |
| `warning` | 连续失败后的软提醒 |
| `circuit_breaker` | 熔断器状态提示 |
| `unlock_hint` | 硬熔断后的解锁建议 |

## 开发与测试

安装开发依赖：

```bash
pip install -e ".[dev]"
```

运行测试：

```bash
python -m pytest tests/ -v
python -m pytest tests/ -q
python -m pytest tests/ -v --timeout=30
```

`--timeout=30` 需要安装 dev extras 中的 `pytest-timeout`。

运行压力测试：

```bash
bash tests/run_stress.sh
```

查看 MCP 服务是否能启动：

```bash
guardian-mcp
```

用 MCP Inspector 验证协议层：

```bash
npx @modelcontextprotocol/inspector .venv/bin/guardian-mcp
```

检查清单：

- `tools/list` 能看到全部 `guardian_*` 工具
- 每个工具都有 annotations
- input schema 字段都有 description 和约束
- `guardian_status` 可用并显示 roots 状态
- `guardian_read_file` / `guardian_glob` 正常返回
- `guardian_run_bash` 能执行安全命令，并阻断危险命令

`guardian-mcp` 是 stdio MCP 服务，正常情况下不会像 HTTP 服务一样打印网页地址。它通常由 Claude Code 拉起并通过 stdio 通信。

## 配置项

当前支持的环境变量：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `GUARDIAN_MODEL_HINT` | `_default` | 给 session 标记模型来源，便于后续统计与策略扩展 |
| `GUARDIAN_ROOTS` | 安装时默认为项目根目录 | 用 `:` 分隔允许访问的根目录，启用后文件、搜索和 bash `cwd` 必须位于这些目录内 |
| `GUARDIAN_ROOT` | 未启用 | 单根目录简写；当 `GUARDIAN_ROOTS` 未设置时生效 |
| `GUARDIAN_REQUIRE_READ_FOR_EDIT` | `1` | 默认要求 edit 提供 `expected_read_id` 或 `expected_file_hash`；设为 `0` 可临时兼容旧流程 |

安装脚本和 `guardian-install` 默认会写入 `GUARDIAN_ROOTS`，如需显式关闭可使用 `guardian-install --no-roots`：

```json
{
  "mcpServers": {
    "guardian": {
      "command": "/absolute/path/to/mcp-guardian/.venv/bin/guardian-mcp",
      "env": {
        "GUARDIAN_MODEL_HINT": "_default",
        "GUARDIAN_ROOTS": "/absolute/path/to/project"
      }
    }
  }
}
```

Roots 限制不是 OS sandbox。它会限制 Guardian 自己处理的 path 和 bash `cwd`，但 shell 命令内部仍可能访问绝对路径；需要强隔离时应使用容器、chroot、seccomp 等系统级沙箱。

## 适合谁使用

MCP Guardian 适合：

- 在 Claude Code 中接入第三方 LLM 的用户
- 经常遇到编辑工具调用失败的用户
- 希望降低模型误操作文件和命令风险的团队
- 想给模型工具调用加一层可观察状态和错误恢复机制的开发者

它不适合：

- 需要完全绕过安全检查的自动化脚本
- 依赖交互式终端会话的任务
- 把 MCP 当作远程常驻 HTTP 服务使用的场景

## 当前限制与升级方向

当前版本已经可用，但仍是 MVP / 初始安全包装层，不应把它当成完整沙箱或高自治 Agent 的最终安全边界。

已完成的 P0 / P1 安全闭环：

- 默认安装写入 `GUARDIAN_ROOTS`，`guardian-install --no-roots` 可显式关闭。
- `guardian_read_file` 返回 `read_id`、`file_hash`、`size`、`mtime_ns`。
- `guardian_edit_file` 默认要求 `expected_read_id` 或 `expected_file_hash`，并能发现 read 后文件变化。
- `guardian_write_file` 默认 `create_only`；覆盖/追加已有文件必须提供 hash，支持 `dry_run diff` 和 backup。
- 已修复 `guardian_run_bash` 的 `argv` 熔断签名。
- 已内置基础 sensitive path policy：`.env`/`.npmrc`/`credentials.json` ask，私钥/证书/Git 凭据 deny。
- 已内置基础 Bash classifier：安全开发命令 allow，破坏性 Git/文件操作 ask，高危提权、下载即执行、宿主根挂载 deny。
- 已区分 `MODEL_ACK_REQUIRED` 和 `APPROVAL_REQUIRED`；高风险操作写入 pending approval，不返回模型可自批准的 `ack_token`。
- 已支持 `.guardian/policy.json` / `.guardian/policy.local.json` 项目级 roots、sensitive paths、bash allow/ask/deny。
- 已增强 `guardian_grep`：优先 `rg`、fallback Python，支持 context / include / exclude / literal / case / max_matches，并逐文件复查 roots 与 sensitive policy。

仍然存在的限制：

- 尚未暴露外部人工审批中心；`guardian_pending_approvals` 目前只读列出 pending 项。
- Bash policy 不是系统级 sandbox，只是命令前分类与阻断。
- 熔断状态是 session 级别；Claude Code 重启 MCP 后会开启新 session。
- 尚无 Git 只读/preview 专用工具和写入后 postcheck。

下一轮开发优先级：

| 阶段 | 目标 | 关键内容 |
| --- | --- | --- |
| Phase 1 | 已完成 | 安装默认写入 `GUARDIAN_ROOTS`，新增 `--no-roots`，补 symlink escape 测试 |
| Phase 2 | 已完成 | `read_id` / `file_hash`，edit 校验 `expected_read_id` / `expected_file_hash` |
| Phase 3 | 已完成 | `mode=create_only/overwrite/append`，`dry_run diff`，`expected_file_hash`，默认 backup |
| Phase 4 | 已完成基础版 | `sensitive.py`，`bash_classifier.py`，allow / ask / deny，危险命令 safer alternative |
| Phase 5 | 已完成 | 区分 `MODEL_ACK_REQUIRED` 和 `APPROVAL_REQUIRED`，记录 pending approvals，暴露 `guardian_pending_approvals` |
| Phase 6 | 部分完成 | 已完成项目级 policy 和 ripgrep backend；Git 只读/preview、diff/multi-edit/apply-patch、postcheck 待后续实现 |

下一轮建议优先做外部审批中心、Git preview 专用工具和写入后 postcheck，而不是继续扩大高风险执行能力。

详细实施总纲见工作室根目录：`../MCP Guardian 最终实施文档.md`。

## License

[GNU Affero General Public License v3.0](LICENSE)

使用 AGPL-3.0：任何基于本项目的衍生产品，包括通过网络提供服务的 SaaS，都必须以相同协议开源。
