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
    Tuple,
)


def _importItem(itemStr: str) -> Any:
    """Import a item from its module
    itemStr: str is in the format module.item
      where item itself could have ' in it
      as we only split on the first '.'

    we first split the string in module and item parts
    then import the module
    and from the module we import the item

    we returen the item or raise a error
    """

    module_path, itemName = itemStr.rsplit(".", 1)
    try:
        module = import_module(module_path)
        item = getattr(module, itemName)
    except (ImportError, AttributeError) as e:
        print(e, file=sys.stderr)
        raise ImportError(itemStr)

    return item


def _importClass(
    klassStr: str,
) -> Any:
    """Import a class from its module
    klassStr: str is in the format module.item
      where klass itself could have ' in it
      as we only split on the first '.'

    we first split the string in module and klass parts
    then import the module
    and from the module we import the klass

    we returen the klass or raise a error
    """

    module_path, class_name = klassStr.rsplit(".", 1)
    try:
        module = import_module(module_path)
        klass = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        print(e, file=sys.stderr)
        raise ImportError(klassStr)

    return klass


def _urlGenOne(
    app,
    index,
    form,
    nav: str,
) -> List[Any]:
    ll = [
        path(f"{app}/", index, name=f"{app}"),
        path(f"{app}/{nav}/", index, name=f"{app}_{nav}"),
        path(f"{app}/{nav}/add/", form, name=f"{app}_{nav}_add"),
        path(f"{app}/{nav}/edit/<uuid:id>", form, name=f"{app}_{nav}_edit"),
        path(f"{app}/{nav}/delete/<uuid:id>", form, name=f"{app}_{nav}_delete"),
    ]
    return ll


def _mkDeleteLink(
    pk: str,
):
    zz = [
        "<input",
        "   class='form-check-input'",
        "   type='checkbox'",
        f"  value='{pk}'" "   name='action{{ action_clean }}'",
        "  id='action{{ action_clean }}{{ " + f"{pk}" + "}}'",
        ">",
    ]
    return " ".join(zz)


def _makeEditLink(
    pk: str,
    name: str,
):
    what = "edit"
    return (
        "<a type='button' class='btn btn-sm btn-outline-info' href='{{ action_clean }}"
        + what
        + "/{{"
        + f"{pk}"
        + "}}'>&nbsp;</a>"
    )
    return "<a href='{{ action_clean }}" + what + "/{{" + f"{pk}" + "}}'>{{" + f"{name}" + "}}</a>"


def _defaultFieldTemplate(
    name,
):
    return "{{ " + f"{name}" + " }}"


def _addFields(
    xFields: Dict[str, Any],  # by ref so in and out
    ff,
    skipList,
) -> None:
    for k, v in ff.items():
        if k in skipList:
            continue
        xFields[v] = _defaultFieldTemplate(k)


def _addDefaultFields(
    ff,
) -> Dict[str, Any]:
    """
    Add extra columns for Delete: _D and Edit: _E
    """
    xFields: Dict[str, Any] = {
        "_D": _mkDeleteLink("id"),
        "_E": _makeEditLink("id", "id"),
    }
    _addFields(xFields, ff, [])
    return xFields


def _getMyFields(
    autoGuiDict: Dict[str, Any],
    app,
    fp,
):
    model = mapModel(autoGuiDict, app, fp)
    if not model:
        return {}

    fields: Dict[str, str] = getModelData2(
        autoGuiDict,
        model.__name__,
    ).get("fields")

    navNames = getNavNames(autoGuiDict).keys()
    for name in navNames:
        if fp.startswith(f"/{app}/{name}/"):
            return _addDefaultFields(fields)

    return {}


def _makeFieldsDictFromModel(
    autoGuiDict: Dict[str, Any],
    instance,
) -> Dict[str, Any]:
    ret: Dict[str, Any] = {}

    if not instance:
        return ret

    pk_name = "id"
    ret[pk_name] = getattr(instance, pk_name)

    modelName = instance.__class__.__name__
    fields = getModelData2(
        autoGuiDict,
        modelName,
    ).get("fields")
    for name in fields.keys():
        ret[name] = getattr(instance, name)

    return ret


