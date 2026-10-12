# Todo

Open items. Finished items are in [done.md](done.md).

## Next production deploy

Production last got the review batches (2026-10-09); check which of these are already done there.

- [ ] Back up the database, then `migrate`: `aComponents 0001`, `aGit2Git 0014`, `aComponents 0002` move the
      component tables to the new app (rehearsed on the production dump).
- [ ] Run `collectstatic` after every deploy now (versioned static names): without it the pages fail.
- [ ] Run `manage.py cleanup_ad_groups` (list first), then with `--delete`.
- [ ] Optional: remove `mail_admins` from the log handler lists and `ENVIRONMENT` from production's `.env`
      (both are ignored now; the handler names give a warning at startup).
- [ ] Old bookmarks to `/aGit2Git/component/…` (feature, implementation, dependencies) now live under
      `/aComponents/…`.

## Permissions

- [ ] The 49 groups named like AD groups keep the member lists of the old mirroring (frozen at each user's
      last login). Before giving one of them permissions, clear its members in the admin, so that only the
      current AD membership counts (`AUTH_LDAP_FIND_GROUP_PERMS`).

## Features

- [ ] Validators for some models (external server, external url), e.g. that a repo's url belongs to its server.
- [ ] `Run`: start copy scripts from g2g (a Run button on repo pairs); design and steps in
      [docs/run-design.md](docs/run-design.md).

## Cleanup

- [ ] Clock skew on the NFS share makes `make` warn and rebuild more often than needed.

## Larger refactor (optional)

- [ ] `appAutoGui` largely reimplements Django's generic views (`ListView`, `CreateView`, `UpdateView`,
      `DeleteView`) using path-string parsing (`_split_path`, `full_path.replace(...)`). Moving to class-based
      views, possibly with `django-filter` / `django-tables2`, would remove most of that code and give sorting,
      filtering and bulk actions without custom code. The current tests (`make test`) are a safety net for this.
