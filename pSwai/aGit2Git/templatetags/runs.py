from django import template

from aGit2Git.models import RepoPair, Run, Script
from aGit2Git.run_access import may_run, pair_script_id
from aGit2Git.run_service import get_runner

register = template.Library()

LAST_RUNS = 5


@register.inclusion_tag("aGit2Git/run-panel.html", takes_context=True)
def run_panel(context, obj):
    """The Run part of a Script's or a RepoPair's page: the button, or why there is none, and the last runs.
    Nothing for other pages, for unsaved items, or when Run is off."""
    runner = get_runner()
    if runner is None or obj is None or obj.pk is None:
        return {"show": False}
    if isinstance(obj, Script):
        if not obj.allowlist_id:
            return {"show": False}
        script_id, reason = obj.allowlist_id, None
        action = f"/aGit2Git/script/run/{obj.pk}"
        runs = Run.objects.filter(script_id=obj.allowlist_id)
    elif isinstance(obj, RepoPair):
        script_id, reason = pair_script_id(obj)
        action = f"/aGit2Git/repopair/run/{obj.pk}"
        runs = Run.objects.filter(repo_pair=obj)
    else:
        return {"show": False}

    if script_id is not None and script_id not in runner.scripts:
        reason = f"the allowlist id {script_id} is not in the allowlist"
    allowed = reason is None and may_run(context["request"], runner, script_id) is not None
    if reason is None and not allowed:
        reason = "you may not run its script"
    return {
        "show": True,
        "script_id": script_id,
        "reason": reason,
        "action": action,
        "runs": runs[:LAST_RUNS] if allowed else [],  # seeing runs needs the right to run the script
        "csrf_token": context.get("csrf_token"),
    }