def _makeHtmlRender(
    tempString,
    item,
):
    t = Template(tempString)
    c = Context(item)
    html = t.render(c)
    return html


# PUBLIC


def urlGenAll(
    autoGuiDict: Dict[str, Any],
    app: str,
    index,
    form,
) -> List[str]:
    xList = getNavNames(autoGuiDict).keys()
    urlPatternList = []
    for item in xList:
        z = _urlGenOne(app, index, form, item)
        urlPatternList += z

    return urlPatternList


def getModelData2(
    autoGuiDict: Dict[str, Any],
    modelName: str,
) -> Dict[str, str]:
    """get the fields for this model from the autoGuiDict"""
    k = "models"
    if modelName in autoGuiDict[k]:
        return autoGuiDict[k][modelName]
    return {}


def maxPerPagePaginate(
    autoGuiDict: Dict[str, Any],
) -> int:
    k = "max_per_page"
    if k in autoGuiDict:
        return int(autoGuiDict[k])
    return 15


def appNavigation(
    autoGuiDict: Dict[str, Any],
    app_name: str,
):
    # only create the nav for this app_name
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


def getNavNames(
    autoGuiDict: Dict[str, Any],
) -> Dict[str, str]:
    """from the given autoGuiDict extract all nav parts in each model
    autoGuiDict: Dict[str,Any]: we pass the auto Gui dict as it holds all info
    """
    ret: Dict[str, str] = {}
    k = "models"
    for name, v in autoGuiDict[k].items():
        if "nav" not in v:
            continue
        ret[v["nav"]] = name
    return ret


def mapForm(
    autoGuiDict: Dict[str, Any],
    app: str,
    fp: str,
    *args,
    **kwargs,
) -> Any:
    """
    autoGuiDict: Dict[str, Any]"
    app: str:
    fp: str:
    *args:
    **kwargs"

    """
    navDict = getNavNames(autoGuiDict)
    for nav, modelName in navDict.items():
        if fp.startswith(f"/{app}/{nav}/"):
            class_str = ".".join([app, "forms", modelName + "Form"])
            klass = _importClass(class_str)
            return klass(*args, **kwargs)
    return None


def mapModel(
    autoGuiDict: Dict[str, Any],
    app: str,
    fp,
) -> Any:
    """ """
    navDict = getNavNames(autoGuiDict)
    for nav, modelName in navDict.items():
        if fp.startswith(f"/{app}/{nav}/"):
            class_str = ".".join([app, "models", modelName])
            klass = _importClass(class_str)
            return klass
    return None


def getKnownApps():
    return ["aGit2Git"]


def addNavHome():
    data = {
        "url": "/",
        "label": "Home",
    }
    zz = []
    zz.append(data)
    return zz


def navigation():
    nav = {}

    nav["_home"] = addNavHome()

    # for all known apps create the nav for this app, add optional admin and home
    # return the nav as dict
    for app_name in getKnownApps():
        appAutoGuiDict = _importItem(".".join([app_name, "autoGui", "AUTO_GUI"]))
        if appAutoGuiDict:
            nav[app_name] = appNavigation(appAutoGuiDict, app_name)
    return nav


def getFilterPrefix():
    return "filter-"


def makeIndexFields(
    autoGuiDict: Dict[str, Any],
    app,
    fp,
    page_obj,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    myFields = _getMyFields(autoGuiDict, app, fp)

    data = []
    names = []

    if page_obj:
        for instance in page_obj:
            fieldData = _makeFieldsDictFromModel(autoGuiDict, instance)
            fieldData["action"] = fp
            fieldData["action_clean"] = fp.split("?")[0]

            fields = {}
            for name, v in myFields.items():
                if name not in names:
                    names.append(name)
                fields[name] = _makeHtmlRender(v, fieldData)
            data.append(fields)

    return names, data
