import sys

from typing import (
    Any,
    # Dict,
)

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
    # AUTO_GUI,
    getFields,
    getNavNames,
)

from aGit2Git import views

# maxPerPagePaginate
DEBUG = 0


def urlGenOne(app, k):
    ll = [
        path(f"{app}/{k}/", views.index, name=f"{app}_{k}"),
        path(f"{app}/{k}/add/", views.form, name=f"{app}_{k}_add"),
        path(f"{app}/{k}/edit/<uuid:id>", views.form, name=f"{app}_{k}_edit"),
        path(f"{app}/{k}/delete/<uuid:id>", views.form, name=f"{app}_{k}_delete"),
    ]

    print(ll, file=sys.stderr)
    return ll


def urlGenAll(app):
    xList = getNavNames()
    urlPatternList = []
    for item in xList:
        z = urlGenOne(app, item)
        urlPatternList += z

    print(urlPatternList, file=sys.stderr)
    return urlPatternList


def mapForm(app: str, fp: str, *args, **kwargs) -> Any:
    xList = getNavNames()
    for name in xList:
        pass

    if fp.startswith(f"/{app}/server/"):
        return ServerForm(*args, **kwargs)
    if fp.startswith(f"/{app}/script/"):
        return ScriptForm(*args, **kwargs)
    if fp.startswith(f"/{app}/url/"):
        return UrlForm(*args, **kwargs)
    if fp.startswith(f"/{app}/urlpair/"):
        return UrlPairForm(*args, **kwargs)
    if fp.startswith(f"/{app}/copytype/"):
        return CopyTypeForm(*args, **kwargs)

    return None


def mapModel(app: str, fp):
    xList = getNavNames()
    for name in xList:
        pass

    print(app, fp, file=sys.stderr)

    if fp.startswith(f"/{app}/server/"):
        return Server
    if fp.startswith(f"/{app}/script/"):
        return Script
    if fp.startswith(f"/{app}/url/"):
        return Url
    if fp.startswith(f"/{app}/urlpair/"):
        return UrlPair
    if fp.startswith(f"/{app}/copytype/"):
        return CopyType

    return None


def mkDeleteLink(pk: str):
    return (
        "<input class='form-check-input' type='checkbox' value='"
        + f"{pk}"
        + "' name='action{{ action_clean }}' id='action{{ action_clean }}{{"
        + f"{pk}"
        + "}}'>"
    )


def makeEditLink(pk: str, name: str):
    what = "edit"
    return "<a href='{{ action_clean }}" + what + "/{{" + f"{pk}" + "}}'>{{" + f"{name}" + "}}</a>"


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


def getMyFields(app, fp):
    model = mapModel(app, fp)
    print(model, file=sys.stderr)
    if not model:
        return {}

    ff = getFields(model.__name__).get("fields")
    print(ff, file=sys.stderr)
    xList = getNavNames()
    for name in xList:
        if fp.startswith(f"/{app}/{name}/"):
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


def makeIndexFields(app, fp, page_obj):
    # this func should be totally generic

    def test1(tempString, item):
        t = Template(tempString)
        c = Context(item)
        html = t.render(c)
        return html

    xFields = getMyFields(app, fp)
    print(xFields, file=sys.stderr)

    data = []
    names = []
    if page_obj:
        for item in page_obj:
            fieldData = makeDictFromModel(item)
            fieldData["action"] = fp
            fieldData["action_clean"] = fp.split("?")[0]

            fields = {}
            for k, v in xFields.items():
                if k not in names:
                    names.append(k)
                html = test1(v, fieldData)
                fields[k] = html
            data.append(fields)
    return names, data
