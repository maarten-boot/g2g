"""Rename the tables taken over from aGit2Git to this app's names (aComponents_*)."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("aComponents", "0001_initial"),
        ("aGit2Git", "0014_move_components_to_acomponents"),
    ]

    operations = [
        migrations.AlterModelTable(name="feature", table=None),
        migrations.AlterModelTable(name="component", table=None),
        migrations.AlterModelTable(name="implementation", table=None),
        migrations.AlterModelTable(name="dependencies", table=None),
    ]
