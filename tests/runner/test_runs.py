"""RunStore: the output of the last run of every script, on disk."""

import errno
import json
import logging
import os
import stat
import time
import types
from pathlib import Path

import pytest
from aGit2Git.runner.runs import RunInfo, RunStore


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


def record(
    store: RunStore,
    script_id: str = "hello",
    user: str = "bob",
    output: bytes = b"hi\n",
    status: str = "exit code 0",
    code: int = 0,
) -> RunInfo:
    recorder = store.begin(script_id, user)
    recorder.write(output)
    recorder.finish(status, code, b"\n[" + status.encode() + b"]\n")
    info = store.last(script_id)
    assert info is not None
    return info


# --- the basic round trip -------------------------------------------------------------------------------------------


def test_no_run_yet(store: RunStore) -> None:
    assert store.last("hello") is None


def test_a_finished_run_is_kept_with_who_when_and_how_it_ended(store: RunStore) -> None:
    before = time.time()
    info = record(store, user="bob", output=b"line one\nline two\n", status="exit code 3", code=3)
    assert (info.script_id, info.user, info.status, info.exit_code) == ("hello", "bob", "exit code 3", 3)
    assert before <= info.started <= info.finished <= time.time()  # type: ignore[operator]
    assert not info.running and not info.ok
    assert store.read(info, 0, 10_000) == b"line one\nline two\n\n[exit code 3]\n"
    assert info.size == len(b"line one\nline two\n\n[exit code 3]\n")


def test_exit_code_zero_is_ok(store: RunStore) -> None:
    assert record(store).ok


def test_a_run_in_progress_shows_its_output_so_far(store: RunStore) -> None:
    recorder = store.begin("hello", "bob")
    recorder.write(b"first\n")
    info = store.last("hello")
    assert info is not None and info.running and info.status is None and info.finished is None
    assert info.size == len(b"first\n")  # taken from the file: it is still growing
    assert store.read(info, 0, 100) == b"first\n"
    recorder.write(b"second\n")
    assert store.read(info, len(b"first\n"), 100) == b"second\n"  # a follower asks from where it stopped
    recorder.finish("exit code 0", 0)
    done = store.last("hello")
    assert done is not None and not done.running and done.size == len(b"first\nsecond\n")


def test_the_next_run_replaces_the_last_one(store: RunStore) -> None:
    first = record(store, output=b"old output\n")
    old_log = store.log_path(first)
    second = record(store, user="alice", output=b"new output\n")
    assert second.run_id != first.run_id and second.user == "alice"
    assert not old_log.exists()  # only the last run is kept
    assert store.read(second, 0, 100).startswith(b"new output")
    assert store.lookup("hello", first.run_id) is None  # and the old run id is gone


def test_scripts_do_not_share_runs(store: RunStore) -> None:
    a = record(store, "alpha", output=b"a\n")
    b = record(store, "beta", output=b"b\n")
    assert store.read(a, 0, 10).startswith(b"a") and store.read(b, 0, 10).startswith(b"b")
    assert store.lookup("alpha", b.run_id) is None


def test_finish_is_idempotent_and_later_writes_are_ignored(store: RunStore) -> None:
    recorder = store.begin("hello", "bob")
    recorder.write(b"x")
    recorder.finish("exit code 0", 0)
    recorder.finish("something else", 9)  # e.g. cancelled-before-start racing with a real finish
    recorder.write(b"too late")
    info = store.last("hello")
    assert info is not None and info.status == "exit code 0" and store.read(info, 0, 100) == b"x"


# --- reading --------------------------------------------------------------------------------------------------------


def test_read_honours_offset_and_limit(store: RunStore) -> None:
    info = record(store, output=b"0123456789")
    assert store.read(info, 2, 3) == b"234"
    assert store.read(info, -5, 3) == b"012"  # a negative offset is just the start
    assert store.read(info, 10_000, 3) == b""  # past the end: nothing
    assert store.read(info, 99999999999999999999, 3) == b""  # absurdly far: still just nothing, no exception


def test_tail_returns_everything_when_it_fits(store: RunStore) -> None:
    info = record(store, output=b"short\n")
    data, start, end = store.tail(info, 1000)
    assert data == b"short\n\n[exit code 0]\n" and start == 0 and end == info.size


def test_tail_returns_only_the_end_of_big_output(store: RunStore) -> None:
    info = record(store, output=b"x" * 5000 + b"THE END")
    data, start, end = store.tail(info, 100)
    assert len(data) == 100 and data.endswith(b"[exit code 0]\n") and start == info.size - 100 and end == info.size


def test_tail_does_not_start_in_the_middle_of_a_character(store: RunStore) -> None:
    euro = "€".encode()  # three bytes
    info = record(store, output=euro * 50)
    for cut in range(1, 8):
        data, _, _ = store.tail(info, len(euro) * 10 + cut)
        data.decode("utf-8")  # must be valid: no stray continuation bytes at the front


def test_tail_of_a_missing_log_is_empty(store: RunStore) -> None:
    info = record(store)
    store.log_path(info).unlink()
    assert store.tail(info, 100) == (b"", 0, 0)
    assert store.read(info, 0, 100) == b""


# --- ids from outside never reach the file system ---------------------------------------------------------------


