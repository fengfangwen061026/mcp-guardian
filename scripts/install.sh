#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${GUARDIAN_VENV_DIR:-$ROOT_DIR/.venv}"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SKILLS_DIR="$CLAUDE_DIR/skills"
MCP_CONFIG="$ROOT_DIR/.mcp.json"

python_bin="${PYTHON:-python3}"

if [ ! -d "$VENV_DIR" ]; then
  "$python_bin" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -e "$ROOT_DIR[dev]"

mkdir -p "$SKILLS_DIR"
rm -rf "$SKILLS_DIR/guardian-mcp"
cp -R "$ROOT_DIR/skills/guardian-mcp" "$SKILLS_DIR/guardian-mcp"

cat > "$MCP_CONFIG" <<JSON
{
  "mcpServers": {
    "guardian": {
      "command": "$VENV_DIR/bin/guardian-mcp",
      "env": {
        "GUARDIAN_MODEL_HINT": "_default",
        "GUARDIAN_ROOTS": "$ROOT_DIR"
      }
    }
  }
}
JSON

"$VENV_DIR/bin/python" -m pytest "$ROOT_DIR/tests" -q

echo "Guardian MCP installed."
echo "MCP config written to: $MCP_CONFIG"
echo "Skill installed to: $SKILLS_DIR/guardian-mcp"
echo "Restart Claude Code in this project so it reloads .mcp.json and skills."
