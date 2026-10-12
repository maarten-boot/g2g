"""Allowlist validation and the subprocess side of the runner (real bash, real processes)."""

import logging
import os
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

import pytest
from aGit2Git.runner.locks import LockUnavailable, ScriptLocks
from aGit2Git.runner.runner import (
    normalize_dn,
    Busy,
    ConfigError,
    NotAllowed,
    ScriptDef,
    ScriptRunner,
    UnknownScript,
    find_bash,
    load_scripts,
    stream_script,
)
from aGit2Git.runner.runs import RunStore

GROUP = "cn=ops,ou=groups,dc=test"
ROOT = Path(__file__).resolve().parents[2] / "pSwai"  # the django project, which a child process puts on its path


# --- allowlist loading -------------------------------------------------------------------------------------------


def write_config(tmp_path: Path, body: str, files: tuple[str, ...] = ("a.sh",)) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    for name in files:
        (scripts / name).write_text("echo hi\n")
    config = tmp_path / "scripts.toml"
    config.write_text(body)
    return config


def test_valid_config_loads(tmp_path: Path) -> None:
    config = write_config(tmp_path, f'[scripts.a]\nname = "A"\nfile = "a.sh"\ngroups = ["{GROUP}"]\ntimeout = 5\n')
    scripts = load_scripts(config)
    assert scripts["a"].name == "A"
    assert scripts["a"].groups == {GROUP}
    assert scripts["a"].timeout == 5
    assert scripts["a"].path == (tmp_path / "scripts" / "a.sh").resolve()


def test_defaults_applied(tmp_path: Path) -> None:
    config = write_config(tmp_path, f'[scripts.a]\nfile = "a.sh"\ngroups = ["{GROUP}"]\n')
    s = load_scripts(config)["a"]
    assert (s.name, s.description, s.timeout) == ("a", "", 300)


@pytest.mark.parametrize(
    "entry",
    [
        'file = "a.sh"',  # no groups at all: must not become "everyone"
        'file = "a.sh"\ngroups = []',  # empty groups: nobody could run it, so refuse the config
        'file = "a.sh"\ngroups = [""]',
        'file = "a.sh"\ngroups = "cn=ops"',  # string instead of list
        f'groups = ["{GROUP}"]',  # no file
        f'file = "missing.sh"\ngroups = ["{GROUP}"]',
        f'file = "../outside.sh"\ngroups = ["{GROUP}"]',
        f'file = "/etc/passwd"\ngroups = ["{GROUP}"]',
        f'file = "a.sh"\ngroups = ["{GROUP}"]\ntimeout = 0',
        f'file = "a.sh"\ngroups = ["{GROUP}"]\ntimeout = 99999',
        f'file = "a.sh"\ngroups = ["{GROUP}"]\ntimeout = true',
        f'file = "a.sh"\ngroups = ["{GROUP}"]\ntimeout = "60"',
        f'file = "a.sh"\ngroups = ["{GROUP}"]\ntimeuot = 5',  # typo'd key must not be silently ignored
        f'file = "a.sh"\ngroups = ["{GROUP}"]\nargs = "-rf /"',
    ],
)
def test_invalid_entries_are_rejected(tmp_path: Path, entry: str) -> None:
    (tmp_path / "outside.sh").write_text("echo outside\n")
    config = write_config(tmp_path, f"[scripts.a]\n{entry}\n")
    with pytest.raises(ConfigError):
        load_scripts(config)


@pytest.mark.parametrize("script_id", ["A", "has space", "../x", "-lead", "a" * 65, "semi;colon"])
def test_invalid_ids_are_rejected(tmp_path: Path, script_id: str) -> None:
    config = write_config(tmp_path, f'[scripts."{script_id}"]\nfile = "a.sh"\ngroups = ["{GROUP}"]\n')
    with pytest.raises(ConfigError):
        load_scripts(config)


def test_symlink_pointing_outside_scripts_dir_is_rejected(tmp_path: Path) -> None:
    config = write_config(tmp_path, f'[scripts.a]\nfile = "link.sh"\ngroups = ["{GROUP}"]\n')
    secret = tmp_path / "secret.sh"
    secret.write_text("echo secret\n")
    (tmp_path / "scripts" / "link.sh").symlink_to(secret)
    with pytest.raises(ConfigError, match="outside"):
        load_scripts(config)


@pytest.mark.parametrize(
    "body",
    ["", "not toml [[[", "[settings]\n", "[scripts]\n"],
    ids=["empty", "bad-toml", "no-scripts", "empty-scripts"],
)
def test_unusable_files_are_rejected(tmp_path: Path, body: str) -> None:
    config = write_config(tmp_path, body)
    with pytest.raises(ConfigError):
        load_scripts(config)


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_scripts(tmp_path / "nope.toml")


def test_missing_scripts_dir_is_a_config_error(tmp_path: Path) -> None:
    config = tmp_path / "scripts.toml"
    config.write_text(f'[scripts.a]\nfile = "a.sh"\ngroups = ["{GROUP}"]\n')
    with pytest.raises(ConfigError, match="does not exist"):
        load_scripts(config)


# --- running -----------------------------------------------------------------------------------------------------


def make_script(tmp_path: Path, body: str, timeout: int = 10, name: str = "s.sh") -> ScriptDef:
    path = tmp_path / name
    path.write_text(body)
    return ScriptDef("s", "S", "", path, frozenset({GROUP}), timeout)


def run(script: ScriptDef, user: str = "alice", **kwargs: Any) -> str:
    return b"".join(stream_script(script, user, bash=find_bash(), **kwargs)).decode()


def test_output_is_combined_stdout_and_stderr_with_exit_code(tmp_path: Path) -> None:
    out = run(make_script(tmp_path, "echo to-out\necho to-err >&2\nexit 3\n"))
    assert "to-out" in out and "to-err" in out
    assert out.rstrip().endswith("[exit code 3]")


def test_output_streams_before_the_script_finishes(tmp_path: Path) -> None:
    script = make_script(tmp_path, "echo first\nsleep 3\necho second\n")
    stream = stream_script(script, "alice", bash=find_bash())
    started = time.monotonic()
    assert next(stream) == b"first\n"
    assert time.monotonic() - started < 2.5  # got the first line well before the script ended
    stream.close()


def test_child_environment_is_scrubbed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LDAP_BIND_PASSWORD", "hunter2-secret")
    monkeypatch.setenv("FLASK_SECRET_KEY", "flask-secret")
    monkeypatch.setenv("BASH_ENV", str(tmp_path / "evil.sh"))
    out = run(make_script(tmp_path, "env | sort\n"), user="alice")
    assert "hunter2-secret" not in out and "flask-secret" not in out and "evil.sh" not in out
    assert "RUNNER_USER=alice" in out and "RUNNER_SCRIPT=s" in out


def test_stdin_is_closed(tmp_path: Path) -> None:
    out = run(make_script(tmp_path, "read -r line && echo got-$line || echo no-stdin\n"))
    assert "no-stdin" in out


def test_username_cannot_inject_environment_or_break_argv(tmp_path: Path) -> None:
    out = run(make_script(tmp_path, 'printf "[%s]\\n" "$RUNNER_USER"\n'), user="x\0; rm -rf /; $(id)")
    assert "[x; rm -rf /; $(id)]" in out  # passed as inert data, NUL stripped, nothing executed


def test_timeout_kills_script_and_reports_it(tmp_path: Path) -> None:
    started = time.monotonic()
    out = run(make_script(tmp_path, "echo start\nsleep 60\necho never\n", timeout=1))
    assert time.monotonic() - started < 8
    assert "start" in out and "never" not in out
    assert "timed out after 1s" in out


def test_timeout_kills_the_whole_process_group(tmp_path: Path) -> None:
    pidfile = tmp_path / "child.pid"
    started = time.monotonic()
    out = run(make_script(tmp_path, f"sleep 60 &\necho $! > {pidfile}\nwait\n", timeout=1))
    assert "timed out" in out and time.monotonic() - started < 8
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and _alive(pid):
        time.sleep(0.05)
    assert not _alive(pid), "grandchild survived the timeout"


def test_output_cap_kills_a_flooding_script(tmp_path: Path) -> None:
    started = time.monotonic()
    out = run(make_script(tmp_path, "yes flood\n"), max_output=2000)
    assert time.monotonic() - started < 8
    assert "output limit of 2000 bytes exceeded" in out
    assert len(out) < 2000 + 200


def test_closing_the_stream_lets_the_script_finish(tmp_path: Path) -> None:
    """Viewer disconnects mid-run: the script is NOT killed, it runs to completion (a half-done sync is worse)."""
    marker = tmp_path / "finished"
    script = make_script(tmp_path, f"echo started\nsleep 1\ntouch {marker}\n")
    stream = stream_script(script, "alice", bash=find_bash())
    assert next(stream) == b"started\n"
    stream.close()
    assert marker.exists(), "script was cut short by the disconnect"


