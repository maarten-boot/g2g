"""One run of a script at a time: in memory, on disk, between worker processes, and across crashes."""

import errno
import fcntl
import json
import os
import stat
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest
from aGit2Git.runner.locks import Busy, LockUnavailable, ScriptLocks

ROOT = Path(__file__).resolve().parents[2] / "pSwai"  # the django project, which a child process puts on its path


@pytest.fixture(params=["memory", "files"])
def mode(request: pytest.FixtureRequest) -> str:
    """Everything that does not depend on files must hold in both modes."""
    return str(request.param)


@pytest.fixture
def locks(mode: str, tmp_path: Path) -> ScriptLocks:
    return ScriptLocks(tmp_path / "locks" if mode == "files" else None)


@pytest.fixture
def lock_dir(tmp_path: Path) -> Path:
    path = tmp_path / "locks"
    path.mkdir()
    return path


# --- the rule: one at a time, the next one after that ------------------------------------------------------------


def test_the_second_user_is_refused_and_the_next_one_after_the_first_finished_is_not(
    locks: ScriptLocks, mode: str, tmp_path: Path
) -> None:
    if mode == "files":
        (tmp_path / "locks").mkdir()
    first = locks.acquire("sync", "alice")
    with pytest.raises(Busy):
        locks.acquire("sync", "bob")  # cannot run at the same time ...
    with pytest.raises(Busy):
        locks.acquire("sync", "alice")  # ... not even the same user twice
    first.release()
    second = locks.acquire("sync", "bob")  # ... but may rerun when it is over
    with pytest.raises(Busy):
        locks.acquire("sync", "carol")
    second.release()
    locks.acquire("sync", "carol").release()


def test_the_refused_user_is_told_who_holds_it_and_since_when(locks: ScriptLocks, mode: str, tmp_path: Path) -> None:
    if mode == "files":
        (tmp_path / "locks").mkdir()
    before = time.time()
    held = locks.acquire("sync", "alice")
    with pytest.raises(Busy) as refused:
        locks.acquire("sync", "bob")
    holder = refused.value.holder
    assert holder is not None and holder.user == "alice" and holder.script_id == "sync" and holder.pid == os.getpid()
    assert before <= holder.since <= time.time()
    assert refused.value.script_id == "sync"
    held.release()


def test_different_scripts_do_not_block_each_other(locks: ScriptLocks, mode: str, tmp_path: Path) -> None:
    if mode == "files":
        (tmp_path / "locks").mkdir()
    a = locks.acquire("alpha", "alice")
    b = locks.acquire("beta", "bob")  # a different script: fine
    a.release()
    b.release()


def test_release_is_idempotent_and_a_stale_handle_cannot_free_somebody_elses_lock(
    locks: ScriptLocks, mode: str, tmp_path: Path
) -> None:
    if mode == "files":
        (tmp_path / "locks").mkdir()
    old = locks.acquire("sync", "alice")
    old.release()
    new = locks.acquire("sync", "bob")
    old.release()  # e.g. a close() that is called twice
    with pytest.raises(Busy):
        locks.acquire("sync", "carol")  # bob still holds it
    new.release()


