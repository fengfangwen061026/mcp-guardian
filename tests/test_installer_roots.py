import json

from guardian.installer import _write_mcp_config


def test_write_mcp_config_includes_roots(tmp_path):
    config_path = tmp_path / ".mcp.json"

    _write_mcp_config(config_path, "guardian-mcp", "_default", str(tmp_path))

    config = json.loads(config_path.read_text(encoding="utf-8"))
    env = config["mcpServers"]["guardian"]["env"]
    assert env["GUARDIAN_ROOTS"] == str(tmp_path)


def test_write_mcp_config_can_omit_roots(tmp_path):
    config_path = tmp_path / ".mcp.json"

    _write_mcp_config(config_path, "guardian-mcp", "_default", None)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    env = config["mcpServers"]["guardian"]["env"]
    assert "GUARDIAN_ROOTS" not in env
