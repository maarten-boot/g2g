# g2g – specification (draft)

Status: **draft**. Statements without a marker describe what the code does today.
**❓** marks a decision that is still open; where there is a suggestion it says so.
How the app is built and run is in the [README](../README.md); open work is in [todo.md](../todo.md).

## 1. Purpose

g2g keeps control of code moving between internal and external git servers.
It records which repositories may be copied where, how, and by whom, and (planned) performs and
logs those copies, so that nothing leaves (or enters) the company unnoticed.

A second, separate part tracks components, their features and their dependencies.

The component/feature part is its own django app (`aComponents`), next to the copy administration
(`aGit2Git`); both start from the git repos (`Component.mainRepo` is an `aGit2Git` `Repo`). Each app has its
own menu section; planned: a collapsible left menu per app.

❓ Does the component part ever drive which repos get copied (e.g. a feature that is "implemented" triggers a
   release copy)?

## 2. Concepts

| concept | meaning today | open |
|---|---|---|
| Server | a git server (url), marked internal or external | ❓ is `internal` enough, or do we need trust levels (e.g. customer, partner, public)? |
| Repo | one branch of a git remote on a server; unique on url + branch | ❓ does a repo also have an `internal` flag of its own, or is it always the server's? (today both exist and can disagree) |
| RepoPair | a source repo, a target repo (different) and a copy type | ❓ is a pair one-directional (source → target only)? suggestion: yes |
| CopyType | how to copy: `manual`, `needTag`, optional script | see §4 |
| Script | a script that performs a copy, optionally kept in a repo | see §4 |
| Component / Feature / Implementation / Dependencies | inventory of components, which features they have, and what uses what | see §1 |

### Planned: namespace level

Server → namespace → repo (from the former TODO).

❓ What is a namespace: a group/organisation/project path on the server (e.g. `gitlab.example.com/team-a`)?
❓ Do rules (§5) apply per namespace (e.g. "everything in `oss/` may go to GitHub")?
❓ Does the repo url then become namespace url + repo name, or is it still entered in full?

## 3. Users and roles

Today: users log in with their AD account; AD group `LDAP_ACTIVE` makes a user active,
`LDAP_STAFF` makes a user staff (admin site). Every logged-in user may view everything; adding, changing
and deleting need the django permission per model. Members of `LDAP_ADMIN` are superusers (all rights);
others get rights through django groups (local, or named like an AD group). See README, Permissions.

❓ Which roles do we need? Suggestion:

| role | may |
|---|---|
| viewer | see everything |
| maintainer | manage servers, repos, pairs, copy types, scripts |
| operator | start a copy (`Run`) for an existing pair |
| approver | approve copies that need approval (§5) |
| admin | everything, including users/groups |

❓ Map roles to AD groups (like `LDAP_STAFF`), or manage them in django groups?
❓ May the person who requests a copy also approve it? Suggestion: no (four-eyes) for copies to external servers.

## 4. Copying (planned: `Run`)

A **run** is one execution of a copy for one repo pair.

### 4.1 Trigger

- `CopyType.manual = True`: an operator starts the run from the UI.
- `CopyType.manual = False`: ❓ what triggers it: a schedule (how often), a webhook from the source server
  (push/tag), or both?

### 4.2 What is copied

❓ Per copy type, what does a copy transfer? Options:
   - the branch of the source repo (the repo's `branch`) to the target branch
   - tags only / a specific tag
   - a full mirror (all branches and tags) — suggestion: never allowed towards external servers

`CopyType.needTag = True`: ❓ suggestion: the run must name a tag that exists in the source;
only the commit history up to that tag is pushed, and the tag is pushed with it.

❓ Is the target ever force-pushed? Suggestion: no; a run fails when the target has diverged.
❓ Is history rewritten or filtered (e.g. removing internal paths or files, squashing) before going external?
   If yes, that is the script's job and the script must be reviewed (see §4.3).

### 4.3 Scripts

Today a script has a name, description and an optional repo where it lives.

❓ What does a script receive (source url, target url, branch, tag, run id, credentials)?
❓ Where does it run: inside the web container, a worker container, or a CI runner?
   Suggestion: a separate worker, never in the web process.
❓ Which version of the script is used: always the latest of its repo, or a pinned commit?
   Suggestion: pinned commit, recorded in the run.
❓ Without a script: is there a built-in default copy (plain `git fetch` + `git push`)?

### 4.4 Credentials

❓ Where do the credentials for the git servers live (per server? per namespace?), and who may set them?
   Suggestion: not in the database in plain text; an environment/secret store reference per server.

### 4.5 What a run records

Suggestion: who started it, when, the pair, the copy type and script version, the source commit (and tag),
the target commit after the push, the result (success/failed), and the log output.
Runs are never edited or deleted from the UI.

❓ How long are runs (and their logs) kept?

## 5. Rules

Enforced today:
- a repo pair's source and target must be different repos
- a repo is unique on url + branch
- a component cannot depend on itself; implementation and dependency pairs are unique

❓ Direction: may data flow external → internal through g2g, or only internal → external?
❓ Must every copy to an external server be approved before it runs? Suggestion: yes, unless the copy
   type is marked as pre-approved by an approver.
❓ Validators (from the former TODO): the repo url must belong to its server (and namespace);
   an "external" repo must be on an external server; anything else?
❓ What happens to existing pairs when a server changes from internal to external?

## 6. Notifications and audit

❓ Who is notified of runs (failed runs, runs to external servers, pending approvals), and how (mail, chat)?
❓ Do changes to servers/repos/pairs/copy types need an audit trail (who changed what, when)?
   Suggestion: yes for pairs, copy types and scripts, as they decide what may leave the company.

## 7. Non-goals

Suggestion (to confirm):
- g2g is not a git hosting service and does not store repository content beyond a run.
- g2g does not review code content; it controls which repos and refs may move, and records that they did.

## 8. Decisions log

Record decisions here as the ❓ items are answered (date, decision, by whom).

| date | decision |
|---|---|
| 2026-10-09 | a repo is unique on url + branch; an empty branch counts as one value |
| 2026-10-09 | the unused `Tag` model is removed |
| 2026-10-09 | all app pages require login; LDAP server certificates are verified |
| 2026-10-10 | components/features moved to their own app `aComponents` (migrations keep the data) |
| 2026-10-10 | everyone logged in may view; add/change/delete per django permission; `LDAP_ADMIN` members are superusers; AD groups no longer mirrored |
