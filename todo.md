# Todo

Open items after the review and fix batches 1–5 (commits `fcb0469`..`2308629`).
The items from the former `TODO` file are listed under "Features".

## Before deploying to the real server

- [x] Back up the database. Migration `0013` drops the `aGit2Git_tag` table.
- [x] Run `migrate` (done 2026-10-09 on production, 0012 found no problem rows).
- [x] Set `LDAP_TLS_VERIFY=True` in `.env` (done 2026-10-09; login works with full certificate check,
      tested on a fresh stack with new volumes).
- [x] Do one real LDAP login with a user account (done 2026-10-09; also works with the UPN or mail address).
- [x] Set `DJANGO_HTTPS=True` (done 2026-10-09 on production).
- [x] `DJANGO_SECURE_HSTS_SECONDS` on production (start small, e.g. 3600, raise later) (2026-10-10).
      No effect on the docker test stack: only read with `DJANGO_HTTPS`, only sent over https.
- [ ] If the site is reached on an address nginx doesn't forward as-is, set `DJANGO_CSRF_TRUSTED_ORIGINS`.

## Secrets and configuration

- [x] `.env.example` holds dummy values only; no `.env` file was ever committed (checked 2026-10-09).
- [x] `env-example` is committed as the template (placeholders only, checked 2026-10-10).
- [x] One real settings file, `pSwai/.env`; docker uses a copy next to `compose.yaml`
      (`make docker_test`) (2026-10-10).
- [x] Unused keys removed from `pSwai/.env` (mail settings from another project), and dead code:
      unused templates, the `file` and `mail_admins` log handlers, `do_paging_with_search_filters`,
      unused parameters, `LOGIN/LOGOUT_REDIRECT_URL` (2026-10-10). Unknown handler names in an
      older `.env` are ignored with a warning.
- [x] The `if DJANGO_DEBUG:` block (not valid dotenv syntax) is gone from the `.env` files (2026-10-09).
- [x] Logging: console (stderr) in docker for development, syslog on the server without docker
      (decided 2026-10-10). For syslog from docker use the logging driver (`driver: journald`),
      not a `/dev/log` mount (that breaks silently when the host's log service restarts).
- [x] `ENVIRONMENT` removed: nothing read it; more logging while developing is `DJANGO_LOG_LEVEL` /
      `LDAP_LOG_LEVEL=DEBUG` (2026-10-10).

## Behaviour to decide

- [x] **Boolean filters**: exact match on yes/no, y/n, true/false, 1/0, on/off (done 2026-10-09).
- [x] **Sorting**: header links sort one column asc/desc/off, "Cs" clears (done 2026-10-09).
- [x] **Clear filters**: the "Cf" button clears the filters of the page (done 2026-10-09).
- [x] **Date format**: `ymd-His` (e.g. 261010-093015) via `pSwai/pSwai/formats/en/formats.py`
      and `FORMAT_MODULE_PATH` (done 2026-10-10).
- [x] **Login permissions**: view for everyone logged in; add/change/delete per django permission
      (local groups); `LDAP_ADMIN` members are superusers; AD groups no longer mirrored (2026-10-10).
- [ ] Set `LDAP_ADMIN` in `pSwai/.env` (local and production) to the AD admin group. Until then only
      local superusers have all rights; a user that is superuser only locally loses it at login
      once `LDAP_ADMIN` is set and they are not in that group.
- [ ] Optional cleanup: the AD groups mirrored before (e.g. 48 for one user) are still django groups with
      stale memberships; they carry no permissions, so they can be deleted in the admin.
- [x] **Two login paths**: only `/login/` logs users in; the session ends when the browser
      closes (done 2026-10-09).

## Features (from the former `TODO` file)

- [ ] Collapsible left menu per app (`aGit2Git`, `aComponents`), open for the app you are working in.
- [ ] Bulk actions: the selection checkboxes exist (`_D` column), but nothing acts on them.
- [ ] Rework the models to add a namespace level: server → namespace → url (repo).
- [ ] Validators for some models (external server, external url),
      e.g. that a repo's url belongs to its server.
- [ ] `Run`: trigger a manual copy action with parameters (from the README).

## Cleanup

- [x] `DJANGO_LOGGERS_HANDLERS_APP` only builds loggers for the project apps; the `django.*` apps
      log through the `django` logger (done 2026-10-09).
- [ ] Clock skew on the NFS share makes `make` warn and rebuild more often than needed.

## Larger refactor (optional)

- [ ] `appAutoGui` largely reimplements Django's generic views (`ListView`, `CreateView`,
      `UpdateView`, `DeleteView`) using path-string parsing (`_split_path`,
      `full_path.replace(...)`). Moving to class-based views, possibly with `django-filter` /
      `django-tables2`, would remove most of that code and give sorting, filtering and bulk
      actions without custom code. The current tests (`make test`) are a safety net for this.
