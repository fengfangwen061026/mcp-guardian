import os

import pytest

from guardian.handlers.edit_file import handle_edit_file


@pytest.fixture(autouse=True)
def legacy_edit_mode(monkeypatch):
    monkeypatch.setenv("GUARDIAN_REQUIRE_READ_FOR_EDIT", "0")


@pytest.mark.asyncio
async def test_strict_match_rejects_extra_spaces(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello\n", encoding="utf-8")
    result = await handle_edit_file(None, str(p), " hello ", "x")
    assert result["success"] is False
    assert result["error_type"] == "old_string_not_found"


@pytest.mark.asyncio
async def test_crlf_old_matches_lf_file(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("a\nb\n", encoding="utf-8")
    result = await handle_edit_file(None, str(p), "a\r\nb", "A\nB")
    assert result["success"] is True
    assert p.read_text(encoding="utf-8") == "A\nB\n"


@pytest.mark.asyncio
async def test_multiple_match_rejected(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("x\nx\n", encoding="utf-8")
    result = await handle_edit_file(None, str(p), "x", "y")
    assert result["success"] is False
    assert result["error_type"] == "appears_multiple_times"


@pytest.mark.asyncio
async def test_not_found_returns_preview(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("line1\nline2\n", encoding="utf-8")
    result = await handle_edit_file(None, str(p), "missing", "y")
    assert result["success"] is False
    assert "1: line1" in result["file_content"]
