import sys
from importlib import import_module

from django.urls import path

from django.template import (
    Context,
    Template,
)

from typing import (
    Any,
    Dict,
    List,
)


def getNavNames(autoGuiDict) -> Dict[str, str]:
    ret = {}
    k = "models"
    for name, v in autoGuiDict[k].items():
        if "nav" not in v:
            continue
        ret[v["nav"]] = name
    return ret


def _urlGenOne(app, index, form, nav: str):
    ll = [
        path(f"{app}/{nav}/", index, name=f"{app}_{nav}"),
        path(f"{app}/{nav}/add/", form, name=f"{app}_{nav}_add"),
        path(f"{app}/{nav}/edit/<uuid:id>", form, name=f"{app}_{nav}_edit"),
        path(f"{app}/{nav}/delete/<uuid:id>", form, name=f"{app}_{nav}_delete"),
    ]
    return ll


def urlGenAll(autoGuiDict, app: str, index, form) -> List[str]:
    xList = getNavNames(autoGuiDict).keys()
    urlPatternList = []
    for item in xList:
        z = _urlGenOne(app, index, form, item)
        urlPatternList += z

    return urlPatternList


def getFields(autoGuiDict, modelName: str) -> Dict[str, str]:
    k = "models"
    if modelName in autoGuiDict[k]:
        return autoGuiDict[k][modelName]
    return {}


def maxPerPagePaginate(autoGuiDict) -> int:
    k = "max_per_page"
    if k in autoGuiDict:
        return int(autoGuiDict[k])
    return 15


def navigation(autoGuiDict: Dict[str, Any], app_name: str):
    zz = autoGuiDict.get("navigation")
    rr = []
    if zz:
        for k, v in zz.items():
            data = {
                "url": "/" + app_name + "/" + v + "/",
                "label": k,
            }
            rr.append(data)
    return rr


def importClass(klassStr):
    module_path, class_name = klassStr.rsplit(".", 1)
    try:
        module = import_module(module_path)
        klass = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        print(e, file=sys.stderr)
        raise ImportError(klassStr)

    return klass


def mapForm(autoGuiDict, app: str, fp: str, *args, **kwargs) -> Any:
    xList = getNavNames(autoGuiDict)
    for nav, modelName in xList.items():
        if fp.startswith(f"/{app}/{nav}/"):
            class_str = ".".join([app, "forms", modelName + "Form"])
            klass = importClass(class_str)
            return klass(*args, **kwargs)
    return None


def mapModel(autoGuiDict, app: str, fp):
    xList = getNavNames(autoGuiDict)
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


def _getMyFields(autoGuiDict, app, fp):
    model = mapModel(autoGuiDict, app, fp)
    if not model:
        return {}

    ff = getFields(autoGuiDict, model.__name__).get("fields")
    xList = getNavNames(autoGuiDict).keys()
    for name in xList:
        if fp.startswith(f"/{app}/{name}/"):
            return _xFieldsDefault(ff)

    return {}


def _makeDictFromModel(autoGuiDict, instance):
    ret = {}
    if not instance:
        return ret

    modelName = instance.__class__.__name__
    name = "id"
    ret[name] = getattr(instance, name)
    ff = getFields(autoGuiDict, modelName).get("fields")
    for name in ff.keys():
        ret[name] = getattr(instance, name)

    return ret


def getFilterPrefix():
    return "filter-"


def makeIndexFields(autoGuiDict, app, fp, page_obj):
    def test1(tempString, item):
        t = Template(tempString)
        c = Context(item)
        html = t.render(c)
        return html

    xFields = _getMyFields(autoGuiDict, app, fp)

    data = []
    names = []
    if page_obj:
        for item in page_obj:
            fieldData = _makeDictFromModel(autoGuiDict, item)
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
