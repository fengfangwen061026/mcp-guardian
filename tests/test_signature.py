from guardian.signature import extract_signature


def test_signature_stable_and_distinct():
    a = extract_signature("guardian_edit_file", {"path": "/a/b.py", "old_str": "x", "new_str": "y"})
    b = extract_signature("guardian_edit_file", {"path": "/a/b.py", "old_str": "x", "new_str": "z"})
    c = extract_signature("guardian_edit_file", {"path": "/a/b.py", "old_str": "x\n" * 20, "new_str": "y"})
    assert a == b
    assert a != c
    assert len(a.split(":")) >= 6
    assert ":sig=" in a


def test_bash_signature_six_dimensions():
    sig = extract_signature("guardian_run_bash", {"command": "echo hi | wc -c"})
    assert len(sig.split(":")) >= 6
    assert "has_pipe=True" in sig
    assert ":sig=" in sig
