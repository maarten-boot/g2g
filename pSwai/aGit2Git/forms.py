from django.forms import ModelForm


from aGit2Git.models import (
    Server,
    Script,
    Url,
    UrlPair,
    CopyType,
    Component,
    Feature,
    Implementation,
    Dependencies,
)

from aGit2Git.autoGui import AUTO_GUI
from appAutoGui.xauto import getModelData2


def _gf(model):
    return getModelData2(AUTO_GUI, model.__name__).get("fields").keys()


class ServerForm(ModelForm):
    class Meta:
        model = Server
        fields = _gf(model)


class ScriptForm(ModelForm):
    class Meta:
        model = Script
        fields = _gf(model)


class UrlForm(ModelForm):
    class Meta:
        model = Url
        fields = _gf(model)


class CopyTypeForm(ModelForm):
    class Meta:
        model = CopyType
        fields = _gf(model)


class UrlPairForm(ModelForm):
    class Meta:
        model = UrlPair
        fields = _gf(model)


class ComponentForm(ModelForm):
    class Meta:
        model = Component
        fields = _gf(model)


class FeatureForm(ModelForm):
    class Meta:
        model = Feature
        fields = _gf(model)


class ImplementationForm(ModelForm):
    class Meta:
        model = Implementation
        fields = _gf(model)

class DependenciesForm(ModelForm):
    class Meta:
        model = Dependencies
        fields = _gf(model)