def test_detached_script_keeps_writing_without_dying_of_sigpipe(tmp_path: Path) -> None:
    """Nobody reads after the viewer left; closing the pipe instead of draining it would SIGPIPE-kill the script."""
    marker = tmp_path / "finished"
    script = make_script(tmp_path, f"echo started\nsleep 0.5\necho still-talking\ntouch {marker}\n")
    stream = stream_script(script, "alice", bash=find_bash())
    assert next(stream) == b"started\n"
    stream.close()
    assert marker.exists(), "script died when it wrote after the viewer went away"


def test_detached_script_with_lots_of_output_is_not_blocked(tmp_path: Path) -> None:
    """A full pipe (64 KiB) would stall the script forever if nobody drained it."""
    marker = tmp_path / "finished"
    script = make_script(tmp_path, f"echo started\nsleep 0.3\nhead -c 1000000 /dev/zero | tr '\\0' x\ntouch {marker}\n")
    stream = stream_script(script, "alice", bash=find_bash())
    assert next(stream) == b"started\n"
    started = time.monotonic()
    stream.close()
    assert marker.exists()
    assert time.monotonic() - started < 8


def test_detached_script_is_still_bounded_by_its_timeout(tmp_path: Path) -> None:
    pidfile = tmp_path / "pid"
    script = make_script(tmp_path, f"echo $$ > {pidfile}\necho started\nsleep 60\n", timeout=1)
    stream = stream_script(script, "alice", bash=find_bash())
    assert next(stream) == b"started\n"
    started = time.monotonic()
    stream.close()
    assert time.monotonic() - started < 8, "timeout must still stop a detached run"
    assert not _alive(int(pidfile.read_text()))


def test_script_that_closes_stdout_early_is_still_waited_for(tmp_path: Path) -> None:
    """EOF on the pipe is not the end of the run: the lock must stay held until the process really exits."""
    marker = tmp_path / "finished"
    script = make_script(tmp_path, f"exec >&- 2>&-\nsleep 1\ntouch {marker}\n")
    out = run(script)
    assert marker.exists(), "run was reported finished while the script was still working"
    assert "[exit code 0]" in out


def test_scripts_run_in_their_own_directory(tmp_path: Path) -> None:
    out = run(make_script(tmp_path, "pwd\n"))
    assert str(tmp_path.resolve()) in out


# --- ScriptRunner: authorization and locking ---------------------------------------------------------------------


def make_runner(tmp_path: Path) -> ScriptRunner:
    return ScriptRunner({"s": make_script(tmp_path, "echo ok\n")})


def test_runner_denies_without_group_and_does_not_start(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    with pytest.raises(NotAllowed):
        runner.start("s", "mallory", {"cn=other"})
    with pytest.raises(NotAllowed):
        runner.start("s", "mallory", set())


def test_runner_unknown_script(tmp_path: Path) -> None:
    with pytest.raises(UnknownScript):
        make_runner(tmp_path).start("nope", "alice", {GROUP})


def test_lock_released_when_stream_is_closed_without_being_read(tmp_path: Path) -> None:
    """Regression guard: an unstarted generator never runs its finally block, so the lock must not live there."""
    runner = make_runner(tmp_path)
    first = runner.start("s", "alice", {GROUP})
    with pytest.raises(Busy):
        runner.start("s", "alice", {GROUP})
    first.close()  # never iterated
    runner.start("s", "alice", {GROUP}).close()  # no Busy: lock is free again


def test_lock_released_after_full_run_and_close_is_idempotent(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    stream = runner.start("s", "alice", {GROUP})
    assert b"ok" in b"".join(stream)
    stream.close()
    stream.close()
    runner.start("s", "alice", {GROUP}).close()


def test_visible_to_filters_and_sorts(tmp_path: Path) -> None:
    other = ScriptDef("z", "Zeta", "", tmp_path / "s.sh", frozenset({"cn=x"}), 5)
    first = ScriptDef("b", "alpha", "", tmp_path / "s.sh", frozenset({GROUP}), 5)
    second = ScriptDef("a", "Beta", "", tmp_path / "s.sh", frozenset({GROUP}), 5)
    runner = ScriptRunner({"z": other, "b": first, "a": second})
    assert [s.id for s in runner.visible_to({GROUP})] == ["b", "a"]
    assert runner.all_groups == {GROUP, "cn=x"}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # a zombie still answers kill(0); treat "defunct" as dead
    try:
        return "Z" not in Path(f"/proc/{pid}/stat").read_text().split(") ")[-1][:1]
    except OSError:
        return False


# --- audit trail -------------------------------------------------------------------------------------------------


def test_audit_log_records_start_and_finish(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="aGit2Git.runner")
    run(make_script(tmp_path, "exit 4\n"), user="alice")
    text = caplog.text
    assert "start user='alice' script=s" in text
    assert "finish user='alice' script=s" in text and "exit code 4" in text


def test_audit_log_records_denied_attempts(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="aGit2Git.runner")
    with pytest.raises(NotAllowed):
        make_runner(tmp_path).start("s", "mallory", {"cn=other"})
    assert "denied user='mallory' script=s" in caplog.text


def test_audit_log_records_detach(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="aGit2Git.runner")
    stream = stream_script(make_script(tmp_path, "echo hi\nsleep 0.2\n"), "alice", bash=find_bash())
    next(stream)
    stream.close()
    assert "detached user='alice' script=s" in caplog.text


def test_usernames_with_newlines_cannot_forge_log_lines(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="aGit2Git.runner")
    run(make_script(tmp_path, "true\n"), user="x\nfinish user='root' script=s status='exit code 0'")
    assert "\nfinish user='root'" not in caplog.text


def test_audit_log_records_busy_rejections(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="aGit2Git.runner")
    runner = make_runner(tmp_path)
    first = runner.start("s", "alice", {GROUP})
    with pytest.raises(Busy):
        runner.start("s", "bob", {GROUP})
    first.close()
    assert "busy user='bob' script=s" in caplog.text


def test_placeholder_group_from_the_example_file_is_flagged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="aGit2Git.runner")
    config = write_config(
        tmp_path, '[scripts.a]\nfile = "a.sh"\ngroups = ["cn=script-runners,ou=groups,dc=example,dc=com"]\n'
    )
    assert "a" in load_scripts(config)  # still loads: it is a warning, not an error
    assert "placeholder" in caplog.text and "scripts.example.toml" in caplog.text


def test_real_group_is_not_flagged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="aGit2Git.runner")
    load_scripts(write_config(tmp_path, f'[scripts.a]\nfile = "a.sh"\ngroups = ["{GROUP}"]\n'))
    assert "placeholder" not in caplog.text


# --- reload: the allowlist can be re-read while the server runs --------------------------------------------------


def toml_for(*entries: tuple[str, str, str]) -> str:
    """(id, file, group) -> a scripts.toml with one entry each."""
    return "".join(
        f'[scripts.{sid}]\nname = "{sid.upper()}"\nfile = "{file}"\ngroups = ["{group}"]\n\n'
        for sid, file, group in entries
    )


def reloadable(
    tmp_path: Path, body: str, files: tuple[str, ...] = ("a.sh", "b.sh", "c.sh")
) -> tuple[ScriptRunner, Path]:
    config = write_config(tmp_path, body, files)
    return ScriptRunner(load_scripts(config), config_file=config), config


def test_reload_picks_up_added_removed_and_changed_scripts(tmp_path: Path) -> None:
    runner, config = reloadable(tmp_path, toml_for(("a", "a.sh", GROUP), ("b", "b.sh", GROUP)))
    config.write_text(toml_for(("a", "a.sh", "cn=other"), ("c", "c.sh", GROUP)))  # a: other group, b: gone, c: new
    assert runner.reload() is True
    assert set(runner.scripts) == {"a", "c"}
    assert runner.scripts["a"].groups == {"cn=other"}
    assert runner.all_groups == {"cn=other", GROUP}


def test_reload_of_an_unchanged_file_reports_no_change(tmp_path: Path) -> None:
    runner, _ = reloadable(tmp_path, toml_for(("a", "a.sh", GROUP)))
    assert runner.reload() is False


def test_removed_and_regrouped_scripts_are_enforced_immediately(tmp_path: Path) -> None:
    runner, config = reloadable(tmp_path, toml_for(("a", "a.sh", GROUP), ("b", "b.sh", GROUP)))
    config.write_text(toml_for(("a", "a.sh", "cn=other")))
    runner.reload()
    with pytest.raises(UnknownScript):
        runner.start("b", "alice", {GROUP})  # no longer in the allowlist at all
    with pytest.raises(NotAllowed):
        runner.start("a", "alice", {GROUP})  # still there, but the user's group no longer matches
    assert [s.id for s in runner.visible_to({GROUP})] == []


def test_a_broken_file_keeps_the_list_in_force_and_a_fixed_one_is_picked_up(tmp_path: Path) -> None:
    runner, config = reloadable(tmp_path, toml_for(("a", "a.sh", GROUP)))
    before = dict(runner.scripts)
    for broken in ("not toml [[[", toml_for(("a", "missing.sh", GROUP)), '[scripts.a]\nfile = "a.sh"\n', ""):
        config.write_text(broken)
        with pytest.raises(ConfigError):
            runner.reload()
        assert runner.scripts == before  # nothing half-applied
    config.write_text(toml_for(("a", "a.sh", GROUP), ("b", "b.sh", GROUP)))
    assert runner.reload() is True and set(runner.scripts) == {"a", "b"}


