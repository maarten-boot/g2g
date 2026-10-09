import uuid

from django.db import models

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


class Component(AbsCommonName):
    internal = models.BooleanField(
        default=True,
    )

    mainRepo = models.ForeignKey(
        Repo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:  # pylint:disable=R0903
        verbose_name_plural = "components"
        ordering = ("name",)


class Feature(AbsCommonName):
    class Meta:  # pylint:disable=R0903
        verbose_name_plural = "features"
        ordering = ("name",)


class Implementation(AbsBase):
    component = models.ForeignKey(
        Component,
        on_delete=models.CASCADE,
    )
    feature = models.ForeignKey(
        Feature,
        on_delete=models.CASCADE,
    )
    requested = models.BooleanField(
        default=False,  # if not requested we dont need to implement it
    )
    implemented = models.BooleanField(
        default=False,
    )
    description = models.TextField(
        blank=True,
        null=True,
    )

    class Meta:  # pylint:disable=R0903
        verbose_name_plural = "implementations"
        ordering = ("component", "feature")
        # (component, feature) is covered by the unique constraint's index
        indexes = [
            models.Index(fields=["requested", "feature"]),
            models.Index(fields=["implemented", "feature"]),
            models.Index(fields=["feature", "component"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["component", "feature"],
                name="implementation_unique_component_feature",
            ),
        ]

    def __str__(self):
        return f"{self.component} / {self.feature}"


class Dependencies(AbsBase):
    component = models.ForeignKey(
        Component,
        on_delete=models.CASCADE,
        related_name="dependencies",  # what this component uses
    )
    uses = models.ForeignKey(
        Component,
        on_delete=models.CASCADE,
        related_name="used_by",
    )
    description = models.TextField(
        blank=True,
        null=True,
    )

    class Meta:  # pylint:disable=R0903
        verbose_name = "dependency"
        verbose_name_plural = "dependencies"
        ordering = ("component", "uses")
        # (component, uses) is covered by the unique constraint's index
        indexes = [
            models.Index(fields=["uses", "component"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["component", "uses"],
                name="dependencies_unique_component_uses",
            ),
            models.CheckConstraint(
                condition=~models.Q(component=models.F("uses")),
                name="dependencies_not_self",
                violation_error_message="A component cannot depend on itself.",
            ),
        ]

    def __str__(self):
        return f"{self.component} uses {self.uses}"
