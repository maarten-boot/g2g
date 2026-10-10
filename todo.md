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
- [ ] Optional: `DJANGO_SECURE_HSTS_SECONDS` once https is known to stay (start small, e.g. 3600).
- [ ] If the site is reached on an address nginx doesn't forward as-is, set `DJANGO_CSRF_TRUSTED_ORIGINS`.

## Secrets and configuration

- [x] `.env.example` holds dummy values only; no `.env` file was ever committed (checked 2026-10-09).
- [ ] Optional: commit `.env.example` as the template for new setups (change `.gitignore` from `.env*`
      to `.env` + `!.env.example`). Check its content first: it gets published with the repo.
- [ ] Two `.env` files hold real secrets: `pSwai/.env` (read by local `manage.py` runs and the systemd
      deployment, found first by `find_dotenv()`) and the root `.env` (read by docker compose).
      Keeping them in sync is manual; consider one file, or compose `env_file: pSwai/.env`.
- [x] The `if DJANGO_DEBUG:` block (not valid dotenv syntax) is gone from the `.env` files (2026-10-09).
- [ ] `.env` logs to `syslog`. That works on the systemd host, but compose overrides it with
      `console` because the container has no `/dev/log`. Check that this is what you want.
- [ ] `ENVIRONMENT` is required (production: `PROD`) but nothing reads it yet: use it or drop it.

## Behaviour to decide

- [x] **Boolean filters**: exact match on yes/no, y/n, true/false, 1/0, on/off (done 2026-10-09).
- [x] **Sorting**: header links sort one column asc/desc/off, "Cs" clears (done 2026-10-09).
- [x] **Clear filters**: the "Cf" button clears the filters of the page (done 2026-10-09).
- [x] **Date format**: `ymd-His` (e.g. 261010-093015) via `pSwai/pSwai/formats/en/formats.py`
      and `FORMAT_MODULE_PATH` (done 2026-10-10).
- [ ] **Login permissions**: any logged-in user can add, edit and delete everything.
      Decide whether to require staff status or per-model permissions.
- [x] **Two login paths**: only `/login/` logs users in; the session ends when the browser
      closes (done 2026-10-09).

## Features (from the former `TODO` file)

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
