from __future__ import annotations

import argparse
import json
import shutil
import sys
from importlib.resources import files
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Guardian MCP config and companion Claude Code skill.")
    parser.add_argument("--project", default=".", help="Project directory where .mcp.json should be written.")
    parser.add_argument("--claude-dir", default=str(Path.home() / ".claude"), help="Claude config directory that contains skills/.")
    parser.add_argument("--command", default=None, help="guardian-mcp command path to write into .mcp.json.")
    parser.add_argument("--model-hint", default="_default", help="GUARDIAN_MODEL_HINT value.")
    parser.add_argument("--roots", default=None, help="Optional GUARDIAN_ROOTS value to add to MCP env.")
    parser.add_argument("--no-roots", action="store_true", help="Do not write GUARDIAN_ROOTS into .mcp.json.")
    args = parser.parse_args()

    project_dir = Path(args.project).expanduser().resolve()
    claude_dir = Path(args.claude_dir).expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    skills_dir = claude_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    command = args.command or _resolve_guardian_mcp()
    roots = None if args.no_roots else (args.roots or str(project_dir))
    _install_skill(skills_dir)
    _write_mcp_config(project_dir / ".mcp.json", command, args.model_hint, roots)

    print(f"MCP config written to: {project_dir / '.mcp.json'}")
    print(f"Skill installed to: {skills_dir / 'guardian-mcp'}")
    print("Restart Claude Code in the project so it reloads the MCP server and skill.")


def _resolve_guardian_mcp() -> str:
    sibling = Path(sys.executable).with_name("guardian-mcp")
    if sibling.exists():
        return str(sibling)
    found = shutil.which("guardian-mcp")
    if found:
        return found
    return "guardian-mcp"


def _install_skill(skills_dir: Path) -> None:
    target = skills_dir / "guardian-mcp"
    if target.exists():
        shutil.rmtree(target)
    source = files("guardian") / "skills" / "guardian-mcp"
    shutil.copytree(source, target)


def _write_mcp_config(path: Path, command: str, model_hint: str, roots: str | None) -> None:
    env = {"GUARDIAN_MODEL_HINT": model_hint}
    if roots:
        env["GUARDIAN_ROOTS"] = roots
    config = {"mcpServers": {"guardian": {"command": command, "env": env}}}
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