def test_many_threads_racing_for_one_script_exactly_one_wins(locks: ScriptLocks, mode: str, tmp_path: Path) -> None:
    if mode == "files":
        (tmp_path / "locks").mkdir()
    barrier = threading.Barrier(20)
    winners: list[str] = []
    refused: list[str] = []
    kept: list[object] = []

    def racer(name: str) -> None:
        barrier.wait()
        try:
            kept.append(locks.acquire("sync", name))
            winners.append(name)
        except Busy:
            refused.append(name)

    threads = [threading.Thread(target=racer, args=(f"user{i}",)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(winners) == 1 and len(refused) == 19


def test_script_ids_are_checked_before_anything_is_touched(lock_dir: Path) -> None:
    locks = ScriptLocks(lock_dir)
    for bad in ("../x", "a/b", "", "A", "has space", "-lead", "a" * 65, "x\0y", ".."):
        with pytest.raises(ValueError):
            locks.acquire(bad, "alice")
        with pytest.raises(ValueError):
            locks.holder(bad)
    assert list(lock_dir.iterdir()) == []


# --- the lock file -----------------------------------------------------------------------------------------------


def test_the_lock_file_is_private_and_stays_after_release(lock_dir: Path) -> None:
    locks = ScriptLocks(lock_dir)
    held = locks.acquire("sync", "alice")
    path = lock_dir / "sync.lock"
    assert path.exists() and stat.S_IMODE(path.stat().st_mode) == 0o600
    held.release()
    assert path.exists()  # never deleted: deleting a file others may be about to lock breaks file locking


def test_the_lock_file_says_who_holds_it_while_it_is_held_and_nothing_afterwards(lock_dir: Path) -> None:
    locks = ScriptLocks(lock_dir)
    held = locks.acquire("sync", "alice")
    info = json.loads((lock_dir / "sync.lock").read_text())
    assert info["user"] == "alice" and info["script_id"] == "sync" and info["pid"] == os.getpid()
    held.release()
    assert (lock_dir / "sync.lock").read_text() == ""  # a leftover name would only mislead the next reader


def test_nothing_is_created_for_a_script_that_was_never_asked_about(lock_dir: Path) -> None:
    locks = ScriptLocks(lock_dir)
    assert locks.holder("sync") is None  # looking is not locking, and it creates nothing
    assert list(lock_dir.iterdir()) == []


def test_the_lock_file_is_not_handed_to_the_scripts_that_run(lock_dir: Path) -> None:
    """If a script inherited the descriptor it would keep the script locked for as long as any child of it lives."""
    locks = ScriptLocks(lock_dir)
    held = locks.acquire("sync", "alice")
    listing = subprocess.run(  # noqa: S603
        ["/bin/ls", "-l", "/proc/self/fd"], capture_output=True, text=True, check=True
    ).stdout
    held.release()
    assert ".lock" not in listing


# --- looking without taking --------------------------------------------------------------------------------------


def test_holder_reports_who_is_running_it(locks: ScriptLocks, mode: str, tmp_path: Path) -> None:
    if mode == "files":
        (tmp_path / "locks").mkdir()
    assert locks.holder("sync") is None
    held = locks.acquire("sync", "alice")
    holder = locks.holder("sync")
    assert holder is not None and holder.user == "alice"
    held.release()
    assert locks.holder("sync") is None


def test_another_worker_sees_the_holder_through_the_lock_file(lock_dir: Path) -> None:
    """Two ScriptLocks on one directory stand in for two server worker processes."""
    worker_a, worker_b = ScriptLocks(lock_dir), ScriptLocks(lock_dir)
    held = worker_a.acquire("sync", "alice")
    seen = worker_b.holder("sync")
    assert seen is not None and seen.user == "alice"
    with pytest.raises(Busy) as refused:
        worker_b.acquire("sync", "bob")
    assert refused.value.holder is not None and refused.value.holder.user == "alice"
    held.release()
    assert worker_b.holder("sync") is None
    worker_b.acquire("sync", "bob").release()


def test_a_name_left_in_the_file_by_a_crash_does_not_make_the_script_look_busy(lock_dir: Path) -> None:
    (lock_dir / "sync.lock").write_text(json.dumps({"user": "ghost", "script_id": "sync", "since": 1.0, "pid": 1}))
    locks = ScriptLocks(lock_dir)
    assert locks.holder("sync") is None  # the lock itself is what counts, and nobody holds it
    held = locks.acquire("sync", "alice")  # and it can be taken
    holder = locks.holder("sync")
    assert holder is not None and holder.user == "alice"
    held.release()


def test_unreadable_holder_info_is_survivable(lock_dir: Path) -> None:
    worker_a, worker_b = ScriptLocks(lock_dir), ScriptLocks(lock_dir)
    held = worker_a.acquire("sync", "alice")
    (lock_dir / "sync.lock").write_text("{ not json")
    with pytest.raises(Busy) as refused:
        worker_b.acquire("sync", "bob")
    assert refused.value.holder is None  # still refused, just without a name
    assert worker_b.holder("sync") is not None
    held.release()


def test_relentless_status_probes_never_make_a_real_start_fail(lock_dir: Path) -> None:
    """The page asks who holds every lock on every view.  However often that happens, starting a run must still work.

    (With several users on the page this is close to continuous, which is why the probe does not take the lock when
    the script is free.)
    """
    probers = [ScriptLocks(lock_dir) for _ in range(4)]
    runner = ScriptLocks(lock_dir)
    runner.acquire("sync", "alice").release()  # the lock file exists, and is free
    stop = threading.Event()
    probes = 0

    def probe(locks: ScriptLocks) -> None:
        nonlocal probes
        while not stop.is_set():
            locks.holder("sync")  # whatever it answers (the runner below holds it now and then) is fine
            probes += 1

    threads = [threading.Thread(target=probe, args=(locks,)) for locks in probers]
    for thread in threads:
        thread.start()
    try:
        for _ in range(300):
            runner.acquire("sync", "alice").release()  # nobody else runs it: must always succeed
    finally:
        stop.set()
        for thread in threads:
            thread.join()
    assert probes > 100, "the probes were not actually running"


def test_probing_a_free_script_does_not_touch_the_lock_at_all(lock_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Why the test above holds: looking at a free script never competes for the lock."""
    locks = ScriptLocks(lock_dir)
    locks.acquire("sync", "alice").release()

    def no_locking(*args: object, **kwargs: object) -> None:
        raise AssertionError("holder() must not take the lock when the script is free")

    fake_fcntl = types.SimpleNamespace(**{name: getattr(fcntl, name) for name in dir(fcntl)})
    fake_fcntl.flock = no_locking
    monkeypatch.setattr("aGit2Git.runner.locks.fcntl", fake_fcntl)
    assert locks.holder("sync") is None
    assert locks.holder("never-run-at-all") is None


def test_a_held_lock_with_no_name_in_it_is_waited_out_then_refused(
    lock_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Somebody holds the lock without claiming it (e.g. foreign code): wait a little, then refuse rather than race."""
    monkey = os.open(lock_dir / "sync.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(monkey, fcntl.LOCK_EX)
    try:
        locks = ScriptLocks(lock_dir)
        started = time.monotonic()
        with pytest.raises(Busy) as refused:
            locks.acquire("sync", "alice")
        waited = time.monotonic() - started
        assert refused.value.holder is None
        assert 0.5 < waited < 10  # it really waited for the unclaimed lock, and did not wait for ever
        assert "held but unclaimed" in caplog.text
    finally:
        fcntl.flock(monkey, fcntl.LOCK_UN)
        os.close(monkey)
    locks.acquire("sync", "alice").release()  # and once it is free again, all is well


def test_a_real_holder_is_refused_at_once_without_waiting(lock_dir: Path) -> None:
    holder = ScriptLocks(lock_dir)
    held = holder.acquire("sync", "alice")
    started = time.monotonic()
    with pytest.raises(Busy) as refused:
        ScriptLocks(lock_dir).acquire("sync", "bob")
    assert time.monotonic() - started < 0.5, "a user whose script is busy must not be kept waiting"
    assert refused.value.holder is not None and refused.value.holder.user == "alice"
    held.release()


def test_a_run_in_progress_is_visible_even_if_its_name_cannot_be_read(lock_dir: Path) -> None:
    """A corrupt record must not make a running script look free (it would hide a run from the page)."""
    worker_a, worker_b = ScriptLocks(lock_dir), ScriptLocks(lock_dir)
    held = worker_a.acquire("sync", "alice")
    (lock_dir / "sync.lock").write_text("{ not json")
    seen = worker_b.holder("sync")
    assert seen is not None  # busy, even though we cannot say who
    with pytest.raises(Busy):
        worker_b.acquire("sync", "bob")
    held.release()
    assert worker_b.holder("sync") is None


# --- other processes, and crashes --------------------------------------------------------------------------------


def child(lock_dir: Path, body: str) -> subprocess.Popen[str]:
    code = (
        f"import sys, time\nsys.path.insert(0, {str(ROOT)!r})\nfrom pathlib import Path\n"
        f"from aGit2Git.runner.locks import Busy, ScriptLocks\nlocks = ScriptLocks(Path({str(lock_dir)!r}))\n{body}"
    )
    return subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)  # noqa: S603


HOLD_FOR_A_WHILE = """
held = locks.acquire("sync", "child")
print("locked", flush=True)
time.sleep(30)
"""


def test_a_lock_held_by_another_process_is_respected(lock_dir: Path) -> None:
    proc = child(lock_dir, HOLD_FOR_A_WHILE)
    try:
        assert proc.stdout is not None and proc.stdout.readline().strip() == "locked"
        mine = ScriptLocks(lock_dir)
        with pytest.raises(Busy) as refused:
            mine.acquire("sync", "alice")
        assert refused.value.holder is not None and refused.value.holder.user == "child"
        assert refused.value.holder.pid == proc.pid
        holder = mine.holder("sync")
        assert holder is not None and holder.pid == proc.pid
    finally:
        proc.kill()
        proc.wait()


def test_a_crashed_process_never_leaves_a_script_locked(lock_dir: Path) -> None:
    """The kernel drops the lock with the process, so there is no stale lock to clean up by hand."""
    proc = child(lock_dir, HOLD_FOR_A_WHILE)
    assert proc.stdout is not None and proc.stdout.readline().strip() == "locked"
    mine = ScriptLocks(lock_dir)
    with pytest.raises(Busy):
        mine.acquire("sync", "alice")
    proc.kill()  # SIGKILL: no chance to clean up
    proc.wait()
    held = mine.acquire("sync", "alice")  # free at once
    holder = mine.holder("sync")
    assert holder is not None and holder.user == "alice"  # the dead process's name is gone
    held.release()


def test_processes_racing_for_one_script_exactly_one_wins(lock_dir: Path) -> None:
    start_at = time.time() + 1.5
    body = f"""
while time.time() < {start_at}:
    time.sleep(0.001)
try:
    held = locks.acquire("sync", "racer")
    print("got", flush=True)
    time.sleep(1.5)
except Busy:
    print("busy", flush=True)
"""
    procs = [child(lock_dir, body) for _ in range(8)]
    results = []
    for proc in procs:
        assert proc.stdout is not None
        results.append(proc.stdout.read().strip())
        proc.wait()
    assert results.count("got") == 1 and results.count("busy") == 7


# --- trouble -----------------------------------------------------------------------------------------------------


def test_a_missing_directory_means_no_lock_and_nothing_stays_locked(tmp_path: Path) -> None:
    locks = ScriptLocks(tmp_path / "gone")
    with pytest.raises(LockUnavailable):
        locks.acquire("sync", "alice")
    (tmp_path / "gone").mkdir()
    locks.acquire("sync", "alice").release()  # the failed attempt did not leave the in-process lock held


def test_a_directory_that_is_not_one_means_no_lock(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(LockUnavailable):
        ScriptLocks(blocker).acquire("sync", "alice")


def test_a_file_system_that_cannot_lock_means_no_run_and_leaks_nothing(
    lock_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E.g. NFS without a lock manager: refusing is the only safe answer."""
    locks = ScriptLocks(lock_dir)
    before = len(os.listdir("/proc/self/fd"))

    def no_locks(*args: object, **kwargs: object) -> None:
        raise OSError(errno.ENOLCK, "No locks available")

    fake_fcntl = types.SimpleNamespace(**{name: getattr(fcntl, name) for name in dir(fcntl)})
    fake_fcntl.flock = no_locks
    monkeypatch.setattr("aGit2Git.runner.locks.fcntl", fake_fcntl)  # only the lock module sees the broken flock
    with pytest.raises(LockUnavailable):
        locks.acquire("sync", "alice")
    monkeypatch.undo()
    assert len(os.listdir("/proc/self/fd")) == before  # no file descriptor leaked
    locks.acquire("sync", "alice").release()  # and the script is not left locked in memory either


def test_a_refused_attempt_leaks_no_file_descriptors(lock_dir: Path) -> None:
    locks = ScriptLocks(lock_dir)
    held = locks.acquire("sync", "alice")
    other = ScriptLocks(lock_dir)
    before = len(os.listdir("/proc/self/fd"))
    for _ in range(50):
        with pytest.raises(Busy):
            other.acquire("sync", "bob")
        other.holder("sync")
    assert len(os.listdir("/proc/self/fd")) == before
    held.release()


def test_releasing_survives_a_broken_file_descriptor(lock_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    locks = ScriptLocks(lock_dir)
    held = locks.acquire("sync", "alice")
    for fd in range(3, 200):  # sabotage: close the lock file's descriptor behind the lock's back
        try:
            if os.readlink(f"/proc/self/fd/{fd}").endswith("sync.lock"):
                os.close(fd)
        except OSError:
            pass
    held.release()  # must not raise, and must still free the in-process lock
    locks.acquire("sync", "bob").release()


# --- a script that outlives its crashed server -------------------------------------------------------------------


def start_script(tmp_path: Path, body: str = "sleep 30\n") -> tuple[subprocess.Popen[bytes], str]:
    """A real bash process in its own session, like the scripts the server starts."""
    script = tmp_path / "orphan.sh"
    script.write_text(body)
    proc = subprocess.Popen(["/bin/bash", str(script)], start_new_session=True)  # noqa: S603
    time.sleep(0.2)  # let it exec, so that /proc shows its command line
    return proc, str(script)


NOTE_CHILD_THEN_HANG = """
held = locks.acquire("sync", "child")
held.note_child({pid}, {path!r})
print("locked", flush=True)
time.sleep(30)
"""


def crashed_server_that_started(lock_dir: Path, pid: int, path: str) -> None:
    """A server process takes the lock, notes its script, and is then killed: it can clean up nothing."""
    proc = child(lock_dir, NOTE_CHILD_THEN_HANG.format(pid=pid, path=path))
    assert proc.stdout is not None and proc.stdout.readline().strip() == "locked"
    proc.kill()
    proc.wait()


def test_a_script_that_outlives_its_crashed_server_still_counts_as_running(lock_dir: Path, tmp_path: Path) -> None:
    script, path = start_script(tmp_path)
    try:
        crashed_server_that_started(lock_dir, script.pid, path)
        mine = ScriptLocks(lock_dir)
        with pytest.raises(Busy) as refused:  # the lock is free (the kernel dropped it) but the script is not done
            mine.acquire("sync", "alice")
        assert refused.value.holder is not None and refused.value.holder.user == "child"
        assert refused.value.holder.child_pid == script.pid
        seen = mine.holder("sync")  # and the page sees it too
        assert seen is not None and seen.user == "child"
    finally:
        script.kill()
        script.wait()
    held = mine.acquire("sync", "alice")  # when the script is really over, the next user may run it
    assert mine.holder("sync") is not None
    held.release()
    assert mine.holder("sync") is None


def test_a_recycled_pid_is_not_mistaken_for_the_script(lock_dir: Path, tmp_path: Path) -> None:
    """The recorded pid now belongs to something else entirely: that must not lock the script forever."""
    other = subprocess.Popen(["/bin/sleep", "30"])  # noqa: S603 - alive, but not the script
    try:
        crashed_server_that_started(lock_dir, other.pid, str(tmp_path / "the-script.sh"))
        locks = ScriptLocks(lock_dir)
        assert locks.holder("sync") is None
        locks.acquire("sync", "alice").release()
    finally:
        other.kill()
        other.wait()


def test_a_script_that_died_with_its_server_leaves_nothing_behind(lock_dir: Path, tmp_path: Path) -> None:
    script, path = start_script(tmp_path)
    crashed_server_that_started(lock_dir, script.pid, path)
    script.kill()  # e.g. systemd stopped the whole service, script included
    script.wait()
    locks = ScriptLocks(lock_dir)
    assert locks.holder("sync") is None
    locks.acquire("sync", "alice").release()


def test_a_clean_release_leaves_no_trace_of_the_script(lock_dir: Path, tmp_path: Path) -> None:
    script, path = start_script(tmp_path)
    try:
        locks = ScriptLocks(lock_dir)
        held = locks.acquire("sync", "alice")
        held.note_child(script.pid, path)
        info = json.loads((lock_dir / "sync.lock").read_text())
        assert info["child_pid"] == script.pid and info["script_path"] == path  # recorded while it runs
        held.release()
        assert (lock_dir / "sync.lock").read_text() == ""
        locks.acquire("sync", "bob").release()  # no phantom "still running", whatever that pid is doing now
    finally:
        script.kill()
        script.wait()


def test_noting_the_script_after_the_lock_was_given_back_is_ignored(lock_dir: Path) -> None:
    locks = ScriptLocks(lock_dir)
    held = locks.acquire("sync", "alice")
    held.release()
    held.note_child(os.getpid(), "/x")  # a late call must not write into a lock that is no longer ours
    assert (lock_dir / "sync.lock").read_text() == ""


def test_a_stale_handle_cannot_write_into_the_next_holders_lock(lock_dir: Path) -> None:
    """Alice's old handle must not change what the lock file says about bob, who holds the lock now."""
    locks = ScriptLocks(lock_dir)
    alice = locks.acquire("sync", "alice")
    alice.release()
    bob = locks.acquire("sync", "bob")
    alice.note_child(4242, "/srv/scripts/alices.sh")  # a late call from the previous run's handle
    holder = locks.holder("sync")
    assert holder is not None and holder.user == "bob" and holder.child_pid == 0
    assert json.loads((lock_dir / "sync.lock").read_text())["child_pid"] == 0
    bob.release()


def test_the_holder_in_this_process_knows_the_script_process(lock_dir: Path) -> None:
    locks = ScriptLocks(lock_dir)
    held = locks.acquire("sync", "alice")
    held.note_child(4242, "/srv/scripts/sync.sh")
    holder = locks.holder("sync")
    assert holder is not None and (holder.child_pid, holder.script_path) == (4242, "/srv/scripts/sync.sh")
    held.release()


def test_in_memory_locks_accept_the_note_and_ignore_it() -> None:
    locks = ScriptLocks()
    held = locks.acquire("sync", "alice")
    held.note_child(4242, "/x")  # nothing to persist, and nothing breaks
    held.release()


def test_lock_files_written_before_this_field_existed_still_load(lock_dir: Path) -> None:
    (lock_dir / "sync.lock").write_text(json.dumps({"user": "old", "script_id": "sync", "since": 1.0, "pid": 7}))
    locks = ScriptLocks(lock_dir)
    assert locks.holder("sync") is None  # free, and no script process recorded: nothing to wait for
    locks.acquire("sync", "alice").release()
