"""Move Component, Feature, Implementation and Dependencies from aGit2Git to aComponents.

The tables are not touched here: this app takes them over in its migration state (still named aGit2Git_*,
0002 renames them), and aGit2Git 0014 drops them from its state only. The content types are relabelled,
so the admin history and the model permissions move along instead of being orphaned.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models

MOVED_MODELS = ["component", "feature", "implementation", "dependencies"]


def move_content_types(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="aGit2Git", model__in=MOVED_MODELS).update(app_label="aComponents")


def move_content_types_back(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="aComponents", model__in=MOVED_MODELS).update(app_label="aGit2Git")


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("aGit2Git", "0013_constraints_and_cleanup"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Feature",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("creStamp", models.DateTimeField(auto_now_add=True)),
                        ("updStamp", models.DateTimeField(auto_now=True, null=True)),
                        ("name", models.CharField(max_length=128, unique=True)),
                        ("description", models.TextField(blank=True, null=True)),
                    ],
                    options={
                        "db_table": "aGit2Git_feature",
                        "verbose_name_plural": "features",
                        "ordering": ("name",),
                    },
                ),
                migrations.CreateModel(
                    name="Component",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("creStamp", models.DateTimeField(auto_now_add=True)),
                        ("updStamp", models.DateTimeField(auto_now=True, null=True)),
                        ("name", models.CharField(max_length=128, unique=True)),
                        ("description", models.TextField(blank=True, null=True)),
                        ("internal", models.BooleanField(default=True)),
                        (
                            "mainRepo",
                            models.ForeignKey(
                                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="aGit2Git.repo"
                            ),
                        ),
                    ],
                    options={
                        "db_table": "aGit2Git_component",
                        "verbose_name_plural": "components",
                        "ordering": ("name",),
                    },
                ),
                migrations.CreateModel(
                    name="Dependencies",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("creStamp", models.DateTimeField(auto_now_add=True)),
                        ("updStamp", models.DateTimeField(auto_now=True, null=True)),
                        ("description", models.TextField(blank=True, null=True)),
                        (
                            "component",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="dependencies",
                                to="aComponents.component",
                            ),
                        ),
                        (
                            "uses",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="used_by",
                                to="aComponents.component",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "aGit2Git_dependencies",
                        "verbose_name": "dependency",
                        "verbose_name_plural": "dependencies",
                        "ordering": ("component", "uses"),
                        "indexes": [models.Index(fields=["uses", "component"], name="aGit2Git_de_uses_id_b4f6db_idx")],
                        "constraints": [
                            models.UniqueConstraint(
                                fields=("component", "uses"), name="dependencies_unique_component_uses"
                            ),
                            models.CheckConstraint(
                                condition=models.Q(("component", models.F("uses")), _negated=True),
                                name="dependencies_not_self",
                                violation_error_message="A component cannot depend on itself.",
                            ),
                        ],
                    },
                ),
                migrations.CreateModel(
                    name="Implementation",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("creStamp", models.DateTimeField(auto_now_add=True)),
                        ("updStamp", models.DateTimeField(auto_now=True, null=True)),
                        ("requested", models.BooleanField(default=False)),
                        ("implemented", models.BooleanField(default=False)),
                        ("description", models.TextField(blank=True, null=True)),
                        (
                            "component",
                            models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="aComponents.component"),
                        ),
                        (
                            "feature",
                            models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="aComponents.feature"),
                        ),
                    ],
                    options={
                        "db_table": "aGit2Git_implementation",
                        "verbose_name_plural": "implementations",
                        "ordering": ("component", "feature"),
                        "indexes": [
                            models.Index(fields=["requested", "feature"], name="aGit2Git_im_request_226743_idx"),
                            models.Index(fields=["implemented", "feature"], name="aGit2Git_im_impleme_879434_idx"),
                            models.Index(fields=["feature", "component"], name="aGit2Git_im_feature_660430_idx"),
                        ],
                        "constraints": [
                            models.UniqueConstraint(
                                fields=("component", "feature"), name="implementation_unique_component_feature"
                            )
                        ],
                    },
                ),
            ],
        ),
        migrations.RunPython(move_content_types, move_content_types_back),
    ]
