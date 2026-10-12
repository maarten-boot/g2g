# Run: starting copy scripts from g2g — design

Status: **proposal**, decisions of 2026-10-11 included. Builds on [spec.md](spec.md) §4 (Run) and on the separate
specification of the Flask tool `g2g-scripts-manual` (`auto-sync-g2g/SPECIFICATION.md`, "the Flask spec" below),
whose Part 1 (requirements) this design follows. Part 2 of the Flask spec (its implementation) is used where it
can be reused; everything Flask-specific is replaced by what g2g already has.

## 1. Decisions

| Topic | Decision |
| --- | --- |
| Place | In the `aGit2Git` app and its menu section. |
| Link to the data | A **RepoPair** is the basic link: RepoPair → CopyType → Script → allowlist entry. A **Run** button on a repo pair, when enabled (§6). |
| Allowlist | A TOML file, root-owned and read-only for the service, as in the Flask spec §7. **Not in the database.** |
| Code | The framework-free modules of the Flask tool (`runner.py`, `locks.py`, `runs.py`) are **copied into g2g** and adapted; no shared package. |
| Run records | **In the database**, kept for **3 months**; output in a file per run. |
| Execution | A **thread in the web process**, as in the Flask version. A separate runner service may follow later. |
| Arguments | **None**, as in the Flask tool. Every run executes a fixed command line. |

## 2. Requirements taken over from the Flask spec (Part 1)

All MUST rules of Part 1 apply unchanged; the ones that shape this design:

- **Only declared scripts run** (§2.3, §14.1): a user picks an item in the UI; it only ever selects an allowlist entry.
  Nothing a user types reaches a command line, an environment variable or a file path.
