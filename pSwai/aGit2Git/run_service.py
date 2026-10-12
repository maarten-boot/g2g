"""Run: the django side of the script runner (docs/run-design.md §5, §8).

The framework-free runner (aGit2Git.runner) writes through a store; here that store keeps one Run row per run in the
database and the output in RUNNER_RUNS_DIR/<run id>.log. One ScriptRunner per process; the per-script locks are flock
files in RUNNER_RUNS_DIR, so one run per script holds across the gunicorn processes.
"""

import logging
import os
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, connection
from django.utils import timezone

from aGit2Git.models import Run
from aGit2Git.runner.locks import ScriptLocks
from aGit2Git.runner.runner import MAX_TIMEOUT, ConfigError, ScriptRunner, load_scripts

log = logging.getLogger(__name__)


def status_of(result: str, exit_code: int | None) -> str:
    """The Run status for the runner's status line ("exit code 0", "timed out after 300s and was killed", ...)."""
    if result.startswith("timed out"):
        return "timed_out"
    if result.startswith("output limit"):
        return "output_capped"
    if result.startswith("cancelled") or exit_code is None:
        return "interrupted"
    return "succeeded" if exit_code == 0 else "failed"


def output_path(run: Run) -> Path:
    # from the run's UUID only, never from anything in a request (Flask spec §14.2)
    return Path(settings.RUNNER_RUNS_DIR) / f"{run.id}.log"


class DbRunRecorder:
    """Writes one run's output and closes its Run row.  Never raises: storage trouble must not stop the script."""

    def __init__(self, run: Run, fd: int) -> None:
        self.run_id = str(run.id)
        self._run_pk = run.pk
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
            log.error("cannot record the output of run %s any more: %s", self.run_id, exc)

    def started(self, pid: int) -> None:
        try:
            Run.objects.filter(pk=self._run_pk).update(pid=pid)
        except DatabaseError as exc:
            log.error("cannot note the pid of run %s: %s", self.run_id, exc)

    def finish(self, result: str, exit_code: int | None, footer: bytes = b"") -> None:
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
        status = status_of(result, exit_code)
        if self._broken:
            result += " (the output could not be saved completely)"
        try:
            Run.objects.filter(pk=self._run_pk).update(
                status=status,
                result=result[:200],
                exit_code=exit_code,
                finished_at=timezone.now(),
                output_bytes=self._size,
            )
        except DatabaseError as exc:
            log.error("cannot record the end of run %s (%s): %s", self.run_id, result, exc)


class DbRunStore:
    """Creates the Run row and the output file for a new run (the runner's store interface)."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def begin(self, script_id: str, username: str, user: Any = None, repo_pair: Any = None) -> DbRunRecorder:
        try:
            run = Run.objects.create(
                script_id=script_id, started_by=user, started_by_name=username, repo_pair=repo_pair
            )
        except DatabaseError as exc:
            # the runner records nothing then, but still runs the script (recording is best-effort, Flask spec §10)
            raise ValueError(f"cannot create the run record: {exc}") from exc
        fd = os.open(self.directory / f"{run.id}.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        return DbRunRecorder(run, fd)


def _close_thread_connection() -> None:
    """The end of a run's thread: its own database connection is not needed any more."""
    connection.close()


# The allowlist "generation" in the cache (shared by the processes on one machine): a reload in one process raises it,
# and the other processes reload when they see it (docs/run-design.md §7).
GENERATION_KEY = "g2g-runner-allowlist-generation"

_runner: ScriptRunner | None = None
_runner_generation = 0
_runner_lock = threading.Lock()


def _generation() -> int:
    return int(cache.get(GENERATION_KEY, 0))


def get_runner() -> ScriptRunner | None:
    """The process's ScriptRunner, or None when Run is switched off or the allowlist cannot be loaded.

    Created on first use (then the runs a restart cut short are marked interrupted); re-read when another process
    has reloaded the allowlist. A reload that fails keeps the allowlist in force."""
    global _runner, _runner_generation
    if not settings.RUNNER_ALLOWLIST or not settings.RUNNER_RUNS_DIR:
        return None
    with _runner_lock:
        if _runner is None:
            runs_dir = Path(settings.RUNNER_RUNS_DIR)
            try:
                scripts = load_scripts(Path(settings.RUNNER_ALLOWLIST))
                runs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                _runner = ScriptRunner(
                    scripts,
                    config_file=Path(settings.RUNNER_ALLOWLIST),
                    store=DbRunStore(runs_dir),  # type: ignore[arg-type]
                    locks=ScriptLocks(runs_dir),
                    on_thread_end=_close_thread_connection,
                )
            except (ConfigError, OSError) as exc:
                log.error("Run is not available: %s", exc)
                return None
            _runner_generation = _generation()
            mark_interrupted_runs(_runner)
        elif _runner_generation != (current := _generation()):
            _runner_generation = current
            try:
                _runner.reload()
            except ConfigError as exc:
                log.error("the allowlist could not be reloaded, the previous one stays in force: %s", exc)
        return _runner


def reload_allowlist(runner: ScriptRunner) -> tuple[list[str], list[str], list[str]]:
    """Re-read the allowlist here and tell the other processes to do the same; (added, removed, changed).
    Raises ConfigError, and then the allowlist in force stays as it was everywhere."""
    global _runner_generation
    runner.reload()
    with _runner_lock:
        try:
            _runner_generation = cache.incr(GENERATION_KEY)
        except ValueError:  # not in the cache yet
            cache.set(GENERATION_KEY, 1, timeout=None)
            _runner_generation = 1
    return runner.last_reload or ([], [], [])


def mark_interrupted_runs(runner: ScriptRunner) -> int:
    """Runs still "running" that nobody runs any more (a restart cut them short) become "interrupted" (Flask spec
    §10). Still running: the script's lock is held, or its script lives on after the server died (the lock check
    sees that too). A run older than the longest timeout cannot be running any more in any case."""
    oldest_possible = timezone.now() - timedelta(seconds=MAX_TIMEOUT + 300)
    count = 0
    for run in Run.objects.filter(status=Run.RUNNING):
        if run.started_at > oldest_possible and runner.locks.holder(run.script_id) is not None:
            continue
        updated = Run.objects.filter(pk=run.pk, status=Run.RUNNING).update(
            status="interrupted", result="interrupted: the server stopped while it ran", finished_at=timezone.now()
        )
        if updated:
            log.warning("run %s of %s was cut short by a restart: marked interrupted", run.pk, run.script_id)
            count += updated
    return count


def purge_old_runs(limit: int | None = None, dry_run: bool = False) -> int:
    """Delete the runs older than RUN_HISTORY_DAYS, with their output files; never a running one."""
    cutoff = timezone.now() - timedelta(days=settings.RUN_HISTORY_DAYS)
    old = Run.objects.filter(started_at__lt=cutoff).exclude(status=Run.RUNNING).order_by("started_at")
    runs = list(old[:limit] if limit else old)
    if dry_run or not runs:
        return len(runs)
    for run in runs:
        try:
            output_path(run).unlink(missing_ok=True)
        except OSError as exc:
            log.error("cannot delete the output of run %s: %s", run.pk, exc)
    Run.objects.filter(pk__in=[r.pk for r in runs]).delete()
    log.info("deleted %d runs older than %d days", len(runs), settings.RUN_HISTORY_DAYS)
    return len(runs)


def reset_runner() -> None:
    """Forget the process's runner (tests; settings changed)."""
    global _runner, _runner_generation
    with _runner_lock:
        _runner = None
        _runner_generation = 0
