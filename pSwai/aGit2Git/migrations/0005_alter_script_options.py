# Generated by Django 4.2.6 on 2023-10-19 18:26

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("aGit2Git", "0004_remove_copytype_scriptname"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="script",
            options={"ordering": ("name",), "verbose_name_plural": "Script"},
        ),
    ]