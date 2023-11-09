from django.forms import ModelForm

from typing import (
    Any,
    Dict,
    #    List,
)


from aGit2Git.models import (
    Server,
    Script,
    Url,
    UrlPair,
    CopyType,
)

from aGit2Git.autoGui import (
    AUTO_GUI,
    getFields,
)

class ServerForm(ModelForm):
    class Meta:
        model = Server
        template_name = "aaa"
        fields = getFields(model.__name__).get("fields").keys()


class ScriptForm(ModelForm):
    class Meta:
        model = Script
        template_name = "aaa"
        fields = getFields(model.__name__).get("fields").keys()


class UrlForm(ModelForm):
    class Meta:
        model = Url
        template_name = "aaa"
        fields = getFields(model.__name__).get("fields").keys()


class CopyTypeForm(ModelForm):
    class Meta:
        model = CopyType
        template_name = "aaa"
        fields = getFields(model.__name__).get("fields").keys()


class UrlPairForm(ModelForm):
    class Meta:
        model = UrlPair
        template_name = "aaa"
        fields = getFields(model.__name__).get("fields").keys()
