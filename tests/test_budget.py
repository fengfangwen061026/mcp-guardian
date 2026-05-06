import json

import pytest

from guardian.budget import BUDGET, SUCCESS_FIELDS, _truncate_to_tokens, enforce_budget
from guardian.handlers.read_file import execute_read_file
from guardian.handlers.run_bash import execute_run_bash


def test_budget_tables_keep_content_and_stdout():
    assert BUDGET[("guardian_read_file", True)] == 2000
    assert SUCCESS_FIELDS["guardian_read_file"] == ["content"]
    assert BUDGET[("guardian_run_bash", True)] >= 700
    assert "stdout" in SUCCESS_FIELDS["guardian_run_bash"]


@pytest.mark.asyncio
async def test_read_file_content_not_dropped(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("\n".join(f"line {i:04d}" for i in range(1000)), encoding="utf-8")
    result = enforce_budget(await execute_read_file(str(p)), "guardian_read_file")
    assert result["success"] is True
    assert len(result["content"]) >= 6000


def test_truncate_marks_string_and_list():
    assert _truncate_to_tokens("x" * 100, 10).endswith("... [truncated]")
    assert "... [truncated]" in _truncate_to_tokens(["x" * 100, "y"], 5)


@pytest.mark.asyncio
async def test_bash_stdout_budget_keeps_large_output():
    result = enforce_budget(await execute_run_bash("seq 1 1000"), "guardian_run_bash")
    assert result["success"] is True
    assert len(result["stdout"]) >= 2400


def test_response_budget_bound():
    result = enforce_budget({"success": True, "content": "x" * 20000}, "guardian_read_file")
    assert len(json.dumps(result, ensure_ascii=False)) <= BUDGET[("guardian_read_file", True)] * 4 + 250
