import pytest
from pathlib import Path

from guardian.circuit import SessionState
from guardian.dispatch import dispatch
from guardian.persist import OffsetStore


@pytest.fixture
def session():
    return SessionState(session_id="test_session", model_hint="_default")


@pytest.fixture
def store(tmp_path):
    return OffsetStore(tmp_path / "test_offsets.db")


@pytest.fixture
def tmpfile(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("line1\nline2\nline3\n", encoding="utf-8")
    return str(p)


@pytest.mark.asyncio
async def test_read_file_success(session, store, tmpfile):
    r = await dispatch(session, "guardian_read_file", {"path": tmpfile}, store)
    assert r["success"]
    assert "1: line1" in r["content"]
    assert r["total_lines"] == 4


@pytest.mark.asyncio
async def test_read_file_range(session, store, tmpfile):
    r = await dispatch(session, "guardian_read_file", {"path": tmpfile, "start_line": 2, "end_line": 2}, store)
    assert r["success"]
    assert "2: line2" in r["content"]
    assert "1: line1" not in r["content"]


@pytest.mark.asyncio
async def test_read_file_not_found(session, store):
    r = await dispatch(session, "guardian_read_file", {"path": "/nonexistent/file"}, store)
    assert not r["success"]
    assert r["error_class"] == "ENV_ERROR"


@pytest.mark.asyncio
async def test_edit_file_success(session, store, tmpfile):
    r = await dispatch(session, "guardian_edit_file", {"path": tmpfile, "old_str": "line2", "new_str": "LINE2"}, store)
    assert r["success"]
    assert "LINE2" in Path(tmpfile).read_text()


@pytest.mark.asyncio
async def test_edit_file_not_found(session, store, tmpfile):
    r = await dispatch(session, "guardian_edit_file", {"path": tmpfile, "old_str": "nonexistent", "new_str": "x"}, store)
    assert not r["success"]
    assert r["error_type"] == "old_string_not_found"
    assert "guidance" in r
    assert "file_content" in r


@pytest.mark.asyncio
async def test_edit_file_multiple_match(session, store, tmp_path):
    p = tmp_path / "dup.txt"
    p.write_text("line\nline\nline\n", encoding="utf-8")
    r = await dispatch(session, "guardian_edit_file", {"path": str(p), "old_str": "line", "new_str": "X"}, store)
    assert not r["success"]
    assert r["error_type"] == "appears_multiple_times"


@pytest.mark.asyncio
async def test_edit_file_circuit_breaker(session, store, tmpfile):
    for _ in range(4):
        r = await dispatch(session, "guardian_edit_file", {"path": tmpfile, "old_str": "absent", "new_str": "x"}, store)
        assert not r["success"]
    r = await dispatch(session, "guardian_edit_file", {"path": tmpfile, "old_str": "absent", "new_str": "x"}, store)
    assert r.get("circuit_breaker") == "HARD_BLOCKED"


@pytest.mark.asyncio
async def test_edit_file_circuit_unlocks_on_sig_change(session, store, tmpfile):
    for _ in range(5):
        await dispatch(session, "guardian_edit_file", {"path": tmpfile, "old_str": "absent_short", "new_str": "x"}, store)
    r = await dispatch(session, "guardian_edit_file", {"path": tmpfile, "old_str": "x" * 300, "new_str": "y"}, store)
    assert r.get("circuit_breaker") != "HARD_BLOCKED"


@pytest.mark.asyncio
async def test_write_file_create(session, store, tmp_path):
    target = str(tmp_path / "new.txt")
    r = await dispatch(session, "guardian_write_file", {"path": target, "content": "hello"}, store)
    assert r["success"]
    assert Path(target).read_text() == "hello"


@pytest.mark.asyncio
async def test_write_file_auto_mkdir(session, store, tmp_path):
    target = str(tmp_path / "deep" / "nested" / "file.txt")
    r = await dispatch(session, "guardian_write_file", {"path": target, "content": "x"}, store)
    assert r["success"]


@pytest.mark.asyncio
async def test_bash_success(session, store):
    r = await dispatch(session, "guardian_run_bash", {"command": "echo hello"}, store)
    assert r["success"]
    assert "hello" in r["stdout"]


@pytest.mark.asyncio
async def test_bash_security_block(session, store):
    r = await dispatch(session, "guardian_run_bash", {"command": "sudo rm -rf /"}, store)
    assert not r["success"]
    assert r["error_class"] == "SECURITY"


@pytest.mark.asyncio
async def test_bash_interactive_block(session, store):
    r = await dispatch(session, "guardian_run_bash", {"command": "python"}, store)
    assert not r["success"]
    assert r["error_type"] == "interactive_command"


@pytest.mark.asyncio
async def test_bash_python_with_arg_ok(session, store, tmp_path):
    script = tmp_path / "ok.py"
    script.write_text("print('ok')\n")
    r = await dispatch(session, "guardian_run_bash", {"command": f"python3 {script}"}, store)
    assert r["success"]
    assert r["execution_mode"] == "shell"
    assert "ok" in r["stdout"]


@pytest.mark.asyncio
async def test_bash_argv_mode_success(session, store):
    r = await dispatch(session, "guardian_run_bash", {"argv": ["python3", "-c", "print('argv ok')"]}, store)
    assert r["success"]
    assert r["execution_mode"] == "argv"
    assert "argv ok" in r["stdout"]


@pytest.mark.asyncio
async def test_bash_rejects_command_and_argv_together(session, store):
    r = await dispatch(session, "guardian_run_bash", {"command": "echo x", "argv": ["echo", "x"]}, store)
    assert not r["success"]
    assert r["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_glob(session, store, tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("x")
    (tmp_path / "c.txt").write_text("x")
    r = await dispatch(session, "guardian_glob", {"pattern": "*.py", "path": str(tmp_path)}, store)
    assert r["success"]
    assert r["count"] == 2


@pytest.mark.asyncio
async def test_grep(session, store, tmp_path):
    (tmp_path / "a.txt").write_text("hello world\nfoo bar\n")
    r = await dispatch(session, "guardian_grep", {"pattern": "hello", "path": str(tmp_path)}, store)
    assert r["success"]
    assert r["count"] == 1


@pytest.mark.asyncio
async def test_get_spec(session, store):
    r = await dispatch(session, "guardian_get_spec", {"tool_name": "guardian_edit_file"}, store)
    assert r["success"]
    assert len(r["spec"]) > 0
    assert any("must_read_first" in e["id"] for e in r["spec"])


@pytest.mark.asyncio
async def test_get_spec_resets_circuit(session, store, tmpfile):
    for _ in range(3):
        await dispatch(session, "guardian_edit_file", {"path": tmpfile, "old_str": "absent", "new_str": "x"}, store)
    state = session.get_state("guardian_edit_file")
    assert state.consecutive_failures > 0
    await dispatch(session, "guardian_get_spec", {"tool_name": "guardian_edit_file"}, store)
    assert state.consecutive_failures == 0


@pytest.mark.asyncio
async def test_budget_does_not_drop_content(session, store, tmp_path):
    p = tmp_path / "med.txt"
    p.write_text("\n".join(f"line {i}" for i in range(100)))
    r = await dispatch(session, "guardian_read_file", {"path": str(p)}, store)
    assert r["success"]
    assert "content" in r
    assert "line 50" in r["content"]
