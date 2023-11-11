import sys
from importlib import import_module

from typing import (
    Any,
    # Dict,
)

from django.template import (
    Context,
    Template,
)

from aGit2Git.autoGui import (
    getFields,
    getNavNames,
)

DEBUG = 0


def importClass(klassStr):
    module_path, class_name = klassStr.rsplit(".", 1)
    try:
        module = import_module(module_path)
        klass = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        print(e, file=sys.stderr)
        raise ImportError(klassStr)

    return klass


def mapForm(app: str, fp: str, *args, **kwargs) -> Any:
    xList = getNavNames()
    for nav, modelName in xList.items():
        if fp.startswith(f"/{app}/{nav}/"):
            class_str = ".".join([app, "forms", modelName + "Form"])
            klass = importClass(class_str)
            return klass(*args, **kwargs)
    return None


def mapModel(app: str, fp):
    xList = getNavNames()
    for nav, modelName in xList.items():
        if fp.startswith(f"/{app}/{nav}/"):
            class_str = ".".join([app, "models", modelName])
            klass = importClass(class_str)
            return klass
    return None


def _mkDeleteLink(pk: str):
    return (
        "<input class='form-check-input' type='checkbox' value='"
        + f"{pk}"
        + "' name='action{{ action_clean }}' id='action{{ action_clean }}{{"
        + f"{pk}"
        + "}}'>"
    )


def _makeEditLink(pk: str, name: str):
    what = "edit"
    return "<a href='{{ action_clean }}" + what + "/{{" + f"{pk}" + "}}'>{{" + f"{name}" + "}}</a>"


def _defaultFieldTemplate(name):
    return "{{ " + f"{name}" + " }}"


def _addFields(xFields, ff, skipList):
    for k, v in ff.items():
        if k in skipList:
            continue
        xFields[v] = _defaultFieldTemplate(k)


def _xFieldsDefault(ff):
    xFields = {
        "_": _mkDeleteLink("id"),
        "Name": _makeEditLink("id", "name"),
    }
    _addFields(xFields, ff, ["name"])
    return xFields


def getMyFields(app, fp):
    model = mapModel(app, fp)
    # print(model, file=sys.stderr)
    if not model:
        return {}

    ff = getFields(model.__name__).get("fields")
    # print(ff, file=sys.stderr)
    xList = getNavNames().keys()
    for name in xList:
        if fp.startswith(f"/{app}/{name}/"):
            return _xFieldsDefault(ff)

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
    # print(xFields, file=sys.stderr)

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