def test_a_deleted_file_keeps_the_list_in_force(tmp_path: Path) -> None:
    runner, config = reloadable(tmp_path, toml_for(("a", "a.sh", GROUP)))
    config.unlink()
    with pytest.raises(ConfigError):
        runner.reload()
    assert set(runner.scripts) == {"a"}


def test_runner_without_a_file_cannot_reload(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="nothing to reload"):
        make_runner(tmp_path).reload()


def test_a_script_removed_and_added_back_cannot_run_twice_in_parallel(tmp_path: Path) -> None:
    """The lock must outlive the reload: otherwise 'remove, re-add' would be a way around one-run-at-a-time."""
    runner, config = reloadable(tmp_path, toml_for(("a", "a.sh", GROUP)))
    running = runner.start("a", "alice", {GROUP})  # a run in progress
    config.write_text(toml_for(("b", "b.sh", GROUP)))
    runner.reload()
    config.write_text(toml_for(("a", "a.sh", GROUP)))
    runner.reload()
    with pytest.raises(Busy):
        runner.start("a", "bob", {GROUP})
    running.close()
    runner.start("a", "bob", {GROUP}).close()


def test_a_run_in_progress_is_not_affected_by_a_reload(tmp_path: Path) -> None:
    script = make_script(tmp_path, "echo before\nsleep 1\necho after\n", timeout=10)
    runner = ScriptRunner({"s": script}, config_file=tmp_path / "unused.toml")
    stream = runner.start("s", "alice", {GROUP})
    assert next(stream) == b"before\n"
    runner.scripts = {}  # as if a reload had removed it meanwhile
    assert b"after" in b"".join(stream)  # the run carries on with the definition it started with
    stream.close()


def test_reload_is_logged_and_warns_about_placeholders_only_when_they_are_new(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="aGit2Git.runner")
    runner, config = reloadable(tmp_path, toml_for(("a", "a.sh", GROUP)))
    placeholder = "cn=script-runners,ou=groups,dc=example,dc=com"
    config.write_text(toml_for(("a", "a.sh", GROUP), ("b", "b.sh", placeholder)))
    runner.reload()
    assert "scripts reloaded" in caplog.text and "added=['b']" in caplog.text
    assert caplog.text.count("placeholder group") == 1
    runner.reload()  # clicking Refresh again must not repeat it
    assert caplog.text.count("placeholder group") == 1


def test_readers_never_see_a_mixture_during_reloads(tmp_path: Path) -> None:
    runner, config = reloadable(tmp_path, toml_for(("a", "a.sh", GROUP), ("b", "b.sh", GROUP)))
    one = toml_for(("a", "a.sh", GROUP), ("b", "b.sh", GROUP))
    two = toml_for(("c", "c.sh", GROUP))
    seen: set[tuple[str, ...]] = set()
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            seen.add(tuple(s.id for s in runner.visible_to({GROUP})))

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    for i in range(40):
        config.write_text(one if i % 2 else two)
        runner.reload()
    stop.set()
    for t in threads:
        t.join()
    assert seen <= {("a", "b"), ("c",)}


# --- recording the output of runs (the "last run" view) ----------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


def recorded_runner(tmp_path: Path, store: RunStore, body: str, timeout: int = 10) -> ScriptRunner:
    return ScriptRunner({"s": make_script(tmp_path, body, timeout=timeout)}, store=store)


def test_the_recorded_output_is_exactly_what_the_viewer_got(tmp_path: Path, store: RunStore) -> None:
    runner = recorded_runner(tmp_path, store, "echo one\necho two >&2\nexit 3\n")
    stream = runner.start("s", "alice", {GROUP})
    seen = b"".join(stream)
    stream.close()
    info = store.last("s")
    assert info is not None and stream.run_id == info.run_id
    assert store.read(info, 0, 10_000) == seen  # including the closing status line
    assert (info.user, info.exit_code, info.status, info.size) == ("alice", 3, "exit code 3", len(seen))
    assert not info.running and not info.ok
    assert seen.endswith(b"[exit code 3]\n")


def test_a_run_nobody_watches_is_still_recorded_in_full(tmp_path: Path, store: RunStore) -> None:
    """The viewer's tab is closed after the first line: the rest of the run must still be in the record."""
    runner = recorded_runner(tmp_path, store, "echo first\nsleep 0.5\necho later\necho even-later\n")
    stream = runner.start("s", "alice", {GROUP})
    assert next(stream) == b"first\n"
    stream.close()  # the viewer is gone; close() waits for the script to end
    info = store.last("s")
    assert info is not None and not info.running and info.exit_code == 0
    assert store.read(info, 0, 10_000) == b"first\nlater\neven-later\n\n[exit code 0]\n"


def test_a_detached_flood_is_still_bounded_by_the_output_cap(tmp_path: Path, store: RunStore) -> None:
    """Nobody watches AND the script floods: recording must not become a way to fill the disk."""
    runner = recorded_runner(tmp_path, store, "echo start\nsleep 0.3\nyes flood\n")
    stream = runner.start("s", "alice", {GROUP})
    assert next(stream) == b"start\n"
    stream.close()
    info = store.last("s")
    assert info is not None and info.status is not None and "output limit" in info.status
    assert info.size < 11 * 1024 * 1024  # the default cap is 10 MiB: whatever happened, it stopped there
    assert not info.running


def test_the_output_cap_is_recorded_for_an_attached_viewer_too(tmp_path: Path, store: RunStore) -> None:
    script = make_script(tmp_path, "yes flood\n")
    recorder = store.begin("s", "alice")
    out = b"".join(stream_script(script, "alice", bash=find_bash(), max_output=2000, recorder=recorder))
    info = store.last("s")
    assert info is not None and info.status == "output limit of 2000 bytes exceeded, killed"
    assert store.read(info, 0, 10_000) == out and info.size < 2000 + 200


def test_a_timeout_is_recorded(tmp_path: Path, store: RunStore) -> None:
    runner = recorded_runner(tmp_path, store, "echo start\nsleep 60\n", timeout=1)
    stream = runner.start("s", "alice", {GROUP})
    b"".join(stream)
    stream.close()
    info = store.last("s")
    assert info is not None and info.status == "timed out after 1s and was killed"
    assert b"start" in store.read(info, 0, 1000)


def test_a_run_can_be_followed_while_it_is_going(tmp_path: Path, store: RunStore) -> None:
    runner = recorded_runner(tmp_path, store, "echo one\nsleep 1\necho two\n")
    stream = runner.start("s", "alice", {GROUP})
    assert next(stream) == b"one\n"
    live = store.last("s")
    assert live is not None and live.running and live.size == len(b"one\n")  # a second person sees it now
    assert store.read(live, 0, 100) == b"one\n"
    b"".join(stream)
    stream.close()
    done = store.last("s")
    assert done is not None and not done.running and b"two" in store.read(done, 0, 100)


def test_closing_a_stream_that_never_started_leaves_no_run_marked_as_running(tmp_path: Path, store: RunStore) -> None:
    runner = recorded_runner(tmp_path, store, "echo should never run\n")
    stream = runner.start("s", "alice", {GROUP})
    stream.close()  # e.g. the browser went away before the first byte was asked for
    info = store.last("s")
    assert info is not None and not info.running and info.status == "cancelled before it started"
    assert store.read(info, 0, 100) == b""
    runner.start("s", "bob", {GROUP}).close()  # and the lock was released


def test_the_next_run_replaces_the_previous_record(tmp_path: Path, store: RunStore) -> None:
    runner = recorded_runner(tmp_path, store, "echo hello\n")
    first = runner.start("s", "alice", {GROUP})
    b"".join(first)
    first.close()
    second = runner.start("s", "bob", {GROUP})
    b"".join(second)
    second.close()
    info = store.last("s")
    assert info is not None and info.user == "bob" and info.run_id == second.run_id != first.run_id
    assert store.lookup("s", first.run_id or "") is None


def test_a_script_that_cannot_be_recorded_still_runs(
    tmp_path: Path, store: RunStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise OSError("read-only file system")

    monkeypatch.setattr(store, "begin", broken)
    runner = recorded_runner(tmp_path, store, "echo still works\n")
    stream = runner.start("s", "alice", {GROUP})
    assert b"still works" in b"".join(stream) and stream.run_id is None
    stream.close()
    assert "cannot record the run of s" in caplog.text


def test_a_recording_that_fails_midway_does_not_disturb_the_run(
    tmp_path: Path, store: RunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = make_script(tmp_path, "echo one\nsleep 0.2\necho two\n")
    recorder = store.begin("s", "alice")

    def disk_exploded(*args: object, **kwargs: object) -> int:
        raise OSError("disk exploded")

    fake_os = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os)})  # only the store's view of os
    fake_os.write = disk_exploded
    monkeypatch.setattr("aGit2Git.runner.runs.os", fake_os)
    out = b"".join(stream_script(script, "alice", bash=find_bash(), recorder=recorder))
    monkeypatch.undo()
    assert b"one" in out and b"two" in out and out.endswith(b"[exit code 0]\n")  # the viewer got everything anyway
    info = store.last("s")
    assert info is not None and info.status is not None and "could not be saved completely" in info.status


