# MCP Guardian

**让第三方 LLM（GPT-4o、Gemini、DeepSeek 等）在 Claude Code 中可靠工作的 MCP 中间件。**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![Tests](https://img.shields.io/badge/tests-151%20passed-green)]()

## 问题背景

Claude Code (CC) 的工具生态（FileEditTool、BashTool 等）专为 Claude 设计和训练。第三方模型接入时面临三类问题：

| 问题 | 表现 | 频率 |
|------|------|------|
| 不读文件就编辑 | `old_string_not_found` | 极高 |
| 失败后无限重试 | 循环消耗 token | 高 |
| 安全 validator 误触发 | 合法命令被拦截 | 中 |

MCP Guardian 在模型和 CC 工具之间插入一个 MCP 层，提供：

- **参数验证**：编辑前强制 Read，old_str 精确匹配检查
- **熔断器**：连续失败自动熔断，防止无限循环
- **知识注入**：错误响应中内嵌修复指导，无需模型额外查询
- **预检拦截**：高风险操作要求模型确认后再执行
- **安全层**：移植 CC 14/22 个 bash 安全 validator

## 架构

```
Claude Code
    ↓ (deny: Edit, Write, MultiEdit)
MCP Guardian
    ├── intercept()   风险评分 + 预检
    ├── circuit.py    熔断器（per-tool, per-session）
    ├── dispatch()    工具执行路由
    ├── budget.py     响应 token 预算
    ├── knowledge.py  28 条预制知识库
    └── persist.py    跨 session 学习持久化
    ↓
文件系统 / subprocess
```

## 快速开始

### 安装

```bash
git clone https://github.com/fengfangwen061026/mcp-guardian.git
cd mcp-guardian
pip install -e ".[dev]"
```

### 配置 Claude Code

在项目的 `.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "guardian": {
      "command": "python",
      "args": ["-m", "guardian.server"],
      "env": {}
    }
  },
  "permissions": {
    "deny": ["Edit", "Write", "MultiEdit"]
  }
}
```

将 `CLAUDE.md` 复制到项目根目录（见 [CLAUDE.md](CLAUDE.md)）。

### 运行测试

```bash
pytest tests/ -v --tb=short
# 期望：151 passed, 0 skipped, 0 failed
```

## 支持的工具

| Guardian 工具 | 对应原版 | 主要增强 |
|-------------|---------|--------|
| `guardian_read_file` | Read | 带行号输出，token 预算控制 |
| `guardian_edit_file` | Edit | 精确匹配验证，容错匹配，熔断器 |
| `guardian_write_file` | Write | 原子写入 |
| `guardian_run_bash` | Bash | 14/22 安全 validator，超时调整 |
| `guardian_glob` | Glob | 结果截断保护 |
| `guardian_grep` | Grep | 结果截断保护 |
| `guardian_get_spec` | — | 熔断解锁，规范查询 |
| `guardian_status` | — | 熔断器状态查询 |

## 已知限制

- Bash 安全层覆盖 14/22 validator（其余 8 个需要 tree-sitter AST 解析）
- stdio MCP 不支持断线重连（CC 原生限制）
- 知识库优先级学习需要积累足够的 session 数据

## License

[GNU Affero General Public License v3.0](LICENSE)

使用 AGPL-3.0：任何基于本项目的衍生产品（包括通过网络提供服务的 SaaS）必须以相同协议开源。
