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


def _importItem(
    itemStr: str,
) -> Any:
    """Import a item from its module
    itemStr: str is in the format module.item
      where item itself could have ' in it
      as we only split on the first '.'

    we first split the string in module and item parts
    then import the module
    and from the module we import the item

    we return the item or raise a error
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
    navName: str,
) -> List[Any]:
    """
    generate all CRUD urls for one (app,navName)
    """
    ll = [
        path(f"{app}/", index, name=f"{app}"),
        path(f"{app}/{navName}/", index, name=f"{app}_{navName}"),
        path(f"{app}/{navName}/add/", form, name=f"{app}_{navName}_add"),
        path(f"{app}/{navName}/sort/<str:name>", index, name=f"{app}_{navName}_sort"),
        path(f"{app}/{navName}/edit/<uuid:id>", form, name=f"{app}_{navName}_edit"),
        path(f"{app}/{navName}/delete/<uuid:id>", form, name=f"{app}_{navName}_delete"),
    ]
    return ll


def _mkIndexDeleteLink(
    pk: str,
):
    """
    Make a link
      that will request
        a delete of an item
            by its primary key
    """
    zz = [
        "<input",
        " class='form-check-input'",
        " type='checkbox'",
        f" value='{pk}'",
        " name='action{{ action_clean }}'",
        " id='action{{ action_clean }}{{ " + f"{pk}" + "}}'",
        ">",
    ]
    return " ".join(zz)


def _mkIndexEditLink(
    pk: str,
    name: str,
):
    """
    Make a link
      that will request
        a edit of an item
            by its primary key
    """

    s = "".join(
        [
            "<a",
            " type='button'",
            " class='btn btn-sm btn-outline-dark'",
            " href='{{ action_clean }}" + "edit/{{" + f"{pk}" + "}}'",
            ">",
            "&nbsp;",
            "</a>",
        ],
    )
    return s


def _defaultIndexFieldTemplate(
    name,
):
    return "{{ " + f"{name}" + " }}"


def _addIndexFields(
    xFields: Dict[str, Any],  # by ref so in and out
    model_fields,
    skipList,
) -> None:
    if model_fields:
        for k, v in model_fields.items():
            if k in skipList:
                continue
            xFields[v] = _defaultIndexFieldTemplate(k)


def _addDefaultIndexFields(
    model_fields,
) -> Dict[str, Any]:
    """
    Add extra columns for Delete: _D and Edit: _E
    """
    xFields: Dict[str, Any] = {
        "_D": _mkIndexDeleteLink("id"),
        "_E": _mkIndexEditLink("id", "id"),
    }
    _addIndexFields(
        xFields=xFields,
        model_fields=model_fields,
        skipList=[],
    )
    return xFields


def _getMyIndexFields(
    autogui_dict: Dict[str, Any],
    app_name: str,
    index_path: str,
):
    if len(autogui_dict) == 0:
        return {}

    model = mapModel(
        autogui_dict,
        app_name,
        index_path,
    )
    if not model:
        return {}

    model_fields: Dict[str, str] = getModelData2(
        autogui_dict,
        model.__name__,
    ).get("fields")

    navNames = getNavNames(autogui_dict).keys()
    for name in navNames:
        if index_path.startswith(f"/{app_name}/{name}/"):
            return _addDefaultIndexFields(model_fields)

    return {}


def _makeFieldsDictFromModel(
    autogui_dict: Dict[str, Any],
    instance,
) -> Dict[str, Any]:
    ret: Dict[str, Any] = {}

    if not instance:
        return ret

    pk_name = "id"
    ret[pk_name] = getattr(instance, pk_name)

    modelName = instance.__class__.__name__
    fields = getModelData2(
        autogui_dict,
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
    autogui_dict: Dict[str, Any],
    app_name: str,
    index,
    form,
) -> List[str]:
    if len(autogui_dict) == 0:
        return []

    urlPatternList = []
    navNameList = getNavNames(autogui_dict).keys()
    for navName in navNameList:
        z = _urlGenOne(
            app_name,
            index,
            form,
            navName,
        )
        urlPatternList += z

    return urlPatternList


def getModelData2(
    autogui_dict: Dict[str, Any],
    modelName: str,
) -> Dict[str, str]:
    print(autogui_dict  , modelName, file=sys.stderr)

    """get the fields for this model from the autogui_dict"""
    k = "models"
    if modelName in autogui_dict[k]:
        return autogui_dict[k][modelName]
    return {}


def maxPerPagePaginate(
    autogui_dict: Dict[str, Any],
) -> int:
    k = "max_per_page"
    if k in autogui_dict:
        return int(autogui_dict[k])
    return 15


def appNavigation(
    autogui_dict: Dict[str, Any],
    app_name: str,
) -> List[Dict[str, str]]:
    """only create the nav for this app_name"""
    rr = []
    zz = autogui_dict.get("navigation")
    if zz:
        for k, v in zz.items():
            data = {
                "url": "/" + app_name + "/" + v + "/",
                "label": k,
            }
            rr.append(data)
    return rr


def getNavNames(
    autogui_dict: Dict[str, Any],
) -> Dict[str, str]:
    """from the given autogui_dict extract all nav parts in each model
    autogui_dict: Dict[str,Any]: we pass the auto Gui dict as it holds all info
    """
    ret: Dict[str, str] = {}
    k = "models"
    for name, v in autogui_dict[k].items():
        if "nav" not in v:
            continue
        ret[v["nav"]] = name
    return ret


def mapForm(
    autogui_dict: Dict[str, Any],
    app_name: str,
    fp: str,
    *args,
    **kwargs,
) -> Any:
    """
    autogui_dict: Dict[str, Any]"
    app_name: str:
    fp: str:
    *args:
    **kwargs"

    """
    if len(autogui_dict) == 0:
        return None

    navDict = getNavNames(autogui_dict)
    for nav, modelName in navDict.items():
        if fp.startswith(f"/{app_name}/{nav}/"):
            class_str = ".".join(
                [
                    app_name,
                    "forms",
                    modelName + "Form",
                ],
            )
            klass = _importClass(class_str)
            return klass(*args, **kwargs)
    return None


def mapModel(
    autogui_dict: Dict[str, Any],
    app_name: str,
    fp,
) -> Any:
    """ """
    if len(autogui_dict) == 0:
        return None

    navDict = getNavNames(autogui_dict)
    for nav, modelName in navDict.items():
        if fp.startswith(f"/{app_name}/{nav}/"):
            class_str = ".".join(
                [
                    app_name,
                    "models",
                    modelName,
                ],
            )
            klass = _importClass(class_str)
            return klass
    return None


def getKnownApps():
    return ["aGit2Git"]  # todo: currently hardcoded


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
        appAutoGuiDict = _importItem(
            ".".join(
                [
                    app_name,
                    "autoGui",
                    "AUTO_GUI",
                ],
            ),
        )
        if appAutoGuiDict:
            nav[app_name] = appNavigation(appAutoGuiDict, app_name)
    return nav


def getFilterPrefix() -> str:
    return "filter-"


def makeIndexFieldNames(
    autogui_dict: Dict[str, Any],
    app_name: str,
    index_path: str,
) -> List[str]:
    names = []
    myFields = _getMyIndexFields(
        autogui_dict,
        app_name,
        index_path,
    )
    for name, _ in myFields.items():
        if name not in names:
            names.append(name)

    return names


def makeIndexFields(
    autogui_dict: Dict[str, Any],
    app_name: str,
    index_path: str,
    page_obj,
) -> Tuple[
    List[str],
    List[Dict[str, Any]],
]:
    data = []
    names = makeIndexFieldNames(autogui_dict, app_name, index_path)
    if page_obj:
        myFields = _getMyIndexFields(autogui_dict, app_name, index_path)
        for instance in page_obj:
            fieldData = _makeFieldsDictFromModel(
                autogui_dict,
                instance,
            )
            fieldData["action"] = index_path
            fieldData["action_clean"] = index_path.split("?")[0]

            fields = {}
            for name, v in myFields.items():
                fields[name] = _makeHtmlRender(
                    v,
                    fieldData,
                )
            data.append(fields)

    return names, data
