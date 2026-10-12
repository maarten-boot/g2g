"""The output of the last run of every script, kept on disk so it can be viewed and downloaded afterwards.

One run per script is kept (the next run replaces it), so the disk use is bounded by the number of scripts times the
output cap.  The output is written while the script runs, whether or not anybody is watching, so a closed browser tab
loses nothing and a second person can follow a run live.  Storing never gets in the way of running: a full disk or a
broken directory is logged and the script carries on.

Layout, all inside one private directory:  <script_id>.json  (who, when, how it ended)
                                           <script_id>.<run_id>.log  (the raw output)
"""

import json
import logging
import os
import re
import secrets
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

log = logging.getLogger("aGit2Git.runner.runs")

_SCRIPT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_RUN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_MAX_OFFSET = 2**62  # far beyond any file we write, far below what seek() can take


@dataclass(frozen=True)
class RunInfo:
    script_id: str
    run_id: str
    user: str
    started: float  # unix time
    finished: float | None = None  # None while the run is going
    status: str | None = None  # "exit code 0", "timed out after 60s and was killed", ...
    exit_code: int | None = None
    size: int = 0  # bytes of output

    @property
    def running(self) -> bool:
        return self.finished is None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class RunRecorder:
    """Writes one run's output.  Never raises: storage trouble must not stop or break the script."""

    def __init__(self, store: RunStore, info: RunInfo, fd: int) -> None:
        self.run_id = info.run_id
        self._store = store
        self._info = info
        self._fd: int | None = fd
        self._size = 0
        self._broken = False
        self._finished = False

    def write(self, chunk: bytes) -> None:
        if self._broken or self._fd is None:
            return
        try:
            view = memoryview(chunk)
            while view:
                written = os.write(self._fd, view)
                view = view[written:]
            self._size += len(chunk)
        except OSError as exc:
            self._broken = True
            log.error("cannot record the output of %s run %s any more: %s", self._info.script_id, self.run_id, exc)

    def finish(self, status: str, exit_code: int | None, footer: bytes = b"") -> None:
        """Close the record with the way the run ended.  Safe to call more than once."""
        if self._finished:
            return
        self._finished = True
        self.write(footer)
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        if self._broken:
            status += " (the output could not be saved completely)"
        self._store.write_meta(
            replace(self._info, finished=time.time(), status=status, exit_code=exit_code, size=self._size)
        )


class RunStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._mark_interrupted()

    # --- writing ---------------------------------------------------------------------------------------------------

    def begin(self, script_id: str, user: str) -> RunRecorder:
        """Start recording a new run; it replaces the previous one as 'the last run'."""
        run_id = secrets.token_hex(8)
        fd = os.open(self._log_path(script_id, run_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        previous = self.last(script_id)
        info = RunInfo(script_id, run_id, user, time.time())
        self.write_meta(info)  # switch to the new run first ...
        if previous is not None and previous.run_id != run_id:
            self._unlink(self._log_path(script_id, previous.run_id))  # ... then drop the old output
        return RunRecorder(self, info, fd)

    def write_meta(self, info: RunInfo) -> None:
        target = self._meta_path(info.script_id)
        tmp = target.with_name(f"{target.name}.{secrets.token_hex(4)}.tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(asdict(info), handle)
            os.replace(tmp, target)  # atomic: readers see the old record or the new one, never half of one
        except OSError as exc:
            log.error("cannot write the run record of %s: %s", info.script_id, exc)
            self._unlink(tmp)

    # --- reading ---------------------------------------------------------------------------------------------------

    def last(self, script_id: str) -> RunInfo | None:
        path = self._meta_path(script_id)  # validated first, outside the try: a bad id is a bug, not "no run yet"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            info = RunInfo(**data)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError) as exc:
            log.warning("unreadable run record for %s: %s", script_id, exc)
            return None
        if info.running:  # the size is not final yet: ask the file
            try:
                return replace(info, size=self._log_path(script_id, info.run_id).stat().st_size)
            except OSError:
                return info
        return info

    def lookup(self, script_id: str, run_id: str) -> RunInfo | None:
        """The run, but only if it is the one currently kept; ids from the outside are checked before use."""
        if not _RUN_ID_RE.match(run_id):
            return None
        info = self.last(script_id)
        return info if info is not None and info.run_id == run_id else None

    def log_path(self, info: RunInfo) -> Path:
        return self._log_path(info.script_id, info.run_id)

    def read(self, info: RunInfo, offset: int, limit: int) -> bytes:
        """Up to `limit` bytes of output from `offset` on."""
        path = self.log_path(info)  # validated first, outside the try: a malformed id is a bug, not "empty output"
        try:
            with path.open("rb") as handle:
                handle.seek(min(max(0, offset), _MAX_OFFSET))  # an absurd offset must not blow up the seek
                return handle.read(limit)
        except OSError, ValueError, OverflowError:
            return b""

    def tail(self, info: RunInfo, max_bytes: int) -> tuple[bytes, int, int]:
        """The last `max_bytes` of the output: (bytes, offset they start at, offset they end at)."""
        try:
            size = self.log_path(info).stat().st_size
        except OSError:
            return b"", 0, 0
        start = max(0, size - max_bytes)
        data = self.read(info, start, size - start)
        if start:  # do not begin in the middle of a multi-byte character
            skip = 0
            while skip < min(3, len(data)) and data[skip] & 0xC0 == 0x80:
                skip += 1
            data, start = data[skip:], start + skip
        return data, start, start + len(data)

    # --- housekeeping ----------------------------------------------------------------------------------------------

    def _mark_interrupted(self) -> None:
        """Runs still marked as going when the server starts were cut off by a restart: say so instead of 'running'."""
        for meta in self.directory.glob("*.json"):
            info = self.last(meta.stem)
            if info is not None and info.running:
                self.write_meta(replace(info, finished=time.time(), status="interrupted (the server was restarted)"))

    def _meta_path(self, script_id: str) -> Path:
        return self.directory / f"{self._valid_script_id(script_id)}.json"

    def _log_path(self, script_id: str, run_id: str) -> Path:
        if not _RUN_ID_RE.match(run_id):
            raise ValueError(f"bad run id {run_id!r}")
        return self.directory / f"{self._valid_script_id(script_id)}.{run_id}.log"

    @staticmethod
    def _valid_script_id(script_id: str) -> str:
        if not _SCRIPT_ID_RE.match(script_id):
            raise ValueError(f"bad script id {script_id!r}")  # never build a path from anything else
        return script_id

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass
