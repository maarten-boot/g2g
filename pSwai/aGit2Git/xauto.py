import sys

from django.template import (
    Context,
    Template,
)

from django.urls import path


from aGit2Git.models import (
    Server,
    Script,
    Url,
    UrlPair,
    CopyType,
)

from aGit2Git.forms import (
    ServerForm,
    ScriptForm,
    UrlForm,
    UrlPairForm,
    CopyTypeForm,
)

from aGit2Git.autoGui import (
    AUTO_GUI,
    getFields,
)

from aGit2Git import views

from typing import (
    Any,
    Dict,
)

DEBUG = 0

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


def addFields(xFields, ff, skipList):
    for k, v in ff.items():
        if k in skipList:
            continue
        xFields[v] = defaultFieldTemplate(k)


def xFieldsDefault(ff):
    xFields = {
        "_": mkDeleteLink("id"),
        "Name": makeEditLink("id", "name"),
    }
    addFields(xFields, ff, ["name"])
    return xFields


def getMyFields(fp):
    model = mapModel(fp)
    if not model:
        return {}

    ff = getFields(model.__name__).get("fields")

    if DEBUG:
        print(ff, file=sys.stderr)

    if fp.startswith("/server/"):
        return xFieldsDefault(ff)

    if fp.startswith("/script/"):
        return xFieldsDefault(ff)

    if fp.startswith("/url/"):
        return xFieldsDefault(ff)

    if fp.startswith("/urlpair/"):
        return xFieldsDefault(ff)

    if fp.startswith("/copytype/"):
        return xFieldsDefault(ff)

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
