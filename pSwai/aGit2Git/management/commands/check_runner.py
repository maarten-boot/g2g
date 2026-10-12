"""Check the Run configuration without the browser (docs/run-design.md, Flask spec §12).

Each step says whether it is fine and, when not, what to change. With --user, also which scripts that user may run
(their LDAP groups are read with the service account, as at login; nothing is changed).
"""

import os
import stat
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError

from aGit2Git.run_access import user_groups
from aGit2Git.runner.runner import LOCAL_PREFIX, ConfigError, find_bash, load_scripts


class Command(BaseCommand):
    help = "Check the Run configuration: allowlist, bash, runs directory, local groups; optionally a user's scripts."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="also show which scripts this user may run (login name, UPN or mail)")

    def handle(self, *args, **options):
        self.failed = False
        allowlist, runs_dir = settings.RUNNER_ALLOWLIST, settings.RUNNER_RUNS_DIR
        if not allowlist and not runs_dir:
            self.stdout.write("Run is switched off (RUNNER_ALLOWLIST and RUNNER_RUNS_DIR are empty).")
            return
        if not allowlist or not runs_dir:
            self.bad("set both RUNNER_ALLOWLIST and RUNNER_RUNS_DIR in pSwai/.env, or neither (Run off)")
            raise CommandError("the Run configuration has problems, see above")

        scripts = self.check_allowlist(Path(allowlist))
        self.check_bash()
        self.check_runs_dir(Path(runs_dir))
        if scripts:
            self.check_local_groups(scripts)
            if options["user"]:
                self.check_user(options["user"], scripts)
        if self.failed:
            raise CommandError("the Run configuration has problems, see above")

    def ok(self, message: str) -> None:
        self.stdout.write(f"  ok    {message}")

    def warn(self, message: str) -> None:
        self.stdout.write(f"  warn  {message}")

    def bad(self, message: str) -> None:
        self.failed = True
        self.stdout.write(f"  FAIL  {message}")

    def check_allowlist(self, path: Path) -> dict:
        try:
            scripts = load_scripts(path)
        except ConfigError as e:
            self.bad(f"allowlist {path}: {e}")
            return {}
        self.ok(f"allowlist {path}: {len(scripts)} scripts ({', '.join(sorted(scripts))})")
        # Flask spec §14.10: the allowlist and the scripts must not be writable by the service user
        for writable in [p for p in [path, *(s.path for s in scripts.values())] if os.access(p, os.W_OK)]:
            self.warn(f"{writable} is writable by this user; it should be root-owned and read-only for the service")
        return scripts

    def check_bash(self) -> None:
        try:
            self.ok(f"bash: {find_bash()}")
        except ConfigError as e:
            self.bad(str(e))

    def check_runs_dir(self, path: Path) -> None:
        if not path.is_dir():
            self.bad(f"runs directory {path} does not exist: create it, owned by the service user, mode 700")
            return
        if not os.access(path, os.W_OK):
            self.bad(f"runs directory {path} is not writable by this user")
            return
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            self.warn(f"runs directory {path} has mode {mode:o}: run output should be private to the service (700)")
        else:
            self.ok(f"runs directory {path}")

    def check_local_groups(self, scripts: dict) -> None:
        wanted = {g[len(LOCAL_PREFIX) :] for s in scripts.values() for g in s.groups if g.startswith(LOCAL_PREFIX)}
        existing = set(Group.objects.filter(name__in=wanted).values_list("name", flat=True))
        for name in sorted(wanted - existing):
            self.warn(f"local group {name!r} does not exist in django: it lets nobody in until it is created")
        if wanted and wanted <= existing:
            self.ok(f"local groups exist: {', '.join(sorted(wanted))}")

    def check_user(self, login_name: str, scripts: dict) -> None:
        from appLogin.backends import LDAPBackend
        from django_auth_ldap.backend import _LDAPUser

        backend = LDAPBackend()
        username = backend.to_sam_account_name(login_name)
        ldap_user = _LDAPUser(backend, username=username)
        if ldap_user.dn is None:
            self.bad(f"user {login_name!r} ({username}) not found in LDAP")
            return
        user = User.objects.filter(username=username).first() or User(username=username)
        groups = user_groups(user, ldap_user.group_dns)
        allowed = sorted(s.id for s in scripts.values() if s.allowed_for(groups))
        self.ok(f"user {username}: {ldap_user.dn}, {len(groups)} groups")
        if allowed:
            self.ok(f"user {username} may run: {', '.join(allowed)}")
        else:
            self.warn(f"user {username} may run none of the scripts")
