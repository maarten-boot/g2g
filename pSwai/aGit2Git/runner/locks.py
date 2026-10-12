"""One run of a script at a time, however many users, threads or server processes are involved.

Every script has a lock file, `<script_id>.lock` in the runs directory.  Starting a run takes an exclusive `flock` on it
before anything else happens, and the lock is held until the run is over.  A second attempt, from any user, thread or
worker process, is refused at once and told who is running the script and since when.  When the first run is over the
next user may start it again.

Why a file lock (and not only a lock in memory): it works across processes, so it stays correct with several server
workers, and the kernel drops it when the holding process dies, so a crash can never leave a script locked for good.
The lock file is never deleted (deleting a file that others may be about to lock is the classic way to break file
locking); who holds the lock is written into it for the message to the next user, and cleared again on release.

A hard crash of the server drops the lock at once, but the script it started may live on in its own session.  So the
lock file also records the process the script runs as: a free lock whose recorded script process is still alive (and
still has that script on its command line, so a recycled pid cannot fool us) counts as "still running".  Where
there is no /proc to check that against, a crashed server's orphan is not noticed.

The runs directory must be on a local file system, or one where `flock` really is shared between the hosts that use it.
If a lock cannot be taken at all the run does not happen: exclusivity matters more than availability here.
"""

import fcntl
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

log = logging.getLogger("aGit2Git.runner.locks")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
# A holder writes its name into the lock file as soon as it has the lock, and clears it on release.  So an empty lock
# file means "free", which lets holder() answer the common case without touching the lock at all, and lets acquire()
# tell a real holder (name present: refuse at once) from a passing status probe (file empty: wait it out).
_WAIT_FOR_PROBES = 2.0  # seconds an acquire keeps trying while the lock is taken but nobody has claimed it
_RETRY_PAUSE = 0.005


@dataclass(frozen=True)
class LockHolder:
    user: str
    script_id: str
    since: float  # unix time
    pid: int  # the server process that holds the lock
    child_pid: int = 0  # the process the script itself runs as (set once it has been started)
    script_path: str = ""  # what that process has on its command line


class Busy(Exception):
    """The script is being run by somebody else right now."""

    def __init__(self, script_id: str, holder: LockHolder | None = None) -> None:
        super().__init__(script_id)
        self.script_id = script_id
        self.holder = holder


class LockUnavailable(Exception):
    """The lock could not be taken for a reason other than somebody else holding it (e.g. the directory is gone)."""


class Held:
    """A lock being held.  release() is safe to call more than once."""

    def __init__(self, release: Callable[[], None], note_child: Callable[[int, str], None] | None = None) -> None:
        self._release = release
        self._note_child = note_child
        self._released = False

    def note_child(self, pid: int, script_path: str) -> None:
        """Record which process the script runs as, so that it still counts as running if this server is killed."""
        if self._note_child is not None and not self._released:
            self._note_child(pid, script_path)

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._release()


