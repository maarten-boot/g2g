# Done

Finished items moved from [todo.md](todo.md), with the commit (or setting) and date.

## Deployment and production

- Back up the database before migration `0013` (drops the `aGit2Git_tag` table); `migrate` run on production,
  `0012` found no problem rows (2026-10-09).
- `LDAP_TLS_VERIFY=True`: login with full certificate check, tested on a fresh stack with new volumes; the host CA
  bundle is mounted into the web container (`49ad93d`, 2026-10-09).
- One real LDAP login with a user account, also with the UPN or mail address (`9fba36b`, 2026-10-09).
- `DJANGO_HTTPS=True` on production (2026-10-09).
- `DJANGO_SECURE_HSTS_SECONDS` on production (start small, e.g. 3600, raise later) (2026-10-10). No effect on the
  docker test stack: only read with `DJANGO_HTTPS`, only sent over https.
- `DJANGO_CSRF_TRUSTED_ORIGINS` in the local `pSwai/.env` for the docker stack (`http://localhost:8080`,
  `http://192.168.122.196:8080`) (2026-10-11). Production only needs it when form posts fail with a CSRF origin
  error (then its own https address).

## Secrets and configuration

- `env-example` (formerly `.env.example`) is the committed template, placeholders only; no real `.env` was ever
  committed (checked 2026-10-09 and 2026-10-10).
- One real settings file, `pSwai/.env`; docker uses a copy next to `compose.yaml` (`make docker_test`);
  the db container gets no app secrets (`17117e0`, 2026-10-10).
- Unused keys removed from `pSwai/.env` (mail settings from another project) and dead code removed: unused
  templates, the `file` and `mail_admins` log handlers, `do_paging_with_search_filters`, unused parameters,
  `LOGIN/LOGOUT_REDIRECT_URL`; unknown handler names in an older `.env` are ignored with a warning
  (`da61176`, 2026-10-10).
- The `if DJANGO_DEBUG:` block (not valid dotenv syntax) removed from the `.env` files (2026-10-09).
- Logging: console (stderr) in docker for development, syslog on the server without docker (decided 2026-10-10).
  For syslog from docker use the logging driver (`driver: journald`), not a `/dev/log` mount.
- `ENVIRONMENT` removed: nothing read it; more logging while developing is `DJANGO_LOG_LEVEL` /
  `LDAP_LOG_LEVEL=DEBUG` (`43b0435`, 2026-10-10).
- Per-app loggers only for the project apps; the `django.*` apps log through the `django` logger
  (`3907275`, 2026-10-09).

## Behaviour

- Boolean filters: exact match on yes/no, y/n, true/false, 1/0, on/off (`50f0251`, 2026-10-09).
- Sorting: header links sort one column asc/desc/off, "Cs" clears; "Cf" clears the filters (`62047e2`, 2026-10-09).
- Date format `ymd-His` (e.g. 261010-093015) via `pSwai/pSwai/formats/en/formats.py` and `FORMAT_MODULE_PATH`
  (`92012c1`, 2026-10-10).
- Permissions: view for everyone logged in; add/change/delete per django permission (local groups); `LDAP_ADMIN`
  members are superusers; AD groups no longer mirrored (`ef73ddd`, 2026-10-10). `LDAP_ADMIN` set in `pSwai/.env`
  (2026-10-11).
- Groups that no longer exist in AD removed locally with `manage.py cleanup_ad_groups --delete`
  (1 of 50 groups; `9a7e94d`, 2026-10-11).
- One login path (`/login/`); the session ends when the browser closes (`058d418`, 2026-10-09).

## Features

- Collapsible left menu: a section per app, open for the app you are in, collapsed otherwise
  (`830ee2a`, `9c658ea`, 2026-10-11).
- Bulk delete from the lists, with a confirmation of what cascades (`5b723a2`, 2026-10-11).
- The single Delete (on an item's page) shows what cascades and needs the delete permission for it too,
  as the bulk delete (2026-10-11).

## Also done (not on the todo list)

- Review fixes, batches 1–5 (`fcb0469`..`2308629`, 2026-10-09): login required, docker setup, bug fixes and
  tests, model constraints, pinned requirements, `make check` / `make test`.
- Failed logins are shown and logged (`276e8ca`); login with UPN, mail address or `DOMAIN\user` (`9fba36b`).
- Restore a database dump on a new docker volume, then migrate (`639c49b`).
- Draft spec `docs/spec.md` (`5ea3fc5`); README brought up to date (`c6fd652` and later).
- Admin link in the menu for staff users (`98e38bd`).
- The components part is its own app `aComponents`, with migrations that keep the data (`927d2ec`).
- Foreign key columns link to the related item's page (`b4b6b68`); URL fields are links (`9d32384`).
- The menu keeps the current model highlighted on its sub-pages (`a7fcded`).
- Very light gray page background (`d8dd879`); centered login form (`db25e61`).
- Versioned static file names, so browsers never keep an old css (`18446bb`).
