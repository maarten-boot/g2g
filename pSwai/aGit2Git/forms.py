from django.forms import ModelForm

from aGit2Git.models import (
    Server,
    Script,
    Url,
    UrlPair,
    CopyType,
)


class ServerForm(ModelForm):
    class Meta:
        model = Server
        template_name = "aaa"
        fields = [
            "name",
            "description",
            "internal",
            "url",
        ]


class ScriptForm(ModelForm):
    class Meta:
        model = Script
        template_name = "aaa"
        fields = [
            "name",
            "description",
            "repo",
        ]


class UrlForm(ModelForm):
    class Meta:
        model = Url
        template_name = "aaa"
        fields = [
            "name",
            "description",
            "url",
            "internal",
            "server",
            "branch",
        ]


class CopyTypeForm(ModelForm):
    class Meta:
        model = CopyType
        template_name = "aaa"
        fields = [
            "name",
            "description",
            "manual",
            "needTag",
            "script",
        ]


class UrlPairForm(ModelForm):
    class Meta:
        model = UrlPair
        template_name = "aaa"
        fields = [
            "name",
            "description",
            "source",
            "target",
            "copyType",
        ]
