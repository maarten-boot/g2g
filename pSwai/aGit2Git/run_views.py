"""Run views: start a script, follow it live, download its output (docs/run-design.md §7)."""

import logging
import time

from appAutoGui.genericViews import page_context
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from aGit2Git.models import RepoPair, Run, Script
from aGit2Git.run_access import may_run, pair_script_id, request_groups
from aGit2Git.run_service import get_runner, output_path, purge_old_runs, reload_allowlist
from aGit2Git.runner.locks import Busy, LockUnavailable
from aGit2Git.runner.runner import ConfigError, NotAllowed, UnknownScript

log = logging.getLogger(__name__)

TAIL_BYTES = 1024 * 1024  # the run page shows the last 1 MiB; the download has all of it (Flask spec §10)
CHUNK_BYTES = 64 * 1024  # what one poll of the live view returns at most


def _unavailable(request, message: str, status: int = 503) -> HttpResponse:
    return render(request, "aGit2Git/run-message.html", page_context(request) | {"message": message}, status=status)


@login_required
@require_POST
def start_script(request, pk):
    """Start the script of a Script record; then the run's page."""
    runner = get_runner()
    if runner is None:
        return _unavailable(request, "Running scripts is not available (Run is off or its allowlist cannot be read).")
    script = get_object_or_404(Script, pk=pk)
    if not script.allowlist_id:
        raise Http404("this script has no allowlist id")
    return _start(request, runner, script.allowlist_id, repo_pair=None)


@login_required
@require_POST
def start_pair(request, pk):
    """Start the script of a repo pair (its copy type's script); then the run's page."""
    runner = get_runner()
    if runner is None:
        return _unavailable(request, "Running scripts is not available (Run is off or its allowlist cannot be read).")
    pair = get_object_or_404(RepoPair.objects.select_related("copyType__script"), pk=pk)
    script_id, reason = pair_script_id(pair)
    if script_id is None:
        return _unavailable(request, f"This repo pair cannot be run: {reason}.", 409)
    return _start(request, runner, script_id, repo_pair=pair)


PURGE_PER_START = 100  # every start also deletes a few runs past the history limit, so no timer is needed


def _start(request, runner, script_id: str, repo_pair):
    try:
        purge_old_runs(limit=PURGE_PER_START)
    except Exception:  # noqa: BLE001 - cleaning up must never stop a run
        log.exception("purging old runs failed")
    try:
        run_id = runner.start_detached(
            script_id,
            request.user.get_username(),
            request_groups(request),
            record={"user": request.user, "repo_pair": repo_pair},
        )
    except UnknownScript:
        raise Http404(f"{script_id} is not in the allowlist") from None
    except NotAllowed:
        return HttpResponseForbidden("You may not run this script.")
    except Busy:
        # not an error page: the run that is going (Flask spec §8)
        current = Run.objects.filter(script_id=script_id, status=Run.RUNNING).first()
        if current is not None:
            return redirect(f"/aGit2Git/run/{current.id}?busy=1")
        return _unavailable(request, "This script is already running; try again when that run has finished.", 409)
    except LockUnavailable:
        return _unavailable(request, "The script could not be started (its lock could not be taken); see the log.")
    if run_id is None:
        return _unavailable(request, "The script was started, but its output could not be recorded; see the log.", 500)
    response = redirect(f"/aGit2Git/run/{run_id}")
    response.status_code = 303  # see other: the run's page, after the POST that started it
    return response


def _visible_run(request, run_id) -> Run:
    """The run, if this user may see it: the same right as running its script (Flask spec §10)."""
    run = get_object_or_404(Run, pk=run_id)
    runner = get_runner()
    if runner is None or may_run(request, runner, run.script_id) is None:
        raise Http404("no such run")  # the same answer for "not allowed": runs of other scripts stay invisible
    return run


def _read_tail(path) -> tuple[bytes, int]:
    """The last TAIL_BYTES of a run's output, and its whole size; nothing when the file is missing."""
    if not path.exists():
        return b"", 0
    with open(path, "rb") as handle:
        size = handle.seek(0, 2)
        handle.seek(max(0, size - TAIL_BYTES))
        return handle.read(), size


