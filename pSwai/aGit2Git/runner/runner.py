"""Allowlisted script runner.

Only scripts declared in the TOML allowlist can ever be executed, each one restricted to the LDAP groups listed for it.
Output is streamed while the script runs.  Scripts are executed with ``bash`` (no shell, fixed argv, scrubbed
environment, own process group, hard timeout, output cap).

Copied from the Flask tool g2g-scripts-manual (see docs/run-design.md) and adapted for g2g: logging is configured by
Django, and the Flask tool's manual groups (a file of user names) are replaced by "local:<name>", a django group that
is checked by the caller (who passes it in the user's groups as "local:<name>").  This module does not import Django.
"""

import inspect
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import tomllib
from collections.abc import Callable, Collection, Generator, Iterable
from dataclasses import dataclass
from pathlib import Path

from .locks import Busy as Busy  # noqa: PLC0414 - re-exported: callers catch runner.Busy
from .locks import LockUnavailable as LockUnavailable  # noqa: PLC0414
from .locks import ScriptLocks
from .runs import RunRecorder, RunStore

log = logging.getLogger("aGit2Git.runner")


MIN_TIMEOUT = 1
MAX_TIMEOUT = 3600
DEFAULT_TIMEOUT = 300
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
_CHUNK = 4096
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
# "profile" is not here: it is consumed while merging (see _with_inherited), so it never reaches _parse_entry.
_ENTRY_KEYS = {"name", "description", "file", "groups", "timeout"}
_INHERITABLE_KEYS = {"groups", "timeout", "description"}  # what [defaults] and a [profiles.<name>] may set
_SETTINGS_KEYS = {"scripts_dir", "allow_dirs", "include"}
# a django group (managed in the admin), instead of an LDAP group DN; the caller passes these as "local:<name>"
LOCAL_PREFIX = "local:"
_GROUP_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_INCLUDED_KEYS = {"scripts", "defaults"}  # what an included (web-editable) file may contain: never [settings]/[groups]
_CHILD_PATH = "/usr/local/bin:/usr/bin:/bin"


def normalize_dn(dn: str) -> str:
    """An LDAP DN in one spelling, so DNs can be compared as strings: DNs are case-insensitive, and a space after a
    comma is not part of the name.  The caller normalizes the user's group DNs the same way.  (An escaped comma inside
    a value is not split correctly; group DNs with one are not expected.)"""
    return ",".join(part.strip() for part in dn.split(",")).casefold()


class ConfigError(Exception):
    """The allowlist file is missing or invalid.  Raised at startup so a bad deploy fails loudly."""


class UnknownScript(Exception):
    pass


class NotAllowed(Exception):
    pass


@dataclass(frozen=True)
class ScriptDef:
    id: str
    name: str
    description: str
    path: Path
    groups: frozenset[str]  # LDAP group DNs and "local:<django group>"
    timeout: int

    def allowed_for(self, user_groups: Collection[str]) -> bool:
        """user_groups: the user's LDAP group DNs plus "local:<name>" for each of their django groups."""
        return not self.groups.isdisjoint(user_groups)

    def allowed_by_local_group(self, user_groups: Collection[str]) -> bool:
        """True when ONLY a local (django) group lets this user in: worth saying so in the log."""
        matching = self.groups.intersection(user_groups)
        return bool(matching) and all(group.startswith(LOCAL_PREFIX) for group in matching)


def _entry_error(script_id: str, message: str) -> ConfigError:
    return ConfigError(f"script {script_id!r}: {message}")