def test_without_a_store_nothing_is_recorded_and_there_is_no_run_id(tmp_path: Path) -> None:
    runner = ScriptRunner({"s": make_script(tmp_path, "echo hi\n")})
    stream = runner.start("s", "alice", {GROUP})
    assert stream.run_id is None and b"hi" in b"".join(stream)
    stream.close()


def test_the_recording_never_contains_the_environment_the_script_does_not_get(
    tmp_path: Path, store: RunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LDAP_BIND_PASSWORD", "hunter2-secret")
    runner = recorded_runner(tmp_path, store, "env | sort\n")
    stream = runner.start("s", "alice", {GROUP})
    b"".join(stream)
    stream.close()
    info = store.last("s")
    assert info is not None and b"hunter2-secret" not in store.read(info, 0, 100_000)


# --- one run of a script at a time, between users and between worker processes -----------------------------------


def workers(tmp_path: Path, store: RunStore, body: str, count: int = 2) -> list[ScriptRunner]:
    """`count` runners sharing one script, one runs directory and one lock directory: like `count` server workers."""
    (tmp_path / "locks").mkdir(exist_ok=True)
    script = make_script(tmp_path, body)
    return [ScriptRunner({"s": script}, store=store, locks=ScriptLocks(tmp_path / "locks")) for _ in range(count)]


def test_a_second_worker_cannot_run_the_script_while_the_first_is_running(tmp_path: Path, store: RunStore) -> None:
    first, second = workers(tmp_path, store, "echo going\nsleep 1\necho gone\n")
    running = first.start("s", "alice", {GROUP})
    assert next(running) == b"going\n"
    with pytest.raises(Busy) as refused:
        second.start("s", "bob", {GROUP})
    assert refused.value.holder is not None and refused.value.holder.user == "alice"
    b"".join(running)
    running.close()
    after = second.start("s", "bob", {GROUP})  # the next user may rerun it once it has finished
    assert b"going" in b"".join(after)
    after.close()


def test_a_refused_attempt_does_not_disturb_the_run_that_is_going(tmp_path: Path, store: RunStore) -> None:
    first, second = workers(tmp_path, store, "echo going\nsleep 1\n")
    running = first.start("s", "alice", {GROUP})
    next(running)
    record = store.last("s")
    with pytest.raises(Busy):
        second.start("s", "bob", {GROUP})
    now = store.last("s")
    assert record is not None and now is not None
    assert (now.run_id, now.user, now.running) == (record.run_id, "alice", True)  # alice's record is still hers
    b"".join(running)
    running.close()


def test_a_refused_attempt_starts_nothing(tmp_path: Path, store: RunStore) -> None:
    marker = tmp_path / "marker"
    first, second = workers(tmp_path, store, f"echo run >> {marker}\nsleep 1\n")
    running = first.start("s", "alice", {GROUP})
    time.sleep(0.3)  # let the script start and write its marker
    for _ in range(5):
        with pytest.raises(Busy):
            second.start("s", "bob", {GROUP})
    b"".join(running)
    running.close()
    assert marker.read_text().count("run") == 1  # the script ran exactly once


def test_the_lock_is_taken_before_anything_is_recorded_or_started(tmp_path: Path, store: RunStore) -> None:
    marker = tmp_path / "marker"
    script = make_script(tmp_path, f"echo ran > {marker}\n")
    runner = ScriptRunner({"s": script}, store=store, locks=ScriptLocks(tmp_path / "no-such-directory"))
    with pytest.raises(LockUnavailable):
        runner.start("s", "alice", {GROUP})
    assert store.last("s") is None and not marker.exists()  # no record, no process: the run did not happen


def test_the_lock_is_given_back_if_starting_fails_unexpectedly(
    tmp_path: Path, store: RunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    (runner,) = workers(tmp_path, store, "echo hi\n", count=1)

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("something unexpected")

    monkeypatch.setattr(store, "begin", boom)
    with pytest.raises(RuntimeError):
        runner.start("s", "alice", {GROUP})
    monkeypatch.undo()
    assert runner.locks.holder("s") is None  # not left locked by a run that never started
    runner.start("s", "bob", {GROUP}).close()


def test_the_lock_is_held_for_the_whole_run_and_given_back_when_it_is_closed(tmp_path: Path, store: RunStore) -> None:
    (runner,) = workers(tmp_path, store, "echo one\nsleep 1\necho two\n", count=1)
    assert runner.locks.holder("s") is None
    stream = runner.start("s", "alice", {GROUP})
    holder = runner.locks.holder("s")
    assert holder is not None and holder.user == "alice"  # held from the moment of starting, even before any output
    next(stream)
    assert runner.locks.holder("s") is not None
    b"".join(stream)
    assert runner.locks.holder("s") is not None  # output done, response not closed yet
    stream.close()
    assert runner.locks.holder("s") is None


def test_a_run_nobody_watches_keeps_the_lock_until_the_script_is_over(tmp_path: Path, store: RunStore) -> None:
    """The viewer left; the script is still running, so nobody else may start it."""
    first, second = workers(tmp_path, store, "echo one\nsleep 1.5\necho two\n")
    stream = first.start("s", "alice", {GROUP})
    next(stream)
    closer = threading.Thread(target=stream.close)  # close() waits for the script to end
    closer.start()
    time.sleep(0.5)
    with pytest.raises(Busy):
        second.start("s", "bob", {GROUP})  # still running in the background
    closer.join()
    second.start("s", "bob", {GROUP}).close()


def test_the_lock_is_not_handed_down_to_the_script(tmp_path: Path, store: RunStore) -> None:
    (runner,) = workers(tmp_path, store, "ls -l /proc/$$/fd\n", count=1)
    stream = runner.start("s", "alice", {GROUP})
    out = b"".join(stream).decode()
    stream.close()
    assert ".lock" not in out  # a script that kept it open would keep the script locked for as long as it lives


def test_of_many_simultaneous_starts_exactly_one_runs(tmp_path: Path, store: RunStore) -> None:
    runners = workers(tmp_path, store, "echo hi\nsleep 1\n", count=3)
    barrier = threading.Barrier(12)
    streams: list[object] = []
    busy: list[str] = []

    def attempt(i: int) -> None:
        barrier.wait()
        try:
            streams.append(runners[i % 3].start("s", f"user{i}", {GROUP}))
        except Busy:
            busy.append(f"user{i}")

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(streams) == 1 and len(busy) == 11
    for stream in streams:
        stream.close()  # type: ignore[attr-defined]


def test_a_script_removed_and_added_back_stays_locked_across_workers(tmp_path: Path, store: RunStore) -> None:
    (tmp_path / "locks").mkdir()
    config = write_config(tmp_path, toml_for(("a", "a.sh", GROUP)), files=("a.sh", "b.sh"))
    locks_dir = tmp_path / "locks"
    first = ScriptRunner(load_scripts(config), config_file=config, locks=ScriptLocks(locks_dir))
    second = ScriptRunner(load_scripts(config), config_file=config, locks=ScriptLocks(locks_dir))
    running = first.start("a", "alice", {GROUP})
    config.write_text(toml_for(("b", "b.sh", GROUP)))
    second.reload()
    config.write_text(toml_for(("a", "a.sh", GROUP)))
    second.reload()  # "a" is back, but alice's run of it is still going on the other worker
    with pytest.raises(Busy):
        second.start("a", "bob", {GROUP})
    running.close()
    second.start("a", "bob", {GROUP}).close()


def test_scripts_do_not_lock_each_other_out(tmp_path: Path, store: RunStore) -> None:
    (tmp_path / "locks").mkdir()
    one, two = make_script(tmp_path, "sleep 1\n", name="one.sh"), make_script(tmp_path, "sleep 1\n", name="two.sh")
    one, two = (
        ScriptDef("one", "One", "", one.path, one.groups, 10),
        ScriptDef("two", "Two", "", two.path, two.groups, 10),
    )
    runner = ScriptRunner({"one": one, "two": two}, locks=ScriptLocks(tmp_path / "locks"))
    a, b = runner.start("one", "alice", {GROUP}), runner.start("two", "bob", {GROUP})  # both at the same time: fine
    a.close()
    b.close()


def test_busy_attempts_are_logged_with_the_holder(
    tmp_path: Path, store: RunStore, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="aGit2Git.runner")
    first, second = workers(tmp_path, store, "sleep 1\n")
    running = first.start("s", "alice", {GROUP})
    with pytest.raises(Busy):
        second.start("s", "bob", {GROUP})
    running.close()
    assert "busy user='bob' script=s" in caplog.text and "held by 'alice'" in caplog.text


def test_a_lock_that_cannot_be_taken_is_logged(
    tmp_path: Path, store: RunStore, caplog: pytest.LogCaptureFixture
) -> None:
    script = make_script(tmp_path, "echo hi\n")
    runner = ScriptRunner({"s": script}, locks=ScriptLocks(tmp_path / "missing"))
    with pytest.raises(LockUnavailable):
        runner.start("s", "alice", {GROUP})
    assert "cannot lock s for user='alice', so it is not run" in caplog.text


# --- a run that outlives its crashed server ----------------------------------------------------------------------


def test_a_run_that_outlives_its_crashed_server_still_blocks_the_next_one(tmp_path: Path, store: RunStore) -> None:
    """kill -9 drops the server's lock at once; the script it started carries on and must still count as running."""
    (tmp_path / "locks").mkdir()
    marker = tmp_path / "script-finished"
    script = make_script(tmp_path, f"echo going\nsleep 2.5\ntouch {marker}\n", timeout=30)
    config = write_config(tmp_path, "", files=())
    config.write_text(f'[scripts.s]\nfile = "{script.path.name}"\ngroups = ["{GROUP}"]\ntimeout = 30\n')
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / script.path.name).write_text(script.path.read_text())

    code = f"""
import sys, time
sys.path.insert(0, {str(ROOT)!r})
from pathlib import Path
from aGit2Git.runner.locks import ScriptLocks
from aGit2Git.runner.runner import ScriptRunner, load_scripts
runner = ScriptRunner(load_scripts(Path({str(config)!r})), locks=ScriptLocks(Path({str(tmp_path / "locks")!r})))
stream = runner.start("s", "alice", {{{GROUP!r}}})
next(stream)
print("started", flush=True)
time.sleep(60)
"""
    server = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)  # noqa: S603
    assert server.stdout is not None and server.stdout.readline().strip() == "started"
    server.kill()  # the server dies without cleaning up; the script (its own session) does not
    server.wait()

    runner = ScriptRunner(load_scripts(config), locks=ScriptLocks(tmp_path / "locks"))
    with pytest.raises(Busy) as refused:
        runner.start("s", "bob", {GROUP})
    assert refused.value.holder is not None and refused.value.holder.user == "alice"
    holder = runner.locks.holder("s")
    assert holder is not None and holder.user == "alice"

    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:  # the orphan finishes on its own
        time.sleep(0.1)
    assert marker.exists()
    time.sleep(0.2)
    runner.start("s", "bob", {GROUP}).close()  # and then the next user may run it