RUNS_PER_PAGE = 50
RELOAD_EVERY_SECONDS = 3  # a reload at most once every 3 s per session (Flask spec §9, §19)


@login_required
@require_POST
def reload_view(request):
    """Re-read the allowlist (in every process); an invalid file leaves the previous one in force (Flask spec §9)."""
    runner = get_runner()
    if runner is None:
        return _unavailable(request, "Running scripts is not available (Run is off or its allowlist cannot be read).")
    last = request.session.get("runner_reload_at", 0)
    if time.time() - last < RELOAD_EVERY_SECONDS:
        messages.warning(request, "The allowlist was reloaded a moment ago; try again in a few seconds.")
        return redirect("/aGit2Git/run/")
    request.session["runner_reload_at"] = time.time()
    try:
        added, removed, changed = reload_allowlist(runner)
    except ConfigError as exc:
        log.error("reload by %s: the allowlist is invalid, the previous one stays in force: %s", request.user, exc)
        message = "The allowlist could not be reloaded; the previous one stays in force."
        if (
            request.user.is_staff
        ):  # the reason is for administrators (Flask spec §3, "the user is not the administrator")
            message += f" Reason: {str(exc)[:2000]}"
        messages.error(request, message)
        return redirect("/aGit2Git/run/")
    log.info("reload by %s: added=%s removed=%s changed=%s", request.user, added, removed, changed)
    if added or removed or changed:
        parts = [
            f"{label}: {', '.join(ids)}"
            for label, ids in (("added", added), ("removed", removed), ("changed", changed))
            if ids
        ]
        messages.success(request, "The allowlist was reloaded; " + "; ".join(parts) + ".")
    else:
        messages.info(request, "The allowlist was reloaded; nothing changed.")
    return redirect("/aGit2Git/run/")


@login_required
def run_list(request):
    """The runs of the scripts this user may run (the same right as viewing a run), newest first."""
    runner = get_runner()
    if runner is None:
        return _unavailable(request, "Running scripts is not available (Run is off or its allowlist cannot be read).")
    allowed = [script_id for script_id in runner.scripts if may_run(request, runner, script_id) is not None]
    runs = Run.objects.filter(script_id__in=allowed).select_related("repo_pair")
    page = Paginator(runs, RUNS_PER_PAGE).get_page(request.GET.get("page"))
    return render(
        request, "aGit2Git/run-list.html", page_context(request) | {"page_obj": page, "runs": page.object_list}
    )


@login_required
def run_page(request, run_id):
    run = _visible_run(request, run_id)
    tail, size = _read_tail(output_path(run))
    return render(
        request,
        "aGit2Git/run.html",
        page_context(request)
        | {
            "run": run,
            "output": tail.decode("utf-8", errors="replace"),  # rendered as text, never as markup
            "offset": size,
            "truncated": size > len(tail),
            "busy": "busy" in request.GET,
        },
    )


@login_required
def run_output(request, run_id):
    """Output from byte `offset` on, for the live view; the status and the next offset in headers."""
    run = _visible_run(request, run_id)
    try:
        offset = max(0, int(request.GET.get("offset", "0")))
    except ValueError:
        offset = 0
    path = output_path(run)
    data = b""
    if path.exists():
        with open(path, "rb") as handle:
            handle.seek(offset)
            data = handle.read(CHUNK_BYTES)
    response = HttpResponse(data, content_type="text/plain; charset=utf-8")
    response["X-Run-Status"] = run.status
    response["X-Next-Offset"] = str(offset + len(data))
    response["Cache-Control"] = "no-store"
    return response


@login_required
def run_download(request, run_id):
    run = _visible_run(request, run_id)
    if run.running:
        return HttpResponse("The run has not finished yet.", status=409, content_type="text/plain")
    path = output_path(run)
    if not path.exists():
        raise Http404("the output of this run is not available")
    name = f"{run.script_id}-{run.started_at:%Y%m%d-%H%M%S}.log"
    return FileResponse(open(path, "rb"), as_attachment=True, filename=name, content_type="text/plain; charset=utf-8")
