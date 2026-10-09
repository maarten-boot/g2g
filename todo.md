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

- [ ] `.env.example` is identical to `.env` and holds real values (Postgres password,
      Django secret key, LDAP bind password). Replace them with placeholders and rotate
      the secrets if the file was ever shared. Then change `.gitignore` from `.env*` to
      `.env` + `!.env.example` so the example can be committed.
- [ ] Two different `.env` files exist: local `manage.py` runs read `pSwai/.env`
      (found first by `find_dotenv()`), compose reads the root `.env`. Keep one.
- [ ] The root `.env` contains an `if DJANGO_DEBUG:` block. That isn't valid dotenv
      syntax, so those lines are ignored ("Invalid line" warnings).
- [ ] `.env` logs to `syslog`. That works on the systemd host, but compose overrides it with
      `console` because the container has no `/dev/log`. Check that this is what you want.
- [ ] `ENVIRONMENT` is required (production: `PROD`) but nothing reads it yet: use it or drop it.

## Behaviour to decide

- [x] **Boolean filters**: exact match on yes/no, y/n, true/false, 1/0, on/off (done 2026-10-09).
- [x] **Sorting**: header links sort one column asc/desc/off, "Cs" clears (done 2026-10-09).
- [x] **Clear filters**: the "Cf" button clears the filters of the page (done 2026-10-09).
- [ ] **Date format**: `DATETIME_FORMAT = "ymd-His"` was removed because Django ignores it.
      If you want that format, add a formats module (`FORMAT_MODULE_PATH`, e.g.
      `pSwai/pSwai/formats/en/formats.py`).
- [ ] **Login permissions**: any logged-in user can add, edit and delete everything.
      Decide whether to require staff status or per-model permissions.
- [ ] **Two login paths**: `/login/` (`appLogin`) and a POST to `/` (`appAutoGui.views.index`)
      both log users in, with different session lifetimes. Keep one.

## Features (from the former `TODO` file)

- [ ] Bulk actions: the selection checkboxes exist (`_D` column), but nothing acts on them.
- [ ] Rework the models to add a namespace level: server → namespace → url (repo).
- [ ] Validators for some models (external server, external url),
      e.g. that a repo's url belongs to its server.
- [ ] `Run`: trigger a manual copy action with parameters (from the README).

## Cleanup

- [ ] `DJANGO_LOGGERS_HANDLERS_APP` builds a logger for every installed app, including the
      `django.*` ones, which already go through the `django` logger. Limit it to the project apps.
- [ ] Clock skew on the NFS share makes `make` warn and rebuild more often than needed.

## Larger refactor (optional)

- [ ] `appAutoGui` largely reimplements Django's generic views (`ListView`, `CreateView`,
      `UpdateView`, `DeleteView`) using path-string parsing (`_split_path`,
      `full_path.replace(...)`). Moving to class-based views, possibly with `django-filter` /
      `django-tables2`, would remove most of that code and give sorting, filtering and bulk
      actions without custom code. The current tests (`make test`) are a safety net for this.