# --- symlinks and allow_dirs ---------------------------------------------------------------------------------


def test_a_symlink_inside_the_scripts_dir_is_fine(tmp_path: Path) -> None:
    config = write_config(tmp_path, toml_for(("a", "link.sh", GROUP)))
    (tmp_path / "scripts" / "link.sh").symlink_to(tmp_path / "scripts" / "a.sh")
    assert load_scripts(config)["a"].path == (tmp_path / "scripts" / "a.sh").resolve()


def test_a_symlink_out_of_the_scripts_dir_is_refused_and_says_what_to_do(tmp_path: Path) -> None:
    elsewhere = tmp_path / "checkout"
    elsewhere.mkdir()
    (elsewhere / "sync.sh").write_text("echo sync\n")
    config = write_config(tmp_path, toml_for(("a", "link.sh", GROUP)))
    (tmp_path / "scripts" / "link.sh").symlink_to(elsewhere / "sync.sh")
    with pytest.raises(ConfigError) as refused:
        load_scripts(config)
    message = str(refused.value)
    assert "outside the allowed directories" in message and "allow_dirs" in message
    assert str(elsewhere / "sync.sh") in message  # where it actually points, not just the link


def test_allow_dirs_lets_a_symlink_point_at_a_declared_directory(tmp_path: Path) -> None:
    elsewhere = tmp_path / "checkout"
    elsewhere.mkdir()
    (elsewhere / "sync.sh").write_text("echo sync\n")
    config = write_config(tmp_path, '[settings]\nallow_dirs = ["checkout"]\n\n' + toml_for(("a", "link.sh", GROUP)))
    (tmp_path / "scripts" / "link.sh").symlink_to(elsewhere / "sync.sh")
    script = load_scripts(config)["a"]
    assert script.path == (elsewhere / "sync.sh").resolve()


def test_allow_dirs_also_allows_a_plain_path_outside_the_scripts_dir(tmp_path: Path) -> None:
    elsewhere = tmp_path / "checkout"
    elsewhere.mkdir()
    (elsewhere / "sync.sh").write_text("echo sync\n")
    config = write_config(
        tmp_path, '[settings]\nallow_dirs = ["checkout"]\n\n' + toml_for(("a", "../checkout/sync.sh", GROUP))
    )
    assert load_scripts(config)["a"].path == (elsewhere / "sync.sh").resolve()


def test_allow_dirs_does_not_open_up_everything_else(tmp_path: Path) -> None:
    allowed = tmp_path / "checkout"
    allowed.mkdir()
    (allowed / "sync.sh").write_text("echo sync\n")
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "keys.sh").write_text("echo secrets\n")
    config = write_config(tmp_path, '[settings]\nallow_dirs = ["checkout"]\n\n' + toml_for(("a", "link.sh", GROUP)))
    (tmp_path / "scripts" / "link.sh").symlink_to(secret / "keys.sh")
    with pytest.raises(ConfigError, match="outside the allowed directories"):
        load_scripts(config)


def test_a_symlink_chain_is_judged_by_where_it_finally_points(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "real.sh").write_text("echo real\n")
    config = write_config(tmp_path, toml_for(("a", "link.sh", GROUP)))
    (tmp_path / "scripts" / "hop.sh").symlink_to(outside / "real.sh")  # link inside -> outside
    (tmp_path / "scripts" / "link.sh").symlink_to(tmp_path / "scripts" / "hop.sh")  # link inside -> link inside
    with pytest.raises(ConfigError, match="outside the allowed directories"):
        load_scripts(config)


def test_a_broken_symlink_says_so(tmp_path: Path) -> None:
    config = write_config(tmp_path, toml_for(("a", "link.sh", GROUP)))
    (tmp_path / "scripts" / "link.sh").symlink_to(tmp_path / "scripts" / "gone.sh")
    with pytest.raises(ConfigError, match="does not exist"):
        load_scripts(config)


@pytest.mark.parametrize(
    "bad", ['allow_dirs = "checkout"', "allow_dirs = [1]", 'allow_dirs = ["no-such-dir"]', 'allow_dirs = [""]']
)
def test_a_bad_allow_dirs_is_a_config_error(tmp_path: Path, bad: str) -> None:
    config = write_config(tmp_path, f"[settings]\n{bad}\n\n" + toml_for(("a", "a.sh", GROUP)))
    with pytest.raises(ConfigError):
        load_scripts(config)


def test_a_typo_in_settings_is_not_silently_ignored(tmp_path: Path) -> None:
    config = write_config(tmp_path, '[settings]\nscript_dir = "scripts"\n\n' + toml_for(("a", "a.sh", GROUP)))
    with pytest.raises(ConfigError, match="unknown keys in .settings."):
        load_scripts(config)


def test_a_symlinked_script_really_runs(tmp_path: Path, store: RunStore) -> None:
    elsewhere = tmp_path / "checkout"
    elsewhere.mkdir()
    (elsewhere / "sync.sh").write_text("echo from the checkout\n")
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "link.sh").symlink_to(elsewhere / "sync.sh")
    config = tmp_path / "scripts.toml"
    config.write_text('[settings]\nallow_dirs = ["checkout"]\n\n' + toml_for(("a", "link.sh", GROUP)))
    (tmp_path / "locks").mkdir(exist_ok=True)
    runner = ScriptRunner(load_scripts(config), store=store, locks=ScriptLocks(tmp_path / "locks"))
    stream = runner.start("a", "alice", {GROUP})
    assert b"from the checkout" in b"".join(stream)
    stream.close()


def test_the_last_reload_is_remembered_for_the_verbose_view(tmp_path: Path) -> None:
    runner, config = reloadable(tmp_path, toml_for(("a", "a.sh", GROUP), ("b", "b.sh", GROUP)))
    assert runner.last_reload is None
    config.write_text(toml_for(("a", "a.sh", "cn=other"), ("c", "c.sh", GROUP)))
    runner.reload()
    assert runner.last_reload == (["c"], ["b"], ["a"])
    runner.reload()
    assert runner.last_reload == ([], [], [])  # nothing changed this time


def test_an_impossible_file_name_is_a_config_error_not_a_crash(tmp_path: Path) -> None:
    """Anything the file system refuses (too long, a loop of links) must come back as a plain configuration error."""
    config = write_config(tmp_path, toml_for(("a", "x" * 9000 + ".sh", GROUP)))
    # python 3.12 raises for the long name ("cannot be used"); 3.14 reports it as missing: a config error either way
    with pytest.raises(ConfigError, match="cannot be used|does not exist"):
        load_scripts(config)


def test_a_loop_of_symlinks_is_a_config_error(tmp_path: Path) -> None:
    config = write_config(tmp_path, toml_for(("a", "loop.sh", GROUP)))
    (tmp_path / "scripts" / "loop.sh").symlink_to(tmp_path / "scripts" / "loop2.sh")
    (tmp_path / "scripts" / "loop2.sh").symlink_to(tmp_path / "scripts" / "loop.sh")
    with pytest.raises(ConfigError):
        load_scripts(config)


