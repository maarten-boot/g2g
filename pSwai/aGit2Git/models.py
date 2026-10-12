import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

# ==============================================
# ==============================================
# Abstract Base Classes


class AbsBase(models.Model):
    # The absolute Basics for all
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    creStamp = models.DateTimeField(
        auto_now=False,
        auto_now_add=True,
        null=False,
    )
    updStamp = models.DateTimeField(
        auto_now=True,
        auto_now_add=False,
        null=True,
    )

    class Meta:  # pylint:disable=R0903
        abstract = True

    def __repr__(self):
        return f"<{self.__class__.__name__} {self}>"

    def __str__(self):
        return str(self.id)


class AbsCommonName(AbsBase):
    # having Name
    name = models.CharField(
        max_length=128,
        unique=True,
        null=False,
    )
    description = models.TextField(
        blank=True,
        null=True,
    )

    class Meta:  # pylint:disable=R0903
        abstract = True

    def __str__(self):
        return self.name


# ==============================================
# ==============================================
# App configuration models


class Server(AbsCommonName):
    internal = models.BooleanField(
        default=True,
    )

    url = models.URLField(
        max_length=255,
        unique=True,
        null=False,
    )

    class Meta:  # pylint:disable=R0903
        verbose_name_plural = "servers"
        ordering = ("name",)


class Repo(AbsCommonName):
    # a repo is one branch of one git remote: unique on (url, branch), the name is just a label
    name = models.CharField(
        max_length=128,
        null=False,
    )

    url = models.URLField(
        max_length=255,
        null=False,
    )

    internal = models.BooleanField(
        default=True,
    )

    server = models.ForeignKey(
        Server,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="repos",
    )
    branch = models.CharField(
        max_length=128,
        unique=False,
        null=True,  # empty in the form is stored as NULL
        blank=True,
    )

    class Meta:  # pylint:disable=R0903
        verbose_name_plural = "repos"
        indexes = [
            models.Index(fields=["name", "branch"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["url", "branch"],
                nulls_distinct=False,  # only one "no branch" row per url
                name="repo_unique_url_branch",
                violation_error_message="This url already exists with the same branch.",
            ),
        ]
        ordering = ("name", "branch")

    def __str__(self):
        if self.branch:
            return f"{self.name} ({self.branch})"
        return self.name


class Script(AbsCommonName):
    repo = models.ForeignKey(
        Repo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    # the [scripts.<id>] of the Run allowlist this script starts (docs/run-design.md); the database never holds a path
    allowlist_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        validators=[
            RegexValidator(r"^[a-z0-9][a-z0-9_-]{0,63}$", "an allowlist id: lower case letters, digits, - and _"),
        ],
    )

    class Meta:  # pylint:disable=R0903
        verbose_name_plural = "scripts"
        ordering = ("name",)


class CopyType(AbsCommonName):
    manual = models.BooleanField(
        default=True,
    )
    needTag = models.BooleanField(
        default=False,
    )

    script = models.ForeignKey(
        Script,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:  # pylint:disable=R0903
        verbose_name_plural = "copy types"
        ordering = ("name",)


class RepoPair(AbsCommonName):
    source = models.ForeignKey(
        Repo,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="pairs_as_source",
    )

    target = models.ForeignKey(
        Repo,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="pairs_as_target",
    )

    copyType = models.ForeignKey(
        CopyType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:  # pylint:disable=R0903
        verbose_name_plural = "repo pairs"
        ordering = ("name",)
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(source=models.F("target")),
                name="repopair_source_not_target",
                violation_error_message="Source and target must be different repos.",
            ),
        ]


class Run(AbsBase):
    """One execution of an allowlisted script (docs/run-design.md §5). The output is in RUNNER_RUNS_DIR/<id>.log."""

    RUNNING = "running"
    STATUS_CHOICES = [
        (RUNNING, "running"),
        ("succeeded", "succeeded"),
        ("failed", "failed"),
        ("timed_out", "timed out"),
        ("output_capped", "output limit exceeded"),
        ("interrupted", "interrupted"),
    ]

    script_id = models.CharField(max_length=64)  # the allowlist id that ran, kept when the Script record changes
    repo_pair = models.ForeignKey(
        RepoPair,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    started_by_name = models.CharField(max_length=150)  # kept when the user is deleted
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=RUNNING)
    result = models.CharField(max_length=200, blank=True)  # the runner's status line, e.g. "exit code 1"
    exit_code = models.IntegerField(null=True, blank=True)
    pid = models.IntegerField(null=True, blank=True)  # the script's process, for the orphan check after a restart
    output_bytes = models.BigIntegerField(default=0)

    class Meta:  # pylint:disable=R0903
        verbose_name_plural = "runs"
        ordering = ("-started_at",)
        indexes = [
            models.Index(fields=["script_id", "-started_at"], name="run_script_started"),
        ]

    def __str__(self):
        return f"{self.script_id} {self.started_at:%Y-%m-%d %H:%M} {self.status}"

    @property
    def running(self) -> bool:
        return self.status == self.RUNNING
