"""Who may run which allowlisted script (docs/run-design.md §4): the django side of the runner.

A user's "groups" for the allowlist are their LDAP group DNs (normalized like the allowlist's) plus "local:<name>" for
each of their django groups. may_run() is the one place that decides; every Run view calls it.
"""

from collections.abc import Iterable
from typing import Any

from appLogin.signals import LDAP_GROUP_DNS

from aGit2Git.runner.runner import LOCAL_PREFIX, ScriptDef, ScriptRunner, normalize_dn


def user_groups(user: Any, ldap_group_dns: Iterable[str]) -> frozenset[str]:
    """The groups to check a user against the allowlist: their LDAP group DNs and their django groups."""
    local = {f"{LOCAL_PREFIX}{name}" for name in user.groups.values_list("name", flat=True)} if user.pk else set()
    return frozenset({normalize_dn(dn) for dn in ldap_group_dns} | local)


def request_groups(request: Any) -> frozenset[str]:
    """The groups of the logged-in user: LDAP DNs from the session (read at login) and their django groups."""
    return user_groups(request.user, request.session.get(LDAP_GROUP_DNS, []))


def may_run(request: Any, runner: ScriptRunner, script_id: str) -> ScriptDef | None:
    """The script when this user may run it (and so view and download its runs, Flask spec §10), else None.
    A script that is not (or no longer) in the allowlist: None, fail closed."""
    script = runner.scripts.get(script_id)
    if script is None or not request.user.is_authenticated:
        return None
    return script if script.allowed_for(request_groups(request)) else None


def pair_script_id(pair: Any) -> tuple[str | None, str | None]:
    """The allowlist id a repo pair runs (through its copy type's script), or None and the reason it cannot run.

    A pair is runnable when its copy type is manual and has a script with an allowlist id (docs/run-design.md §6).
    Scripts take no arguments, so the script itself is per pair; pairs sharing a copy type run the same script."""
    copy_type = pair.copyType
    if copy_type is None:
        return None, "this repo pair has no copy type"
    if not copy_type.manual:
        return None, f"its copy type {copy_type.name} is not manual"
    if copy_type.script is None:
        return None, f"its copy type {copy_type.name} has no script"
    if not copy_type.script.allowlist_id:
        return None, f"the script {copy_type.script.name} has no allowlist id"
    return copy_type.script.allowlist_id, None
