from aGit2Git.models import AbsBase, AbsCommonName
from django.db import models

# Components, their features and dependencies. A component's main repo is a aGit2Git Repo.
# These models moved here from aGit2Git (migrations aComponents 0001/0002 and aGit2Git 0014);
# the index names below are the names the tables got in aGit2Git.


class Component(AbsCommonName):
    internal = models.BooleanField(
        default=True,
    )

    mainRepo = models.ForeignKey(
        "aGit2Git.Repo",
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
            models.Index(fields=["requested", "feature"], name="aGit2Git_im_request_226743_idx"),
            models.Index(fields=["implemented", "feature"], name="aGit2Git_im_impleme_879434_idx"),
            models.Index(fields=["feature", "component"], name="aGit2Git_im_feature_660430_idx"),
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
            models.Index(fields=["uses", "component"], name="aGit2Git_de_uses_id_b4f6db_idx"),
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