def test_an_impossible_allow_dirs_entry_is_a_config_error(tmp_path: Path) -> None:
    config = write_config(tmp_path, f'[settings]\nallow_dirs = ["{"y" * 9000}"]\n\n' + toml_for(("a", "a.sh", GROUP)))
    with pytest.raises(ConfigError, match="allow_dirs"):
        load_scripts(config)


# --- [defaults] and [profiles.<name>]: say the shared things once --------------------------------------------


OPS, ADMINS = "cn=ops,dc=test", "cn=admins,dc=test"


def test_defaults_supply_what_a_script_leaves_out(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        f'[defaults]\ngroups = ["{OPS}"]\ntimeout = 45\ndescription = "a g2g sync"\n\n'
        '[scripts.a]\nname = "A"\nfile = "a.sh"\n\n[scripts.b]\nname = "B"\nfile = "b.sh"\n',
        files=("a.sh", "b.sh"),
    )
    scripts = load_scripts(config)
    for script in scripts.values():
        assert script.groups == {OPS} and script.timeout == 45 and script.description == "a g2g sync"


def test_a_script_overrides_the_defaults(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        f'[defaults]\ngroups = ["{OPS}"]\ntimeout = 45\n\n'
        f'[scripts.a]\nfile = "a.sh"\n\n[scripts.b]\nfile = "b.sh"\ngroups = ["{ADMINS}"]\ntimeout = 600\n',
        files=("a.sh", "b.sh"),
    )
    scripts = load_scripts(config)
    assert scripts["a"].groups == {OPS} and scripts["a"].timeout == 45
    assert scripts["b"].groups == {ADMINS} and scripts["b"].timeout == 600  # not merged: replaced


def test_a_profile_supplies_settings_to_the_scripts_that_name_it(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        f'[profiles.nightly]\ngroups = ["{OPS}"]\ntimeout = 900\n\n'
        '[scripts.a]\nfile = "a.sh"\nprofile = "nightly"\n\n'
        f'[scripts.b]\nfile = "b.sh"\ngroups = ["{ADMINS}"]\n',
        files=("a.sh", "b.sh"),
    )
    scripts = load_scripts(config)
    assert scripts["a"].groups == {OPS} and scripts["a"].timeout == 900
    assert scripts["b"].groups == {ADMINS} and scripts["b"].timeout == 300  # untouched by the profile


def test_script_beats_profile_beats_defaults(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        f'[defaults]\ngroups = ["{OPS}"]\ntimeout = 45\ndescription = "from defaults"\n\n'
        f'[profiles.slow]\ntimeout = 900\ndescription = "from the profile"\n\n'
        '[scripts.a]\nfile = "a.sh"\nprofile = "slow"\n\n'
        '[scripts.b]\nfile = "b.sh"\nprofile = "slow"\ntimeout = 5\n',
        files=("a.sh", "b.sh"),
    )
    scripts = load_scripts(config)
    assert scripts["a"].timeout == 900 and scripts["a"].description == "from the profile"
    assert scripts["a"].groups == {OPS}  # the profile says nothing about groups, so [defaults] still applies
    assert scripts["b"].timeout == 5 and scripts["b"].description == "from the profile"


def test_several_profiles_can_coexist(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        f'[profiles.ops]\ngroups = ["{OPS}"]\n\n[profiles.admin]\ngroups = ["{ADMINS}"]\ntimeout = 10\n\n'
        '[scripts.a]\nfile = "a.sh"\nprofile = "ops"\n\n[scripts.b]\nfile = "b.sh"\nprofile = "admin"\n',
        files=("a.sh", "b.sh"),
    )
    scripts = load_scripts(config)
    assert scripts["a"].groups == {OPS} and scripts["b"].groups == {ADMINS} and scripts["b"].timeout == 10


def test_a_script_still_needs_groups_from_somewhere(tmp_path: Path) -> None:
    config = write_config(tmp_path, '[defaults]\ntimeout = 45\n\n[scripts.a]\nfile = "a.sh"\n')
    with pytest.raises(ConfigError, match="groups"):
        load_scripts(config)


def test_an_unknown_profile_is_refused_and_lists_the_known_ones(tmp_path: Path) -> None:
    config = write_config(
        tmp_path, f'[profiles.ops]\ngroups = ["{OPS}"]\n\n[scripts.a]\nfile = "a.sh"\nprofile = "opss"\n'
    )
    with pytest.raises(ConfigError) as refused:
        load_scripts(config)
    assert "does not exist" in str(refused.value) and "ops" in str(refused.value)


def test_a_profile_when_none_are_defined_says_so(tmp_path: Path) -> None:
    config = write_config(tmp_path, f'[scripts.a]\nfile = "a.sh"\ngroups = ["{OPS}"]\nprofile = "nightly"\n')
    with pytest.raises(ConfigError, match="none are defined"):
        load_scripts(config)


@pytest.mark.parametrize(
    "table",
    [
        '[defaults]\nfile = "a.sh"',  # a file for every script makes no sense
        '[defaults]\nname = "A"',  # nor one name for all of them
        '[defaults]\nprofile = "x"',
        "[defaults]\ntimeuot = 5",  # a typo must not be silently ignored
        '[profiles.x]\nfile = "a.sh"',
        "[profiles.x]\nnmae = 5",
        "defaults = 5",
        "profiles = 5",
    ],
)
def test_what_may_not_be_inherited_is_refused(tmp_path: Path, table: str) -> None:
    config = write_config(tmp_path, f"{table}\n\n" + toml_for(("a", "a.sh", OPS)))
    with pytest.raises(ConfigError):
        load_scripts(config)


def test_an_inherited_value_is_still_validated(tmp_path: Path) -> None:
    """A bad timeout in [defaults] must be caught exactly like a bad one on the script."""
    config = write_config(tmp_path, f'[defaults]\ngroups = ["{OPS}"]\ntimeout = 99999\n\n[scripts.a]\nfile = "a.sh"\n')
    with pytest.raises(ConfigError, match="timeout"):
        load_scripts(config)
    config.write_text(f'[defaults]\ngroups = "{OPS}"\n\n[scripts.a]\nfile = "a.sh"\n')
    with pytest.raises(ConfigError, match="groups"):
        load_scripts(config)


def test_a_profile_does_not_leak_between_scripts(tmp_path: Path) -> None:
    """Merging must not mutate the shared tables: the second script would otherwise inherit the first one's values."""
    config = write_config(
        tmp_path,
        f'[profiles.p]\ngroups = ["{OPS}"]\n\n'
        '[scripts.a]\nfile = "a.sh"\nprofile = "p"\ntimeout = 7\nname = "A"\n\n'
        '[scripts.b]\nfile = "b.sh"\nprofile = "p"\n',
        files=("a.sh", "b.sh"),
    )
    scripts = load_scripts(config)
    assert scripts["a"].timeout == 7 and scripts["b"].timeout == 300
    assert scripts["a"].name == "A" and scripts["b"].name == "b"


def test_the_placeholder_warning_also_sees_an_inherited_group(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="aGit2Git.runner")
    config = write_config(
        tmp_path,
        '[defaults]\ngroups = ["cn=script-runners,ou=groups,dc=example,dc=com"]\n\n[scripts.a]\nfile = "a.sh"\n',
    )
    load_scripts(config)
    assert "placeholder" in caplog.text


def test_a_misspelled_profile_key_is_refused(tmp_path: Path) -> None:
    config = write_config(tmp_path, f'[profiles.p]\ngroups = ["{OPS}"]\n\n[scripts.a]\nfile = "a.sh"\nprofiel = "p"\n')
    with pytest.raises(ConfigError, match="unknown keys"):
        load_scripts(config)


def test_the_shipped_example_allowlist_is_valid(tmp_path: Path) -> None:
    """scripts.example.toml is what people copy: it must load, and show what defaults and profiles do."""
    shipped = Path(__file__).resolve().parents[2] / "runner" / "scripts.example.toml"
    config = tmp_path / "scripts.toml"
    config.write_text(shipped.read_text())
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "hello.sh").write_text("echo hi\n")
    scripts = load_scripts(config, warn=False)
    assert {"hello", "nightly-sync", "admin-only"} <= set(scripts)
    assert scripts["hello"].timeout == 60  # its own
    assert scripts["nightly-sync"].timeout == 1800  # from the profile
    assert scripts["nightly-sync"].groups == scripts["hello"].groups  # from [defaults]
    assert scripts["admin-only"].groups != scripts["hello"].groups  # its own, replacing the default


# --- [groups]: short names instead of long DNs ----------------------------------------------------------------


OPS_DN = "cn=ops,ou=groups,dc=corp,dc=local"
ADMINS_DN = "cn=g2g-admins,ou=groups,dc=corp,dc=local"
NAMES = f'[groups]\nops = "{OPS_DN}"\nadmins = "{ADMINS_DN}"\n\n'


def test_a_script_can_use_a_short_group_name(tmp_path: Path) -> None:
    config = write_config(tmp_path, NAMES + '[scripts.a]\nfile = "a.sh"\ngroups = ["ops", "admins"]\n')
    assert load_scripts(config)["a"].groups == {OPS_DN, ADMINS_DN}