class ScriptLocks:
    """Per-script exclusive locks.  Without a directory they are in-memory only (one process), which is for tests."""

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = directory
        self._guard = threading.Lock()
        # Never shrunk, not even when a script leaves the allowlist: if it comes back while its old run is still going,
        # it must still find itself locked.
        self._threads: dict[str, threading.Lock] = {}
        self._holders: dict[str, LockHolder] = {}  # who holds which lock in THIS process

    # --- taking and giving back -----------------------------------------------------------------------------------

    def acquire(self, script_id: str, user: str) -> Held:
        """Take the script's lock, or raise Busy (somebody holds it) / LockUnavailable (it cannot be taken)."""
        self._check(script_id)
        thread_lock = self._thread_lock(script_id)
        if not thread_lock.acquire(blocking=False):
            raise Busy(script_id, self._holder_in_process(script_id) or self._read_holder(script_id))
        try:
            fd = self._lock_file(script_id) if self._dir is not None else None
            leftover = self._read_holder(script_id) if fd is not None else None  # who held it last, if not cleanly
            if leftover is not None and _script_still_running(leftover):
                # The lock is free, but a run that outlived its server is not over.  Hand the lock back WITHOUT
                # clearing the file: that is the evidence the next attempt (and the page) needs as well.
                self._release(script_id, fd, None, clear=False)
                raise Busy(script_id, leftover)
        except BaseException:
            thread_lock.release()
            raise
        holder = LockHolder(user, script_id, time.time(), os.getpid())
        if fd is not None:
            self._write_holder(fd, holder)
        with self._guard:
            self._holders[script_id] = holder
        return Held(
            lambda: self._release(script_id, fd, thread_lock),
            lambda pid, path: self._note_child(script_id, fd, pid, path),
        )

    def holder(self, script_id: str) -> LockHolder | None:
        """Who is running the script right now (None if nobody).  Never blocks, and never waits for the lock.

        The page calls this for every script on every view, so it must not get in the way of somebody starting a run:
        an empty lock file is answered without touching the lock at all.
        """
        self._check(script_id)
        here = self._holder_in_process(script_id)
        if here is not None or self._dir is None:
            return here
        if not self._is_claimed(script_id):
            return None  # no lock file, or an empty one: free, and answered without touching the lock
        claimed = self._read_holder(script_id)
        try:
            fd = os.open(self._path(script_id), os.O_RDONLY)
        except OSError:
            return None
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                # Somebody (another worker) holds it.  `claimed` is who, or None if the file could not be read.
                return claimed or LockHolder("somebody", script_id, 0.0, 0)
            except OSError:
                return None
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        # The lock is free but a name was left behind: the server that held it died.  Its script may still be running.
        return claimed if claimed is not None and _script_still_running(claimed) else None

    # --- internals ------------------------------------------------------------------------------------------------

    def _lock_file(self, script_id: str) -> int:
        path = self._path(script_id)
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:
            raise LockUnavailable(f"cannot open the lock file {path}: {exc}") from exc
        deadline = time.monotonic() + _WAIT_FOR_PROBES
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if self._is_claimed(script_id):  # somebody is really running it: say so at once, do not wait
                    claimed = self._read_holder(script_id)
                    os.close(fd)
                    raise Busy(script_id, claimed) from None
                if time.monotonic() >= deadline:
                    # Taken, but still unclaimed after all this time.  Refuse rather than risk a second run.
                    log.warning("the lock of %s is held but unclaimed; not starting a second run", script_id)
                    os.close(fd)
                    raise Busy(script_id, None) from None
                time.sleep(_RETRY_PAUSE)  # a passing status probe, or a holder that has not written its name yet
            except OSError as exc:
                os.close(fd)
                raise LockUnavailable(f"cannot lock {path}: {exc}") from exc

    def _note_child(self, script_id: str, fd: int | None, pid: int, script_path: str) -> None:
        with self._guard:
            current = self._holders.get(script_id)
            if current is None:
                return
            holder = replace(current, child_pid=pid, script_path=script_path)
            self._holders[script_id] = holder
        if fd is not None:
            self._write_holder(fd, holder)

    def _release(
        self, script_id: str, fd: int | None, thread_lock: threading.Lock | None, *, clear: bool = True
    ) -> None:
        with self._guard:
            self._holders.pop(script_id, None)
        try:
            if fd is not None:
                steps: list[Callable[[], object]] = [
                    lambda: os.ftruncate(fd, 0) if clear else None,  # forget who held it
                    lambda: fcntl.flock(fd, fcntl.LOCK_UN),
                    lambda: os.close(fd),
                ]
                for step in steps:  # each on its own, whatever happens to the others
                    try:
                        step()
                    except OSError as exc:
                        log.warning("while releasing the lock of %s: %s", script_id, exc)
        finally:
            if thread_lock is not None:
                thread_lock.release()

    def _write_holder(self, fd: int, holder: LockHolder) -> None:
        try:
            os.ftruncate(fd, 0)
            os.pwrite(fd, json.dumps(asdict(holder)).encode(), 0)
        except OSError as exc:  # only the message to the next user suffers: the lock itself is held
            log.warning("cannot record who holds the lock of %s: %s", holder.script_id, exc)

    def _is_claimed(self, script_id: str) -> bool:
        """Has whoever holds the lock written their name into it?  (An unreadable name still counts as claimed.)"""
        if self._dir is None:
            return False
        try:
            return self._path(script_id).stat().st_size > 0
        except OSError:
            return False  # no lock file yet: the script has never been run

    def _read_holder(self, script_id: str) -> LockHolder | None:
        if self._dir is None:
            return None
        try:
            return LockHolder(**json.loads(self._path(script_id).read_text(encoding="utf-8")))
        except OSError, ValueError, TypeError:
            return None

    def _holder_in_process(self, script_id: str) -> LockHolder | None:
        with self._guard:
            return self._holders.get(script_id)

    def _thread_lock(self, script_id: str) -> threading.Lock:
        with self._guard:
            return self._threads.setdefault(script_id, threading.Lock())

    def _path(self, script_id: str) -> Path:
        if self._dir is None:
            raise RuntimeError("in-memory locks have no files")
        return self._dir / f"{script_id}.lock"

    @staticmethod
    def _check(script_id: str) -> None:
        if not _ID_RE.match(script_id):
            raise ValueError(f"bad script id {script_id!r}")  # never build a path from anything else


def _script_still_running(holder: LockHolder) -> bool:
    """Is the script process a previous holder recorded still alive?  (Linux: through /proc.)"""
    if holder.child_pid <= 0 or not holder.script_path:
        return False
    try:
        arguments = Path(f"/proc/{holder.child_pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False  # no such process (or no /proc to ask): not known to be running
    return holder.script_path.encode() in arguments  # a recycled pid would be running something else
