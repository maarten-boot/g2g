# import sys

from aGit2Git.forms import (
    ServerForm,
    ScriptForm,
    UrlForm,
    UrlPairForm,
    CopyTypeForm,
)

from aGit2Git.models import (
    Server,
    Script,
    Url,
    UrlPair,
    CopyType,
)
from django.template import (
    Context,
    Template,
)

from django.urls import path
from aGit2Git import views

from typing import (
    Any,
    Dict,
)


AUTO_GUI = {
    "navigation": {
        "Server": "server",
        "Script": "script",
        "Url": "url",
        "UrlPair": "urlpair",
        "CopyType": "copytype",
        "Admin": "admin",
    },
    "models": {
        "Server": {
            "nav": "server",
            "fields": {
                "name": "Name",
                "description": "Description",
                "url": "Url",
                "internal": "Internal",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "url": "url",
                "internal": "internal",
            },
        },
        "Url": {
            "nav": "url",
            "fields": {
                "name": "Name",
                "description": "Description",
                "server": "Server",
                "internal": "Internal",
                "url": "Url",
                "branch": "Branch",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "server": "server__name",
                "internal": "internal",
                "url": "url",
                "branch": "branch",
            },
        },
        "Script": {
            "nav": "script",
            "fields": {
                "name": "Name",
                "description": "Description",
                "repo": "Repository",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "repo": "repo__name",
            },
        },
        "CopyType": {
            "nav": "copytype",
            "fields": {
                "name": "Name",
                "description": "Description",
                "manual": "Manual",
                "needTag": "NeedTag",
                "script": "Script",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "manual": "manual",
                "needTag": "needTag",
                "script": "script__name",
            },
        },
        "UrlPair": {
            "nav": "urlpair",
            "fields": {
                "name": "Name",
                "description": "Description",
                "source": "Source",
                "target": "Target",
                "copyType": "CopyType",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "source": "source__name",
                "target": "target__name",
                "copyType": "copyType",
            },
        },
    },
}


def getFields(modelName: str) -> Dict[str, str]:
    k = "models"
    if modelName in AUTO_GUI[k]:
        return AUTO_GUI[k][modelName]
    return {}


def urlGenOne(k):
    return [
        path(f"{k}/", views.index, name=f"{k}"),
        path(f"{k}/add/", views.form, name=f"{k}_add"),
        path(f"{k}/edit/<uuid:id>", views.form, name=f"{k}_edit"),
        path(f"{k}/delete/<uuid:id>", views.form, name=f"{k}_delete"),
    ]


def urlGenAll():
    xList = [
        "server",
        "script",
        "url",
        "urlpair",
        "copytype",
    ]
    urlPatternList = []
    for item in xList:
        z = urlGenOne(item)
        urlPatternList += z
    return urlPatternList


def maxPerPagePaginate():
    return 10


def mapForm(fp: str, *args, **kwargs) -> Any:
    if fp.startswith("/server/"):
        return ServerForm(*args, **kwargs)
    if fp.startswith("/script/"):
        return ScriptForm(*args, **kwargs)
    if fp.startswith("/url/"):
        return UrlForm(*args, **kwargs)
    if fp.startswith("/urlpair/"):
        return UrlPairForm(*args, **kwargs)
    if fp.startswith("/copytype/"):
        return CopyTypeForm(*args, **kwargs)

    return None


def mapModel(fp):
    if fp.startswith("/server/"):
        return Server
    if fp.startswith("/script/"):
        return Script
    if fp.startswith("/url/"):
        return Url
    if fp.startswith("/urlpair/"):
        return UrlPair
    if fp.startswith("/copytype/"):
        return CopyType
    return None


def mkDeleteLink(pk: str):
    return "<input class='form-check-input' type='checkbox' value='" + f"{pk}" + "' name='action{{ action }}' id='action{{ action }}{{" + f"{pk}" + "}}'>"


def makeEditLink(pk: str, name: str):
    return "<a href='{{ action }}edit/{{" + f"{pk}" + "}}'>{{" + f"{name}" + "}}</a>"


def defaultFieldTemplate(name):
    return "{{ " + f"{name}" + " }}"


def getMyFields(fp):
    def addFields(xFields, ff, skipList):
        for k, v in ff.items():
            if k in skipList:
                continue
            xFields[v] = defaultFieldTemplate(k)

    model = mapModel(fp)
    if not model:
        return {}

    ff = getFields(model.__name__).get("fields")

    if fp.startswith("/server/"):
        xFields = {
            "_": mkDeleteLink("id"),
            "Name": makeEditLink("id", "name"),
        }
        addFields(xFields, ff, ["name"])
        return xFields

    if fp.startswith("/script/"):
        xFields = {
            "_": mkDeleteLink("id"),
            "Name": makeEditLink("id", "name"),
        }
        addFields(xFields, ff, ["name"])
        return xFields

    if fp.startswith("/url/"):
        xFields = {
            "_": mkDeleteLink("id"),
            "Name": makeEditLink("id", "name"),
        }
        addFields(xFields, ff, ["name"])
        return xFields

    if fp.startswith("/urlpair/"):
        xFields = {
            "_": mkDeleteLink("id"),
            "Name": makeEditLink("id", "name"),
        }
        addFields(xFields, ff, ["name"])
        return xFields

    if fp.startswith("/copytype/"):
        xFields = {
            "_": mkDeleteLink("id"),
            "Name": makeEditLink("id", "name"),
        }
        addFields(xFields, ff, ["name"])
        return xFields

    return {}


def makeDictFromModel(instance):
    # this func should be totally generic

    ret = {}
    if not instance:
        return ret

    modelName = instance.__class__.__name__

    # the first item in the result
    name = "id"
    ret[name] = getattr(instance, name)

    # the other items in the result
    ff = getFields(modelName).get("fields")
    for name in ff.keys():
        ret[name] = getattr(instance, name)

    return ret


def getFilterPrefix():
    return "filter-"


def makeIndexFields(fp, page_obj):
    # this func should be totally generic

    def test1(tempString, item):
        t = Template(tempString)
        c = Context(item)
        html = t.render(c)
        return html

    xFields = getMyFields(fp)

    data = []
    names = []
    if page_obj:
        for item in page_obj:
            fieldData = makeDictFromModel(item)
            fieldData["action"] = fp
            fields = {}
            for k, v in xFields.items():
                if k not in names:
                    names.append(k)
                html = test1(v, fieldData)
                fields[k] = html
            data.append(fields)
    return names, data