def test_a_dn_written_out_in_full_still_works(tmp_path: Path) -> None:
    config = write_config(tmp_path, NAMES + f'[scripts.a]\nfile = "a.sh"\ngroups = ["{ADMINS_DN}"]\n')
    assert load_scripts(config)["a"].groups == {ADMINS_DN}


def test_short_names_work_in_defaults_and_profiles(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        NAMES + '[defaults]\ngroups = ["ops"]\n\n[profiles.p]\ngroups = ["admins"]\n\n'
        '[scripts.a]\nfile = "a.sh"\n\n[scripts.b]\nfile = "b.sh"\nprofile = "p"\n',
        files=("a.sh", "b.sh"),
    )
    scripts = load_scripts(config)
    assert scripts["a"].groups == {OPS_DN} and scripts["b"].groups == {ADMINS_DN}


def test_an_unknown_short_name_is_refused_and_lists_the_known_ones(tmp_path: Path) -> None:
    config = write_config(tmp_path, NAMES + '[scripts.a]\nfile = "a.sh"\ngroups = ["opss"]\n')
    with pytest.raises(ConfigError) as refused:
        load_scripts(config)
    assert "is not in [groups]" in str(refused.value) and "ops, admins" in str(refused.value).replace(
        "admins, ops", "ops, admins"
    )


@pytest.mark.parametrize(
    "bad", ["[groups]\nops = 5", '[groups]\nops = "not-a-dn"', '[groups]\n"Bad Name" = "cn=x,dc=y"', "groups = 5"]
)
def test_a_bad_groups_table_is_refused(tmp_path: Path, bad: str) -> None:
    config = write_config(tmp_path, f"{bad}\n\n" + toml_for(("a", "a.sh", OPS_DN)))
    with pytest.raises(ConfigError):
        load_scripts(config)


# --- include: the scripts can live in their own files ---------------------------------------------------------


def split_config(tmp_path: Path, main_extra: str = "", **included: str) -> Path:
    """A main file with [settings]/[groups]/[defaults] and one included file per keyword argument."""
    (tmp_path / "scripts").mkdir(exist_ok=True)
    for name in ("a.sh", "b.sh", "c.sh"):
        (tmp_path / "scripts" / name).write_text("echo hi\n")
    enabled = tmp_path / "scripts-enabled"
    enabled.mkdir(exist_ok=True)
    for stem, content in included.items():
        (enabled / f"{stem}.toml").write_text(content)
    config = tmp_path / "scripts.toml"
    config.write_text('[settings]\ninclude = ["scripts-enabled/*.toml"]\n\n' + NAMES + main_extra)
    return config


def test_scripts_are_read_from_the_included_files(tmp_path: Path) -> None:
    config = split_config(
        tmp_path,
        ops='[scripts.a]\nname = "A"\nfile = "a.sh"\ngroups = ["ops"]\n',
        admins='[scripts.b]\nname = "B"\nfile = "b.sh"\ngroups = ["admins"]\n',
    )
    scripts = load_scripts(config)
    assert set(scripts) == {"a", "b"}
    assert scripts["a"].groups == {OPS_DN} and scripts["b"].groups == {ADMINS_DN}


def test_a_file_named_after_a_group_can_set_it_once_for_all_its_scripts(tmp_path: Path) -> None:
    """The point of naming a file after a group: say the group once, in that file's own [defaults]."""
    config = split_config(
        tmp_path,
        ops='[defaults]\ngroups = ["ops"]\n\n[scripts.a]\nfile = "a.sh"\n\n[scripts.b]\nfile = "b.sh"\n',
    )
    scripts = load_scripts(config)
    assert scripts["a"].groups == {OPS_DN} and scripts["b"].groups == {OPS_DN}


def test_global_defaults_reach_the_included_files(tmp_path: Path) -> None:
    config = split_config(
        tmp_path,
        main_extra='[defaults]\ngroups = ["ops"]\ntimeout = 45\n',
        ops='[scripts.a]\nfile = "a.sh"\n\n[scripts.b]\nfile = "b.sh"\ntimeout = 5\n',
    )
    scripts = load_scripts(config)
    assert scripts["a"].timeout == 45 and scripts["b"].timeout == 5
    assert scripts["a"].groups == {OPS_DN}


def test_a_files_own_defaults_win_over_the_global_ones(tmp_path: Path) -> None:
    config = split_config(
        tmp_path,
        main_extra='[defaults]\ngroups = ["ops"]\ntimeout = 45\n',
        admins='[defaults]\ngroups = ["admins"]\n\n[scripts.a]\nfile = "a.sh"\n',
    )
    script = load_scripts(config)["a"]
    assert script.groups == {ADMINS_DN} and script.timeout == 45  # the timeout still comes from the global defaults


def test_profiles_from_the_main_file_can_be_used_in_an_included_one(tmp_path: Path) -> None:
    config = split_config(
        tmp_path,
        main_extra="[profiles.slow]\ntimeout = 1800\n",
        ops='[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\nprofile = "slow"\n',
    )
    assert load_scripts(config)["a"].timeout == 1800


def test_scripts_may_still_live_in_the_main_file(tmp_path: Path) -> None:
    config = split_config(
        tmp_path,
        main_extra='[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n',
        ops='[scripts.b]\nfile = "b.sh"\ngroups = ["ops"]\n',
    )
    assert set(load_scripts(config)) == {"a", "b"}


def test_the_same_script_id_in_two_files_is_refused_naming_both(tmp_path: Path) -> None:
    config = split_config(
        tmp_path,
        ops='[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n',
        admins='[scripts.a]\nfile = "b.sh"\ngroups = ["admins"]\n',
    )
    with pytest.raises(ConfigError) as refused:
        load_scripts(config)
    assert "defined twice" in str(refused.value)
    assert "ops.toml" in str(refused.value) and "admins.toml" in str(refused.value)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('[settings]\nscripts_dir = "/etc"\n\n[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n', "settings"),
        ('[groups]\nops = "cn=anything,dc=x"\n\n[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n', "groups"),
        ('[profiles.p]\ntimeout = 5\n\n[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n', "profiles"),
    ],
)
def test_an_included_file_cannot_change_the_trusted_parts(tmp_path: Path, content: str, expected: str) -> None:
    """This is what makes included files safe to hand to an administrator (or a web editor)."""
    config = split_config(tmp_path, ops=content)
    with pytest.raises(ConfigError) as refused:
        load_scripts(config)
    assert expected in str(refused.value) and "may only hold" in str(refused.value)


def test_an_error_in_an_included_file_names_that_file(tmp_path: Path) -> None:
    config = split_config(tmp_path, ops='[scripts.a]\nfile = "nowhere.sh"\ngroups = ["ops"]\n')
    with pytest.raises(ConfigError) as refused:
        load_scripts(config)
    assert "ops.toml" in str(refused.value) and "does not exist" in str(refused.value)


def test_a_broken_included_file_is_reported_with_its_name(tmp_path: Path) -> None:
    config = split_config(tmp_path, ops="this is [[[ not toml")
    with pytest.raises(ConfigError, match="ops.toml"):
        load_scripts(config)


def test_an_empty_include_directory_is_an_error_not_an_empty_allowlist(tmp_path: Path) -> None:
    config = split_config(tmp_path)
    with pytest.raises(ConfigError, match="at least one"):
        load_scripts(config)


def test_a_named_include_that_does_not_exist_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a.sh").write_text("echo hi\n")
    config = tmp_path / "scripts.toml"
    config.write_text('[settings]\ninclude = ["missing.toml"]\n\n' + NAMES + toml_for(("a", "a.sh", "ops")))
    with pytest.raises(ConfigError, match="does not exist"):
        load_scripts(config)


