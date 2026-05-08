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
    assert "mode=command" in sig
    assert "has_pipe=True" in sig
    assert ":sig=" in sig


def test_bash_argv_signature_distinguishes_modes_and_values():
    command_sig = extract_signature("guardian_run_bash", {"command": "python3 -c 'print(1)'"})
    argv_sig = extract_signature("guardian_run_bash", {"argv": ["python3", "-c", "print(1)"]})
    other_argv_sig = extract_signature("guardian_run_bash", {"argv": ["python3", "-c", "print(2)"]})

    assert "mode=argv" in argv_sig
    assert command_sig != argv_sig
    assert argv_sig != other_argv_sig
    assert argv_sig == extract_signature("guardian_run_bash", {"argv": ["python3", "-c", "print(1)"]})