@pytest.mark.parametrize("bad", ["../x", "a/b", "", "A", "has space", "-lead", "a" * 65, "x\0y", ".."])
def test_bad_script_ids_are_refused_before_touching_the_disk(store: RunStore, bad: str) -> None:
    with pytest.raises(ValueError):
        store.begin(bad, "bob")
    with pytest.raises(ValueError):
        store.last(bad)
    assert [p.name for p in store.directory.iterdir()] == []


@pytest.mark.parametrize(
    "bad",
    ["", "../../etc/passwd", "ZZZZZZZZZZZZZZZZ", "abc", "0123456789abcdef0", "0123456789abcdeg", "0123456789ABCDEF"],
)
def test_bad_run_ids_never_match(store: RunStore, bad: str) -> None:
    record(store)
    assert store.lookup("hello", bad) is None


@pytest.mark.parametrize("bad", ["../../etc/passwd", "../x", "", "xyz", "0123456789abcdef/../.."])
def test_a_log_path_is_never_built_from_a_malformed_run_id(store: RunStore, bad: str) -> None:
    """The last line of defence: even if a bad id got past lookup(), it cannot become a path."""
    info = RunInfo("hello", bad, "bob", time.time())
    with pytest.raises(ValueError):
        store.log_path(info)
    with pytest.raises(ValueError):
        store.read(info, 0, 10)


def test_the_right_run_id_matches(store: RunStore) -> None:
    info = record(store)
    assert store.lookup("hello", info.run_id) == info


# --- privacy, atomicity and recovery ----------------------------------------------------------------------------


def test_files_and_directory_are_private(store: RunStore) -> None:
    info = record(store, output=b"maybe sensitive\n")
    assert stat.S_IMODE(store.directory.stat().st_mode) & 0o077 == 0
    for path in (store.log_path(info), store.directory / "hello.json"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_no_temporary_files_are_left_behind(store: RunStore) -> None:
    for _ in range(5):
        record(store)
    assert sorted(p.name for p in store.directory.iterdir() if p.suffix == ".tmp") == []
    assert len(list(store.directory.iterdir())) == 2  # one record + one log, nothing else


def test_a_corrupt_record_is_survivable(store: RunStore, caplog: pytest.LogCaptureFixture) -> None:
    record(store)
    (store.directory / "hello.json").write_text("{ not json")
    assert store.last("hello") is None
    assert "unreadable run record" in caplog.text
    assert record(store).ok  # and the next run simply starts over


def test_a_record_with_unexpected_fields_is_survivable(store: RunStore) -> None:
    record(store)
    (store.directory / "hello.json").write_text(json.dumps({"surprise": 1}))
    assert store.last("hello") is None


def test_runs_cut_off_by_a_restart_are_marked_interrupted(tmp_path: Path) -> None:
    first = RunStore(tmp_path / "runs")
    first.begin("hello", "bob").write(b"half of the output\n")  # the server dies here: never finished
    second = RunStore(tmp_path / "runs")  # the server starts again
    info = second.last("hello")
    assert info is not None and not info.running
    assert info.status == "interrupted (the server was restarted)"
    assert second.read(info, 0, 100) == b"half of the output\n"  # what there is stays viewable


def test_finished_runs_are_left_alone_by_a_restart(tmp_path: Path) -> None:
    first = RunStore(tmp_path / "runs")
    done = record(first)
    assert RunStore(tmp_path / "runs").last("hello") == done


# --- storage trouble must never break a run --------------------------------------------------------------------


def test_a_full_disk_does_not_raise_and_is_reported(
    store: RunStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    recorder = store.begin("hello", "bob")
    recorder.write(b"saved\n")

    def full(*args: object, **kwargs: object) -> int:
        raise OSError(errno.ENOSPC, "No space left on device")

    # Only the store's view of `os` is replaced: the rest of the process (pytest, logging) keeps a working os.write.
    fake_os = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os)})
    fake_os.write = full
    monkeypatch.setattr("aGit2Git.runner.runs.os", fake_os)
    recorder.write(b"lost\n")  # must not raise: the script is still running
    recorder.write(b"lost too\n")
    monkeypatch.undo()
    recorder.finish("exit code 0", 0, b"\n[exit code 0]\n")
    info = store.last("hello")
    assert info is not None and info.status is not None and "could not be saved completely" in info.status
    assert caplog.text.count("cannot record the output") == 1  # logged once, not per chunk


def test_a_broken_record_directory_does_not_raise_when_finishing(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    recorder = store.begin("hello", "bob")
    for p in list((tmp_path / "runs").iterdir()):
        p.unlink()
    (tmp_path / "runs").rmdir()
    recorder.write(b"x")
    recorder.finish("exit code 0", 0)  # nothing to write to any more: logged, not raised


def test_begin_reports_an_unusable_directory_so_the_caller_can_carry_on(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    (tmp_path / "runs").chmod(0o500)
    try:
        if os.access(tmp_path / "runs", os.W_OK):
            pytest.skip("running as a user that ignores directory permissions")
        with pytest.raises(OSError):
            store.begin("hello", "bob")
    finally:
        (tmp_path / "runs").chmod(0o700)


def test_a_missing_directory_is_created(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "runs"
    RunStore(deep)
    assert deep.is_dir()


def test_a_directory_that_cannot_be_created_is_an_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(OSError):
        RunStore(blocker / "runs")


def test_log_messages_do_not_leak_output(store: RunStore, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    record(store, output=b"password=hunter2\n")
    assert "hunter2" not in caplog.text