def test_a_glob_that_matches_nothing_is_allowed_if_other_scripts_exist(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a.sh").write_text("echo hi\n")
    config = tmp_path / "scripts.toml"
    config.write_text('[settings]\ninclude = ["scripts-enabled/*.toml"]\n\n' + NAMES + toml_for(("a", "a.sh", "ops")))
    assert set(load_scripts(config)) == {"a"}  # nobody has added a file yet


@pytest.mark.parametrize("bad", ['include = "one.toml"', "include = [5]", 'include = ["/etc/passwd"]'])
def test_a_bad_include_setting_is_refused(tmp_path: Path, bad: str) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a.sh").write_text("echo hi\n")
    config = tmp_path / "scripts.toml"
    config.write_text(f"[settings]\n{bad}\n\n" + NAMES + toml_for(("a", "a.sh", "ops")))
    with pytest.raises(ConfigError):
        load_scripts(config)


def test_adding_and_removing_an_included_file_is_picked_up_by_a_reload(tmp_path: Path) -> None:
    config = split_config(tmp_path, ops='[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n')
    runner = ScriptRunner(load_scripts(config), config_file=config)
    assert set(runner.scripts) == {"a"}

    (tmp_path / "scripts-enabled" / "admins.toml").write_text('[scripts.b]\nfile = "b.sh"\ngroups = ["admins"]\n')
    assert runner.reload() is True and set(runner.scripts) == {"a", "b"}

    (tmp_path / "scripts-enabled" / "admins.toml").unlink()
    assert runner.reload() is True and set(runner.scripts) == {"a"}


def test_a_broken_included_file_leaves_the_previous_list_in_force(tmp_path: Path) -> None:
    config = split_config(tmp_path, ops='[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n')
    runner = ScriptRunner(load_scripts(config), config_file=config)
    (tmp_path / "scripts-enabled" / "ops.toml").write_text("broken [[[")
    with pytest.raises(ConfigError):
        runner.reload()
    assert set(runner.scripts) == {"a"}


# --- local groups: a django group, for when a new LDAP group would take too long ------------------------------


def test_a_local_group_lets_its_members_run_a_script(tmp_path: Path) -> None:
    """The caller passes the user's django groups as "local:<name>" next to their LDAP group DNs."""
    config = write_config(tmp_path, NAMES + '[scripts.a]\nfile = "a.sh"\ngroups = ["local:hotfix"]\n')
    script = load_scripts(config)["a"]
    assert script.groups == {"local:hotfix"}
    assert script.allowed_for({"local:hotfix"})
    assert not script.allowed_for({"local:other", OPS_DN})


def test_a_local_group_name_is_not_an_ldap_name(tmp_path: Path) -> None:
    """A django group called like an LDAP group DN does not give LDAP rights, and the reverse."""
    config = write_config(tmp_path, NAMES + '[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n')
    assert not load_scripts(config)["a"].allowed_for({f"local:{OPS_DN}", "local:ops"})


def test_a_script_can_have_both_an_ldap_group_and_a_local_one(tmp_path: Path) -> None:
    config = write_config(tmp_path, NAMES + '[scripts.a]\nfile = "a.sh"\ngroups = ["ops", "local:hotfix"]\n')
    script = load_scripts(config)["a"]
    assert script.groups == {OPS_DN, "local:hotfix"}
    assert script.allowed_for({OPS_DN}) and script.allowed_for({"local:hotfix"})
    assert not script.allowed_for(set())


def test_access_through_a_local_group_is_distinguishable_from_ldap(tmp_path: Path) -> None:
    """The runner logs which of the two let somebody in; temporary access should be visible in the audit trail."""
    config = write_config(tmp_path, NAMES + '[scripts.a]\nfile = "a.sh"\ngroups = ["ops", "local:hotfix"]\n')
    script = load_scripts(config)["a"]
    assert script.allowed_by_local_group({"local:hotfix"})
    assert not script.allowed_by_local_group({OPS_DN, "local:hotfix"})  # in the LDAP group as well: nothing special
    assert not script.allowed_by_local_group({OPS_DN})
    assert not script.allowed_by_local_group(set())


def test_a_local_group_may_not_be_used_from_an_included_file(tmp_path: Path) -> None:
    """Included files are the ones administrators edit: they must not be able to hand out access that way."""
    config = split_config(tmp_path, ops='[scripts.a]\nfile = "a.sh"\ngroups = ["local:hotfix"]\n')
    with pytest.raises(ConfigError) as refused:
        load_scripts(config)
    assert "only be used in the main allowlist" in str(refused.value) and "ops.toml" in str(refused.value)


@pytest.mark.parametrize("group", ["local:", "local:   ", "local:a\\u0001b", "local:" + "x" * 151])
def test_an_unusable_local_group_name_is_refused(tmp_path: Path, group: str) -> None:
    config = write_config(tmp_path, NAMES + f'[scripts.a]\nfile = "a.sh"\ngroups = ["{group}"]\n')
    with pytest.raises(ConfigError, match="not a usable django group name"):
        load_scripts(config)


def test_a_plain_name_that_is_not_in_groups_is_refused_and_mentions_local(tmp_path: Path) -> None:
    """ "hotfix" is not an LDAP name: the prefix is what says where access comes from."""
    config = write_config(tmp_path, NAMES + '[scripts.a]\nfile = "a.sh"\ngroups = ["hotfix"]\n')
    with pytest.raises(ConfigError, match="local:<django group>"):
        load_scripts(config)


def test_manual_groups_from_the_flask_tool_are_not_supported(tmp_path: Path) -> None:
    config = write_config(tmp_path, '[settings]\nmanual_groups = "manual-groups.toml"\n\n' + toml_for(("a", "a.sh", OPS_DN)))
    with pytest.raises(ConfigError, match="manual_groups"):
        load_scripts(config)


def test_the_runner_shows_and_runs_a_script_for_a_local_group_member(tmp_path: Path) -> None:
    config = write_config(tmp_path, NAMES + '[scripts.a]\nname = "A"\nfile = "a.sh"\ngroups = ["local:hotfix"]\n')
    (tmp_path / "locks").mkdir(exist_ok=True)
    runner = ScriptRunner(load_scripts(config), config_file=config, locks=ScriptLocks(tmp_path / "locks"))
    assert [s.id for s in runner.visible_to({"local:hotfix"})] == ["a"]
    assert runner.visible_to({OPS_DN}) == []
    with pytest.raises(NotAllowed):
        runner.start("a", "carol", {OPS_DN})
    stream = runner.start("a", "mboot", {"local:hotfix"})
    assert b"hi" in b"".join(stream)
    stream.close()


# --- a key under the wrong section header is the easiest mistake to make in TOML ------------------------------


@pytest.mark.parametrize(
    ("body", "key", "belongs"),
    [
        # exactly what happens when allow_dirs is written below [groups] instead of under [settings]
        (
            f'[groups]\nops = "{OPS_DN}"\nallow_dirs = ["/opt/bin"]\n\n[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n',
            "allow_dirs",
            "[settings]",
        ),
        (
            f'[groups]\nops = "{OPS_DN}"\ninclude = ["x/*.toml"]\n\n[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n',
            "include",
            "[settings]",
        ),
        (
            f'[settings]\ntimeout = 60\n\n[groups]\nops = "{OPS_DN}"\n\n[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n',
            "timeout",
            "[defaults]",
        ),
        (
            f'[defaults]\ngroups = ["{OPS_DN}"]\nscripts_dir = "scripts"\n\n[scripts.a]\nfile = "a.sh"\n',
            "scripts_dir",
            "[settings]",
        ),
        (f'[scripts.a]\nfile = "a.sh"\ngroups = ["{OPS_DN}"]\nallow_dirs = ["/opt/bin"]\n', "allow_dirs", "[settings]"),
    ],
)
def test_a_key_under_the_wrong_header_says_where_it_belongs(tmp_path: Path, body: str, key: str, belongs: str) -> None:
    config = write_config(tmp_path, body)
    with pytest.raises(ConfigError) as refused:
        load_scripts(config)
    message = str(refused.value)
    assert key in message and belongs in message
    assert "every key goes under the section header above it" in message


def test_a_genuinely_unknown_key_gets_no_misleading_hint(tmp_path: Path) -> None:
    config = write_config(tmp_path, "[settings]\nnonsense = 1\n\n" + toml_for(("a", "a.sh", OPS_DN)))
    with pytest.raises(ConfigError) as refused:
        load_scripts(config)
    assert "nonsense" in str(refused.value) and "belongs in" not in str(refused.value)


def test_the_shipped_example_is_valid_and_indented(tmp_path: Path) -> None:
    """The example is what people copy; it must load, and show the structure it is teaching."""
    example = Path(__file__).resolve().parents[2] / "runner" / "scripts.example.toml"
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "hello.sh").write_text("echo hi\n")
    config = tmp_path / "scripts.toml"
    config.write_text(example.read_text())
    scripts = load_scripts(config, warn=False)
    assert {"hello", "nightly-sync", "admin-only"} <= set(scripts)
    assert scripts["hello"].timeout == 60 and scripts["nightly-sync"].timeout == 1800
    text = example.read_text()
    assert "\n    " in text, "the example should indent the keys under their section headers"
    assert "WHAT GOES WHERE" in text


# --- DNs are compared as normalized strings ----------------------------------------------------------------------


def test_group_dns_are_normalized(tmp_path: Path) -> None:
    """AD returns CN=...,OU=...; the allowlist may say cn=..., ou=...: the same group."""
    config = write_config(
        tmp_path,
        '[groups]\nops = "CN=Ops, OU=Groups,DC=Corp"\n\n'
        '[scripts.a]\nfile = "a.sh"\ngroups = ["ops", "CN=Admins , ou=groups,dc=corp", "local:Hot Fix"]\n',
    )
    script = load_scripts(config)["a"]
    assert script.groups == {"cn=ops,ou=groups,dc=corp", "cn=admins,ou=groups,dc=corp", "local:Hot Fix"}
    assert script.allowed_for({normalize_dn("CN=Ops,OU=Groups,DC=Corp")})
    assert not script.allowed_for({"local:hot fix"})  # django group names are case-sensitive


def test_normalize_dn() -> None:
    assert normalize_dn("CN=Ops , OU=Groups,DC=Corp") == "cn=ops,ou=groups,dc=corp"
    assert normalize_dn("cn=ops,ou=groups,dc=corp") == "cn=ops,ou=groups,dc=corp"
