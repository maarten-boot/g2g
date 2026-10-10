"""Component, Feature, Implementation and Dependencies moved to the aComponents app.

State only: the tables stay, aComponents 0001 took them over (and 0002 renames them).
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("aGit2Git", "0013_constraints_and_cleanup"),
        ("aComponents", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="Dependencies"),
                migrations.DeleteModel(name="Implementation"),
                migrations.DeleteModel(name="Component"),
                migrations.DeleteModel(name="Feature"),
            ],
        ),
    ]
