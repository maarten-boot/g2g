"""Prepare existing data for the constraints added in 0013.

- an empty branch ("") is stored as NULL, so "" and NULL cannot be two different "no branch" rows
- refuse to continue (nothing is changed) when existing rows would violate:
    repo (url, branch) unique, repo pair source != target, dependency component != uses
  fix those rows first (admin or index pages), then run migrate again.
"""

from django.db import migrations
from django.db.models import Count, F


def _check(apps, schema_editor):
    Repo = apps.get_model("aGit2Git", "Repo")
    RepoPair = apps.get_model("aGit2Git", "RepoPair")
    Dependencies = apps.get_model("aGit2Git", "Dependencies")

    Repo.objects.filter(branch="").update(branch=None)

    problems = []

    duplicates = Repo.objects.values("url", "branch").annotate(n=Count("id")).filter(n__gt=1)
    for d in duplicates:
        names = list(Repo.objects.filter(url=d["url"], branch=d["branch"]).values_list("name", flat=True))
        problems.append(f"repo url {d['url']!r} branch {d['branch']!r} is used {d['n']} times: {names}")

    for p in RepoPair.objects.filter(source=F("target")):
        problems.append(f"repo pair {p.name!r} has the same repo as source and target")

    for dep in Dependencies.objects.filter(component=F("uses")).select_related("component"):
        problems.append(f"component {dep.component.name!r} depends on itself")

    if problems:
        # the migration runs in a transaction: raising also undoes the branch update above
        raise RuntimeError(
            "existing data violates the new constraints, fix these rows and run migrate again:\n  - "
            + "\n  - ".join(problems)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("aGit2Git", "0011_rename_url_repo_rename_urlpair_repopair_and_more"),
    ]

    operations = [
        migrations.RunPython(_check, migrations.RunPython.noop),
    ]
