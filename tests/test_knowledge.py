from guardian.knowledge import ALL_ENTRIES, get_static_guidance
from guardian.state import SessionState


def test_knowledge_entry_count_and_tool_coverage():
    assert len(ALL_ENTRIES) >= 28
    for tool in ["guardian_read_file", "guardian_write_file", "guardian_edit_file", "guardian_run_bash", "guardian_glob", "guardian_grep"]:
        entries = [e for e in ALL_ENTRIES if e.tool_name == tool]
        assert len(entries) >= 3


def test_knowledge_error_coverage():
    edit_text = " ".join(e.id + " " + " ".join(e.error_types) for e in ALL_ENTRIES if e.tool_name == "guardian_edit_file")
    bash_text = " ".join(e.id + " " + " ".join(e.error_types) for e in ALL_ENTRIES if e.tool_name == "guardian_run_bash")
    assert "old_string_not_found" in edit_text
    assert "appears_multiple_times" in edit_text
    assert "command_not_found" in bash_text
    assert "TimeoutError" in bash_text
    assert "nonzero_exit" in bash_text


def test_guidance_under_budget_and_priority_hit():
    session = SessionState("knowledge")
    first = get_static_guidance("guardian_edit_file", "old_string_not_found", session)
    session.knowledge_hits[first[0]["id"]] += 2
    second = get_static_guidance("guardian_edit_file", "old_string_not_found", session)
    assert len(str(second)) <= 150 * 4 + 100
    assert second[0]["id"] == first[0]["id"]
