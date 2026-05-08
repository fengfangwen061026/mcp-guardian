import pytest

from guardian.dispatch import dispatch
from guardian.handlers import search_backend
from guardian.persist import OffsetStore
from guardian.state import SessionState


@pytest.fixture
def session():
    return SessionState(session_id="search_backend_test")


@pytest.fixture
def store(tmp_path):
    return OffsetStore(tmp_path / "events.db")


@pytest.mark.asyncio
async def test_grep_returns_backend_and_context(session, store, tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    result = await dispatch(session, "guardian_grep", {"pattern": "beta", "path": str(tmp_path), "context_lines": 1}, store)

    assert result["success"] is True
    assert result["backend"] in {"rg", "python"}
    assert result["count"] == 1
    assert result["matches"][0]["context_before"] == [{"line": 1, "content": "alpha"}]
    assert result["matches"][0]["context_after"] == [{"line": 3, "content": "gamma"}]


@pytest.mark.asyncio
async def test_grep_literal_case_insensitive_and_include(session, store, tmp_path):
    (tmp_path / "a.py").write_text("Hello.World\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("hello world\n", encoding="utf-8")

    result = await dispatch(
        session,
        "guardian_grep",
        {"pattern": "hello.world", "path": str(tmp_path), "include": "*.py", "literal": True, "case_sensitive": False},
        store,
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["matches"][0]["file"] == "a.py"


@pytest.mark.asyncio
async def test_grep_exclude_and_max_matches(session, store, tmp_path):
    (tmp_path / "a.txt").write_text("hit\nhit\n", encoding="utf-8")
    (tmp_path / "skip.txt").write_text("hit\n", encoding="utf-8")

    result = await dispatch(session, "guardian_grep", {"pattern": "hit", "path": str(tmp_path), "exclude": "skip.txt", "max_matches": 1}, store)

    assert result["success"] is True
    assert result["count"] == 1
    assert result["matches"][0]["file"] == "a.txt"
    assert "truncated_results" in result


@pytest.mark.asyncio
async def test_grep_skips_default_excluded_dirs(session, store, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.txt").write_text("needle\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("needle\n", encoding="utf-8")

    result = await dispatch(session, "guardian_grep", {"pattern": "needle", "path": str(tmp_path)}, store)

    assert result["success"] is True
    assert result["count"] == 1
    assert result["matches"][0]["file"] == "src/a.txt"


@pytest.mark.asyncio
async def test_grep_respects_roots(monkeypatch, session, store, tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setenv("GUARDIAN_ROOTS", str(allowed))

    result = await dispatch(session, "guardian_grep", {"pattern": "x", "path": str(outside)}, store)

    assert result["success"] is False
    assert result["error_type"] == "PathOutsideRoot"


@pytest.mark.asyncio
async def test_grep_skips_symlink_escape(monkeypatch, session, store, tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside.txt"
    allowed.mkdir()
    outside.write_text("needle\n", encoding="utf-8")
    (allowed / "escape.txt").symlink_to(outside)
    monkeypatch.setenv("GUARDIAN_ROOTS", str(allowed))

    result = await dispatch(session, "guardian_grep", {"pattern": "needle", "path": str(allowed)}, store)

    assert result["success"] is True
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_grep_skips_symlink_to_sensitive_file(session, store, tmp_path):
    outside_env = tmp_path / ".env"
    outside_env.write_text("TOKEN=needle\n", encoding="utf-8")
    (tmp_path / "safe.txt").symlink_to(outside_env)

    result = await dispatch(session, "guardian_grep", {"pattern": "needle", "path": str(tmp_path)}, store)

    assert result["success"] is True
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_grep_skips_sensitive_files(session, store, tmp_path):
    (tmp_path / ".env").write_text("TOKEN=needle\n", encoding="utf-8")
    (tmp_path / "safe.txt").write_text("needle\n", encoding="utf-8")

    result = await dispatch(session, "guardian_grep", {"pattern": "needle", "path": str(tmp_path)}, store)

    assert result["success"] is True
    assert result["count"] == 1
    assert result["matches"][0]["file"] == "safe.txt"


@pytest.mark.asyncio
async def test_grep_python_fallback(monkeypatch, session, store, tmp_path):
    monkeypatch.setattr(search_backend.shutil, "which", lambda _: None)
    (tmp_path / "a.txt").write_text("needle\n", encoding="utf-8")

    result = await dispatch(session, "guardian_grep", {"pattern": "needle", "path": str(tmp_path)}, store)

    assert result["success"] is True
    assert result["backend"] == "python"
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_grep_uses_rg_when_available(monkeypatch, session, store, tmp_path):
    monkeypatch.setattr(search_backend.shutil, "which", lambda _: "/usr/bin/rg")
    (tmp_path / "a.txt").write_text("needle\n", encoding="utf-8")

    result = await dispatch(session, "guardian_grep", {"pattern": "needle", "path": str(tmp_path)}, store)

    assert result["success"] is True
    assert result["backend"] == "rg"
    assert result["count"] == 1
