from django.forms import ModelForm


from aGit2Git.models import (
    Server,
    Script,
    Url,
    UrlPair,
    CopyType,
)

from aGit2Git.autoGui import AUTO_GUI
from appAutoGui.xauto import getFields


def _gf(model):
    return getFields(AUTO_GUI, model.__name__).get("fields").keys()


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