def _parse_entry(
    script_id: str,
    entry: object,
    base: Path,
    allowed: tuple[Path, ...],
    names: dict[str, str],
    *,
    main_file: bool,
) -> ScriptDef:
    if not _ID_RE.match(script_id):
        raise _entry_error(script_id, "id must match [a-z0-9][a-z0-9_-]* (max 64 chars)")
    if not isinstance(entry, dict):
        raise _entry_error(script_id, "must be a table")
    unknown = set(entry) - _ENTRY_KEYS
    if unknown:
        hints = "".join(_misplaced(key, f"[scripts.{script_id}]") for key in sorted(unknown))
        raise _entry_error(script_id, f"unknown keys {sorted(unknown)}.{hints}")

    file = entry.get("file")
    if not isinstance(file, str) or not file:
        raise _entry_error(script_id, "'file' is required")
    # resolve() follows symlinks, so where a link POINTS is what has to be allowed, not where it sits.
    try:
        path = (base / file).resolve()
        exists = path.is_file()
        dangling = path.is_symlink() or (base / file).is_symlink()
    except (OSError, RuntimeError) as exc:  # too long a name, an unreadable directory, a loop of symlinks, ...
        raise _entry_error(script_id, f"{file!r} cannot be used: {exc}") from exc
    if not any(path.is_relative_to(directory) for directory in allowed):
        where = ", ".join(str(directory) for directory in allowed)
        raise _entry_error(
            script_id,
            f"{file!r} resolves to {path}, which is outside the allowed directories ({where}). A symlink is fine, "
            "but what it points at must be in one of them; add its directory to allow_dirs in [settings] if that is "
            "what you want.",
        )
    if not exists:
        raise _entry_error(
            script_id, f"file {path} does not exist{' (a symlink pointing at nothing?)' if dangling else ''}"
        )

    # After the key check above, so that a typo is reported as a typo rather than as its consequence.
    groups = _resolve_groups(script_id, _as_group_list(script_id, entry.get("groups")), names, main_file=main_file)

    timeout = entry.get("timeout", DEFAULT_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not MIN_TIMEOUT <= timeout <= MAX_TIMEOUT:
        raise _entry_error(script_id, f"'timeout' must be an integer {MIN_TIMEOUT}..{MAX_TIMEOUT} seconds")

    name = entry.get("name", script_id)
    description = entry.get("description", "")
    if not isinstance(name, str) or not isinstance(description, str):
        raise _entry_error(script_id, "'name' and 'description' must be strings")
    return ScriptDef(script_id, name, description, path, frozenset(groups), timeout)


_MISPLACED = {  # a key that belongs somewhere else: TOML puts every key under the last section header above it
    **dict.fromkeys(_SETTINGS_KEYS, "[settings]"),
    **dict.fromkeys(_INHERITABLE_KEYS, "[defaults] (or a profile, or the script itself)"),
    "include": "[settings]",
    "profile": "a [scripts.<id>] table",
    "file": "a [scripts.<id>] table",
    "name": "a [scripts.<id>] table",
}


def _misplaced(key: str, section: str) -> str:
    """The extra sentence for a key that is simply in the wrong place, which is nearly always what has happened."""
    belongs = _MISPLACED.get(key)
    if belongs is None or belongs == section:
        return ""
    return (
        f" The key {key!r} belongs in {belongs}. In TOML every key goes under the section header above it, so a key "
        f"written below {section} is part of {section}: move it above the first header, or under its own one."
    )


def _group_names(raw: dict[str, object], config_file: Path) -> dict[str, str]:
    """The [groups] table: short name -> LDAP group DN, so scripts can say "ops" instead of the whole DN."""
    table = raw.get("groups", {})
    if not isinstance(table, dict):
        raise ConfigError(f'{config_file}: [groups] must be a table of name = "<group DN>" entries')
    names: dict[str, str] = {}
    for name, dn in table.items():
        if not _GROUP_NAME_RE.match(name):
            raise ConfigError(
                f"{config_file}: group name {name!r} must match [a-z0-9][a-z0-9_-]* (max 64 chars)"
                f"{_misplaced(name, '[groups]')}"
            )
        if not isinstance(dn, str) or "=" not in dn:
            raise ConfigError(
                f"{config_file}: [groups] maps a short name to one LDAP group DN, so {name!r} = {dn!r} makes no "
                f"sense.{_misplaced(name, '[groups]')}"
            )
        names[name] = dn
    return names


def _resolve_groups(
    script_id: str,
    groups: list[str],
    names: dict[str, str],
    *,
    main_file: bool,
) -> list[str]:
    """What a script's group list means: LDAP group DNs, and "local:<name>" django groups."""
    resolved: list[str] = []
    for group in groups:
        if group.startswith(LOCAL_PREFIX):
            name = group[len(LOCAL_PREFIX) :]
            if not main_file:
                raise _entry_error(
                    script_id,
                    f"{group!r} can only be used in the main allowlist, not in an included file (that is what keeps "
                    "access by local group out of the files administrators edit)",
                )
            if not name.strip() or len(name) > 150 or any(ord(c) < 32 for c in name):
                raise _entry_error(script_id, f"{group!r} is not a usable django group name")
            resolved.append(group)
        elif group in names:
            resolved.append(normalize_dn(names[group]))
        elif "=" in group:  # a DN written out in full: always allowed, [groups] is a convenience not a gate
            resolved.append(normalize_dn(group))
        else:
            known = ", ".join(sorted(names)) or "none are defined"
            raise _entry_error(
                script_id,
                f"group {group!r} is not in [groups], is not a DN and is not local:<django group> "
                f"(known names: {known})",
            )
    return resolved


def read_group_names(config_file: Path) -> dict[str, str]:
    """The [groups] name -> DN table of the main allowlist, for settings elsewhere that name a group."""
    return _group_names(_read_toml(config_file), config_file)


def _included_files(settings: dict[str, object], config_file: Path) -> list[Path]:
    """The files named by include = [...] in [settings].  Entries may be glob patterns; order is sorted by path."""
    raw = settings.get("include", [])
    if not isinstance(raw, list) or not all(isinstance(entry, str) and entry for entry in raw):
        raise ConfigError(f"{config_file}: include must be a list of file names or glob patterns")
    found: list[Path] = []
    for pattern in raw:
        if Path(pattern).is_absolute():
            raise ConfigError(f"{config_file}: include entry {pattern!r} must be relative to {config_file.parent}")
        matches = sorted(config_file.parent.glob(pattern))
        if not matches and not any(character in pattern for character in "*?["):
            raise ConfigError(f"{config_file}: include entry {pattern!r} does not exist")
        found.extend(match for match in matches if match.is_file())
    return found


def _read_toml(path: Path) -> dict[str, object]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc


def _inheritable(table: object, where: str) -> dict[str, object]:
    """Check a [defaults] or [profiles.<name>] table and return it.  Only settings a script may inherit belong there."""
    if not isinstance(table, dict):
        raise ConfigError(f"{where} must be a table")
    unknown = set(table) - _INHERITABLE_KEYS
    if unknown:
        section = where.rsplit(": ", 1)[-1]
        hints = "".join(_misplaced(key, section) for key in sorted(unknown))
        raise ConfigError(f"{where}: {sorted(unknown)} cannot be set there (only {sorted(_INHERITABLE_KEYS)}).{hints}")
    return table


def _profiles(raw: dict[str, object], config_file: Path) -> dict[str, dict[str, object]]:
    """The named sets of settings scripts can point at with profile = "<name>"."""
    tables = raw.get("profiles", {})
    if not isinstance(tables, dict):
        raise ConfigError(f"{config_file}: [profiles] must be a table of tables ([profiles.<name>])")
    return {name: _inheritable(table, f"{config_file}: [profiles.{name}]") for name, table in tables.items()}


def _with_inherited(
    script_id: str, entry: object, defaults: dict[str, object], profiles: dict[str, dict[str, object]]
) -> dict[str, object]:
    """One script's settings: its own, over its profile's, over [defaults]."""
    if not isinstance(entry, dict):
        raise _entry_error(script_id, "must be a table")
    profile_name = entry.get("profile")
    profile: dict[str, object] = {}
    if profile_name is not None:
        if not isinstance(profile_name, str) or profile_name not in profiles:
            known = ", ".join(sorted(profiles)) or "none are defined"
            raise _entry_error(script_id, f"profile {profile_name!r} does not exist (known profiles: {known})")
        profile = profiles[profile_name]
    merged = {**defaults, **profile, **entry}
    merged.pop("profile", None)  # consumed here; anything else left over is a typo and _parse_entry says so
    return merged


def _allowed_dirs(settings: dict[str, object], base: Path, config_file: Path) -> tuple[Path, ...]:
    """The directories a script file may resolve into: the scripts dir, plus whatever allow_dirs names.

    Symlinks in the scripts dir are the point of allow_dirs: the link may stay with the other scripts while the script
    itself lives in, say, a checkout.  Everything in these directories is as trusted as the scripts dir itself, so
    they should be owned by root and not writable by the service user.
    """
    raw = settings.get("allow_dirs", [])
    if not isinstance(raw, list) or not all(isinstance(entry, str) and entry for entry in raw):
        raise ConfigError(f"{config_file}: allow_dirs must be a list of directory paths")
    allowed = [base]
    for entry in raw:
        try:
            directory = (config_file.parent / entry).resolve()
            usable = directory.is_dir()
        except (OSError, RuntimeError) as exc:
            raise ConfigError(f"{config_file}: allow_dirs entry {entry!r} cannot be used: {exc}") from exc
        if not usable:
            raise ConfigError(f"{config_file}: allow_dirs entry {entry!r} ({directory}) is not a directory")
        allowed.append(directory)
    return tuple(allowed)


def _warn_placeholders(scripts: Iterable[ScriptDef], config_file: Path) -> None:
    for script in scripts:
        for group in sorted(g for g in script.groups if g.lower().endswith("dc=example,dc=com")):
            log.warning(
                "script %r uses the placeholder group %r from scripts.example.toml: nobody can run it until you "
                "put a real LDAP group DN in %s",
                script.id,
                group,
                config_file,
            )


def load_scripts(config_file: Path, *, warn: bool = True) -> dict[str, ScriptDef]:
    """Parse and validate the allowlist.  Any problem raises ConfigError (fail closed).

    The main file holds [settings], [groups], [defaults] and [profiles.<name>], and may name further files with
    include = [...] in [settings].  An included file holds [scripts.<id>] tables and, optionally, its own [defaults]
    for the scripts in it; it may NOT change [settings] or [groups].  That is what makes it safe to let administrators
    edit included files (from the web, say) while the trusted parts stay where only root can change them.
    """
    raw = _read_toml(config_file)
    settings = raw.get("settings", {})
    if not isinstance(settings, dict):
        raise ConfigError(f"{config_file}: [settings] must be a table")
    unknown_settings = set(settings) - _SETTINGS_KEYS
    if unknown_settings:
        hints = "".join(_misplaced(key, "[settings]") for key in sorted(unknown_settings))
        raise ConfigError(f"{config_file}: unknown keys in [settings]: {sorted(unknown_settings)}.{hints}")
    base = (config_file.parent / settings.get("scripts_dir", "scripts")).resolve()
    if not base.is_dir():
        raise ConfigError(f"scripts dir {base} does not exist")
    allowed = _allowed_dirs(settings, base, config_file)
    names = _group_names(raw, config_file)
    defaults = _inheritable(raw.get("defaults", {}), f"{config_file}: [defaults]")
    profiles = _profiles(raw, config_file)

    scripts: dict[str, ScriptDef] = {}
    came_from: dict[str, Path] = {}
    for source, entries, file_defaults in _all_entries(config_file, raw, settings, defaults):
        for script_id, entry in entries.items():
            if script_id in came_from:
                raise ConfigError(f"script {script_id!r} is defined twice: in {came_from[script_id]} and in {source}")
            merged = _with_inherited(script_id, entry, file_defaults, profiles)
            try:
                scripts[script_id] = _parse_entry(
                    script_id, merged, base, allowed, names, main_file=source == config_file
                )
            except ConfigError as exc:
                raise ConfigError(f"{source}: {exc}") from exc
            came_from[script_id] = source
    if not scripts:
        raise ConfigError(f"{config_file}: define at least one [scripts.<id>] table (here or in an included file)")
    if warn:
        _warn_placeholders(scripts.values(), config_file)
    return scripts


def _as_group_list(script_id: str, groups: object) -> list[str]:
    if not isinstance(groups, list) or not groups or not all(isinstance(g, str) and g for g in groups):
        raise _entry_error(
            script_id,
            "'groups' must be a non-empty list of LDAP group names or DNs (nobody is the safe default). Set it on "
            "the script, on its profile, or in [defaults].",
        )
    return groups


def _all_entries(
    config_file: Path, raw: dict[str, object], settings: dict[str, object], defaults: dict[str, object]
) -> list[tuple[Path, dict[str, object], dict[str, object]]]:
    """Every source of [scripts.<id>] tables: the main file first, then each included file, with its own defaults."""
    sources: list[tuple[Path, dict[str, object], dict[str, object]]] = []
    main = raw.get("scripts", {})
    if not isinstance(main, dict):
        raise ConfigError(f"{config_file}: [scripts] must be a table of [scripts.<id>] tables")
    sources.append((config_file, main, defaults))
    for path in _included_files(settings, config_file):
        included = _read_toml(path)
        unknown = set(included) - _INCLUDED_KEYS
        if unknown:
            raise ConfigError(
                f"{path}: an included file may only hold {sorted(_INCLUDED_KEYS)}, not {sorted(unknown)} "
                f"(those belong in {config_file.name})"
            )
        entries = included.get("scripts", {})
        if not isinstance(entries, dict):
            raise ConfigError(f"{path}: [scripts] must be a table of [scripts.<id>] tables")
        file_defaults = {**defaults, **_inheritable(included.get("defaults", {}), f"{path}: [defaults]")}
        sources.append((path, entries, file_defaults))
    return sources


def find_bash() -> str:
    bash = shutil.which("bash")
    if bash is None:
        raise ConfigError("bash not found in PATH")
    return bash


def _child_env(script: ScriptDef, username: str) -> dict[str, str]:
    # Deliberately NOT os.environ: it holds everything loaded from the env file (Django secret key, LDAP bind password).
    return {
        "PATH": _CHILD_PATH,
        "LANG": "C.UTF-8",
        "HOME": os.environ.get("HOME", "/"),
        "RUNNER_USER": username.replace("\0", ""),
        "RUNNER_SCRIPT": script.id,
    }


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    if proc.returncode is not None:  # already reaped: the pid could belong to someone else by now
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # new session => pgid == pid; takes grandchildren down too
    except ProcessLookupError:
        pass


def stream_script(
    script: ScriptDef,
    username: str,
    *,
    bash: str,
    max_output: int = MAX_OUTPUT_BYTES,
    recorder: RunRecorder | None = None,
    on_started: Callable[[int], None] | None = None,
) -> Generator[bytes]:
    """Run the script, yielding combined stdout/stderr as it appears, then a final status line.

    Everything is also written to `recorder` (if given) before it is offered to the viewer, so the record is complete
    whether or not anybody is still watching.
    """
    started = time.monotonic()
    log.info("start user=%r script=%s", username, script.id)
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell; the path comes from the validated allowlist
        [bash, str(script.path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=script.path.parent,
        env=_child_env(script, username),
        start_new_session=True,
        close_fds=True,
    )
    if proc.stdout is None:
        raise RuntimeError("stdout pipe missing")
    if on_started is not None:
        on_started(proc.pid)

    out_fd = proc.stdout.fileno()
    timed_out = threading.Event()

    def on_timeout() -> None:
        timed_out.set()
        _kill_group(proc)

    timer = threading.Timer(script.timeout, on_timeout)
    timer.daemon = True
    timer.start()

    sent = 0
    over_limit = False

    def take(chunk: bytes) -> bool:
        """Count and record a chunk.  False once the output cap is exceeded: the script is killed."""
        nonlocal sent, over_limit
        sent += len(chunk)
        if sent > max_output:
            over_limit = True
            _kill_group(proc)
            return False
        if recorder is not None:
            recorder.write(chunk)
        return True

    try:
        while chunk := os.read(out_fd, _CHUNK):  # returns as soon as any data is there: no buffering
            if not take(chunk):
                break
            yield chunk
    except GeneratorExit:
        # The viewer went away.  A WSGI server only notices that on its next write, so killing here would be
        # inconsistent (silent scripts survive, chatty ones die) and a half-finished sync is worse than an unwatched
        # one.  So: the script always runs to completion, and keeps being recorded for the "last run" view.  Reading on
        # also means it never blocks on a full pipe; the timeout (still armed) and the output cap still apply.
        log.warning("detached user=%r script=%s (client went away, run continues)", username, script.id)
        while chunk := _read_quietly(out_fd):
            if not take(chunk):
                break
        raise
    except BaseException:
        _kill_group(proc)  # something broke in here: never leave an unsupervised script behind
        raise
    finally:
        proc.stdout.close()
        rc = proc.wait()  # also waits out a script that closed its stdout but keeps working; the timer still applies
        timer.cancel()
        if timed_out.is_set():
            status = f"timed out after {script.timeout}s and was killed"
        elif over_limit:
            status = f"output limit of {max_output} bytes exceeded, killed"
        else:
            status = f"exit code {rc}"
        footer = f"\n[{status}]\n".encode()
        if recorder is not None:
            recorder.finish(status, rc, footer)  # also when the viewer is gone or something broke
        log.info(
            "finish user=%r script=%s status=%r duration=%.1fs", username, script.id, status, time.monotonic() - started
        )
    yield footer


def _read_quietly(fd: int) -> bytes:
    try:
        return os.read(fd, _CHUNK)
    except OSError:
        return b""


class RunStream:
    """Iterator over a run's output.

    Closing it (response finished or client gone) releases the script lock.  If the run is still going, close() first
    waits for the script to finish: it is never killed because the viewer left, only by its timeout.
    """

    def __init__(
        self,
        chunks: Generator[bytes],
        release: Callable[[], None],
        recorder: RunRecorder | None = None,
    ) -> None:
        self._chunks = chunks
        self._release = release
        self._recorder = recorder
        self.run_id = recorder.run_id if recorder is not None else None
        self._released = False

    def __iter__(self) -> RunStream:
        return self

    def __next__(self) -> bytes:
        return next(self._chunks)

    def close(self) -> None:
        try:
            if self._recorder is not None and inspect.getgeneratorstate(self._chunks) == inspect.GEN_CREATED:
                # Closed before the first byte was asked for: the script never ran, so do not leave "running" behind.
                self._recorder.finish("cancelled before it started", None)
            self._chunks.close()
        finally:
            if not self._released:
                self._released = True
                self._release()


class ScriptRunner:
    """The allowlist plus per-script run locks (one run of a given script at a time, per process)."""

    def __init__(
        self,
        scripts: dict[str, ScriptDef],
        bash: str | None = None,
        *,
        config_file: Path | None = None,
        store: RunStore | None = None,
        locks: ScriptLocks | None = None,
        on_thread_end: Callable[[], None] | None = None,
    ) -> None:
        self.scripts = scripts
        # called at the end of a detached run's thread (g2g: close the thread's database connection)
        self._on_thread_end = on_thread_end
        self.bash = bash or find_bash()
        self._config_file = config_file
        self.store = store
        # The "one run at a time" locks.  They are keyed by script id and live outside the allowlist, so a reload cannot
        # lose them: a script that is removed and added again while its old run is going is still locked.
        self.locks = locks if locks is not None else ScriptLocks()
        self.last_reload: tuple[list[str], list[str], list[str]] | None = None  # added, removed, changed
        self._reload_lock = threading.Lock()

    def reload(self) -> bool:  # noqa: D401
        """Re-read the allowlist file.  True if anything changed.

        A bad file raises ConfigError and the list in force stays exactly as it was.  Runs that are in progress are not
        touched: each keeps the definition it started with.
        """
        if self._config_file is None:
            raise ConfigError("this runner was not created from a file, there is nothing to reload")
        with self._reload_lock:
            new = load_scripts(self._config_file, warn=False)
            old = self.scripts
            if new == old:
                self.last_reload = ([], [], [])
                return False
            changed = sorted(sid for sid in new.keys() & old.keys() if new[sid] != old[sid])
            added = sorted(new.keys() - old.keys())
            self.last_reload = (added, sorted(old.keys() - new.keys()), changed)
            self.scripts = new  # one assignment: readers see the old list or the new one, never a mixture
            log.info(
                "scripts reloaded from %s: added=%s removed=%s changed=%s",
                self._config_file,
                added,
                sorted(old.keys() - new.keys()),
                changed,
            )
            _warn_placeholders((new[sid] for sid in added + changed), self._config_file)
            return True

    @property
    def all_groups(self) -> frozenset[str]:
        return frozenset(g for s in self.scripts.values() for g in s.groups)

    def visible_to(self, user_groups: Collection[str]) -> list[ScriptDef]:
        scripts = self.scripts  # one snapshot: a reload may swap the dict while we work
        allowed = (s for s in scripts.values() if s.allowed_for(user_groups))
        return sorted(allowed, key=lambda s: s.name.lower())

    def start(
        self, script_id: str, username: str, user_groups: Collection[str], record: dict[str, object] | None = None
    ) -> RunStream:
        """Authorize and begin a run.  Authorization lives here so no route can forget it.

        record: extra details for the store's begin() (g2g: the django user and the repo pair).
        """
        script = self.scripts.get(script_id)
        if script is None:
            raise UnknownScript(script_id)
        if not script.allowed_for(user_groups):
            log.warning("denied user=%r script=%s", username, script_id)
            raise NotAllowed(script_id)
        if script.allowed_by_local_group(user_groups):
            log.info("user=%r may run %s through a local django group, not through LDAP", username, script_id)
        # The lock comes first, before anything is recorded or started: only the one who holds it may run the script.
        try:
            held = self.locks.acquire(script_id, username)
        except Busy as busy:
            who = f"held by {busy.holder.user!r}" if busy.holder is not None else "holder unknown"
            log.info("busy user=%r script=%s (already running, %s)", username, script_id, who)
            raise
        except LockUnavailable as exc:
            log.error("cannot lock %s for user=%r, so it is not run: %s", script_id, username, exc)
            raise
        try:
            recorder = self._begin_record(script, username, record)

            def on_started(pid: int) -> None:
                held.note_child(pid, str(script.path))
                if recorder is not None and hasattr(recorder, "started"):
                    recorder.started(pid)  # g2g: the run record keeps the pid for the orphan check

            chunks = stream_script(script, username, bash=self.bash, recorder=recorder, on_started=on_started)
            return RunStream(chunks, held.release, recorder)
        except BaseException:
            held.release()  # nothing was started: do not leave the script locked
            raise

    def start_detached(
        self, script_id: str, username: str, user_groups: Collection[str], record: dict[str, object] | None = None
    ) -> str | None:
        """Start a run and let it finish on its own, recorded; returns the run id for the page that will show it.

        The browser is no longer what drives the script: a thread reads it to the end, so a run survives a closed tab,
        a reload, or the user walking away.  Authorisation, locking and recording are exactly as in start().
        """
        stream = self.start(script_id, username, user_groups, record)

        def drain() -> None:
            try:
                for _ in stream:
                    pass
            finally:
                try:
                    stream.close()  # releases the script's lock, whichever way the run ended
                finally:
                    if self._on_thread_end is not None:
                        self._on_thread_end()

        threading.Thread(target=drain, name=f"run-{script_id}", daemon=True).start()
        return stream.run_id

    def _begin_record(
        self, script: ScriptDef, username: str, record: dict[str, object] | None = None
    ) -> RunRecorder | None:
        if self.store is None:
            return None
        try:
            if record:
                return self.store.begin(script.id, username, **record)  # type: ignore[call-arg]
            return self.store.begin(script.id, username)
        except (OSError, ValueError) as exc:  # a broken runs directory must not stop the script from running
            log.error("cannot record the run of %s: %s", script.id, exc)
            return None