- **Authorisation per script, decided in one place** (§3, §6): one function `may_run(user, script_id)`.
- **Execution constraints** (§8): no shell, scrubbed environment (`PATH`, `LANG`, `HOME`, `RUNNER_USER`,
  `RUNNER_SCRIPT` only — never the server's environment with the Django secret key and the LDAP bind password),
  no stdin, own process group, timeout kills the group, output cap (10 MiB) kills the script.
- **A started run finishes** (§3, §8): closing the browser does not stop it; only the timeout does.
- **One run of a script at a time, across processes** (§11), released by the OS on a crash, with the orphan check.
- **Fail closed** (§3): a lock that cannot be taken means no run; a group that cannot be checked means no right.
- **Viewing and downloading a run needs the right to run the script** (§10); output is never rendered as markup.
- **An invalid allowlist leaves the previous one in force** (§9).
- The acceptance list of the Flask spec **§16** is the acceptance test of this implementation.

## 3. What is copied, what g2g already has, what is new

**Copied from the Flask tool** (standard library only, with their tests converted to Django tests):

| Module | Holds | Adaptation |
| --- | --- | --- |
| `runner.py` | Allowlist parsing and validation (precedence, groups replaced not merged, symlink checks, includes, unknown keys are errors), reload with fallback, execution (`Popen`, scrubbed env, process group, timeout, output cap) | Group names: AD DNs and `local:<django group>` instead of the manual-groups file |
| `locks.py` | Per-script `flock` with the holder in the lock file (the §21 starvation trap solved), orphan check via the pid | None expected |
| `runs.py` | The last-run record on disk | **Replaced** by the `Run` model (§5); the file-writing part is kept for the output file |

The Flask tool's `groups.py` (background group lookups) is **not needed**: Active Directory returns all groups of a
user with the login itself (`memberOf`, one query), so a login does not get slower with more scripts (Flask spec §6,
§15). `app.py` and `diagnose.py` are Flask/ldap3-specific and are rebuilt.

**Already in g2g**: LDAP login with TLS verification and empty passwords refused (django-auth-ldap), the login gate
(`LDAP_ACTIVE`), CSRF protection, secure session cookies, a new session at every login, server-side sessions,
logging without passwords, the admin.

**New in g2g**: the `Run` model, views and templates, the allowlist loader in Django settings, the `may_run` check,
the Run button, the live view, a management command for the diagnosis (`check_runner`) and one for the 3-month
clean-up (`purge_runs`).

## 4. Authorisation

- The allowlist names groups per script (or via defaults/profiles), as in the Flask spec §7:
  - an **AD group DN** (or a short name from `[groups]`), checked against the user's AD groups;
  - **`local:<name>`**, a Django group managed in the admin (by superusers). This replaces the Flask tool's manual-groups
    file: it exists for the same reason (adding someone to an AD group can take days), is clearly distinguishable by
    its prefix, and a run allowed by it is logged as such.
- The user's AD group DNs are read at login (django-auth-ldap) and kept in the **server-side session**, never taken
  from the browser (Flask spec §14.6). They are fixed for the session; the next login picks up changes.
- DNs are compared as **normalized strings** (`normalize_dn`: lower case, no spaces around commas), on both sides:
  AD returns `CN=...,OU=...` while the allowlist may say `cn=..., ou=...`. (The Flask tool asked the directory per
  group, so spelling did not matter there.) `local:` names are compared as written: django group names are
  case-sensitive.
- `may_run` is the only place that decides; the views for starting, viewing and downloading a run all call it.
- Superusers (`LDAP_ADMIN`) do **not** automatically get every script: the allowlist decides who may run what, as in the
  Flask spec. (Open question §9.3.)

## 5. Data model

```text
Script (existing, aGit2Git)
    + allowlist_id   CharField, optional, unique: the [scripts.<id>] it starts; validated against the allowlist

Run (new, aGit2Git)
    id               UUID (also names the output file)
    script_id        the allowlist id that ran (kept even if the Script record changes)
    repo_pair        FK RepoPair, optional, SET_NULL: the pair the run was started from
    started_by       FK User, PROTECT-free (SET_NULL) + the username as text
    started_at, finished_at
    status           running | succeeded | failed | timed_out | output_capped | interrupted | refused
    exit_code        optional
    pid              optional, for the orphan check after a restart
    output_bytes     size of the output file
```

- **Output** is written to `RUNS_DIR/<run id>.log` while the script runs (private to the service user, Flask spec
  §14.8). The file name comes from the UUID, never from user input (Flask spec §14.2).
- **History of 3 months**: `manage.py purge_runs` deletes runs older than 3 months together with their output files;
  run daily (systemd timer or cron), and once at the start of every run, so it also works without a timer. The
  limit is a setting (`RUN_HISTORY_DAYS`, default 90).
- **Interrupted runs**: at startup, runs still `running` whose process is gone are marked `interrupted`
  (Flask spec §10).
- Storage is bounded by the number of runs in 3 months × the 10 MiB cap.

## 6. The Run button on a repo pair

- A repo pair shows **Run** when it is **enabled** for runs:
  its CopyType is `manual`, the CopyType has a Script, that Script has an `allowlist_id` that exists in the
  current allowlist, **and** `may_run` allows the user. Otherwise there is no button (and a POST is refused).
- Because scripts take **no arguments**, the script cannot be told which pair it runs for. For now that means:
  **one script per repo pair** (or per group of pairs that are copied together), declared in the allowlist.
  See open question §9.1.
- The pair's page shows the last runs of its script, with links to their output.

## 7. Pages and requests

| Method and path | Purpose |
| --- | --- |
| `POST /aGit2Git/repopair/run/<pair id>` | Start the pair's script; 303 to the run page; 403/404 when not allowed or unknown |
| `POST /aGit2Git/script/run/<script id>` | The same from a Script (all scripts in the allowlist) |
| `GET /aGit2Git/run/` | The run list (filter, sort, as the other lists); only runs the user may see |
| `GET /aGit2Git/run/<run id>` | One run, following it live while it runs |
| `GET /aGit2Git/run/<run id>/output?offset=N` | New output from byte N, for the live view (polling, no WebSocket) |
| `GET /aGit2Git/run/<run id>/download` | The whole output as a plain-text attachment; 409 while running |
| `POST /aGit2Git/run/reload` | Re-read the allowlist (previous one stays on errors); rate-limited |

All state-changing requests are POST with CSRF. A refused start (the script is already running) is shown on the run
page of the running run: "started by X at HH:MM".

## 8. Execution in the web process

- The start view takes the script's lock, creates the `Run` row, starts the script and a thread that reads its output
  into the output file, then returns the redirect. The thread finishes the row and releases the lock.
- gunicorn runs several processes; `flock` works across them, so one run per script holds (Flask spec §11).
- A deploy restarts the web processes: a running script continues (own process group) but its output is no longer
  read; the run is marked `interrupted` (§5). Deploy when nothing runs, until a separate runner service exists.
- **Docker**: the scripts run in the `web` container, so the scripts, `git` and any credentials they need must be
  mounted there read-only. On the server without docker this is not an issue.

## 9. Open questions

1. **Which pair a script runs for.** With no arguments a script needs to be per pair. Later options: declared,
   validated arguments per script (Flask spec §13 allows that, never free text), or `RUNNER_*` environment variables
   with the pair's data — but those come from the database, which users with change rights can edit, so they would
   be user input reaching the script (Flask spec §2.3). Needs a decision before more than a few pairs are runnable.
2. **Who may see a run's output.** The Flask spec: everybody who may run the script. Alternative: also everybody who
   may view the repo pair.
3. **Superusers and scripts.** Should `LDAP_ADMIN` members implicitly be allowed to run every script, or only what the
   allowlist grants (as proposed)?
4. **A separate runner service** (later): the web process would only queue runs, and a separate service with the
   script privileges would execute them. More secure and deploy-safe; more moving parts.

## 10. Steps

1. **Done (2026-10-11).** `runner.py`, `locks.py` and (until step 2) `runs.py` copied to `pSwai/aGit2Git/runner/`
   (no Django imports there); manual groups replaced by `local:`; DN normalization. Their 266 tests run with pytest
   from `tests/runner/` (`make test` runs them and the Django tests). Settings `RUNNER_ALLOWLIST`, `RUNNER_RUNS_DIR`,
   `RUN_HISTORY_DAYS` (both paths empty: Run off); example `runner/scripts.example.toml`; `manage.py check_runner
   [--user NAME]`.
2. **Done (2026-10-11).** `Run` model and `Script.allowlist_id` (migration `aGit2Git 0015`); a database-backed
   store (`aGit2Git/run_service.py`, output in `RUNNER_RUNS_DIR/<run id>.log`, mode 600); the start view (303 to the
   run page, a busy script sends you to the run that is going), the run page following the output live (polling,
   streaming UTF-8 decode, no-JS refresh), the output endpoint and the download (409 while running); `may_run` with
   the LDAP group DNs kept in the session at login; a Run panel (button and last runs) on a Script's page; Run in
   the admin, read only. Docker: `./runner` mounted read-only at `/runner`, a `runs` volume; Run is on in docker only
   with `DOCKER_RUNNER_ALLOWLIST` set.
3. **Done (2026-10-11).** (`may_run` came with step 2.) The Run button on a repo pair (`POST
   /aGit2Git/repopair/run/<pair id>`, its copy type's script, the run records the pair), or the reason it cannot run
   (no copy type, not manual, no script, no allowlist id, not in the allowlist, not allowed); the pair's last runs on
   its page; the run list `/aGit2Git/run/` with only the runs the user may see, as **Runs** in the menu; the run pages
   have the menu (`page_context`).
4. **Done (2026-10-11).** `manage.py purge_runs [--dry-run]` deletes runs older than `RUN_HISTORY_DAYS` with their
   output (never a running one), and every start of a run purges up to 100; runs that a restart cut short become
   `interrupted` when a process starts Run (unless the script's lock is held, or its orphan still runs; always after
   the longest timeout); **Reload the allowlist** on the Runs page (rate-limited per session, shows added / removed /
   changed; an invalid file keeps the previous one, the reason only for staff). The reload reaches every web
   process through a generation number in the shared cache; a process that starts with an invalid allowlist has no
   Run (nothing to keep).
5. The Flask spec §16 checklist as acceptance tests; then a trial with one real script.
