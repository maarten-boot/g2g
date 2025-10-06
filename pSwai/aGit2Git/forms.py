from django.forms import ModelForm


from aGit2Git.models import (
    Server,
    Script,
    Repo,
    RepoPair,
    CopyType,
    Component,
    Feature,
    Implementation,
    Dependencies,
)

from aGit2Git.autoGui import AUTO_GUI
from appAutoGui.xauto import get_model_data_from_autogui


def _gf(model):
    """_getFields of a model:
    get all the field names from a given model using the json AUTOGUI tree
    """
    return (
        get_model_data_from_autogui(
            AUTO_GUI,
            model.__name__,
        )
        .get("fields")
        .keys()
    )


class ServerForm(ModelForm):
    class Meta:  # pylint:disable=R0903
        model = Server
        fields = _gf(model)


class ScriptForm(ModelForm):
    class Meta:  # pylint:disable=R0903
        model = Script
        fields = _gf(model)


class RepoForm(ModelForm):
    class Meta:  # pylint:disable=R0903
        model = Repo
        fields = _gf(model)


class CopyTypeForm(ModelForm):
    class Meta:  # pylint:disable=R0903
        model = CopyType
        fields = _gf(model)


class RepoPairForm(ModelForm):
    class Meta:  # pylint:disable=R0903
        model = RepoPair
        fields = _gf(model)


class ComponentForm(ModelForm):
    class Meta:  # pylint:disable=R0903
        model = Component
        fields = _gf(model)


class FeatureForm(ModelForm):
    class Meta:  # pylint:disable=R0903
        model = Feature
        fields = _gf(model)


class ImplementationForm(ModelForm):
    class Meta:  # pylint:disable=R0903
        model = Implementation
        fields = _gf(model)


class DependenciesForm(ModelForm):
    class Meta:  # pylint:disable=R0903
        model = Dependencies
        fields = _gf(model)
