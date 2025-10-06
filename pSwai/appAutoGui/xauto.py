from typing import (
    Any,
    Dict,
    List,
)

import sys
from importlib import import_module
from django.urls import path
from django.template import (
    Context,
    Template,
)


def _import_item(
    item_str: str,
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

    module_path, item_name = item_str.rsplit(".", 1)
    try:
        module = import_module(module_path)
        item = getattr(module, item_name)
    except (ImportError, AttributeError) as e:
        print(e, file=sys.stderr)
        raise ImportError(item_str) from e

    return item


def _import_class(
    klass_str: str,
) -> Any:
    """Import a class from its module
    klass_str: str is in the format module.item
      where klass itself could have ' in it
      as we only split on the first '.'

    we first split the string in module and klass parts
    then import the module
    and from the module we import the klass

    we returen the klass or raise a error
    """

    module_path, class_name = klass_str.rsplit(".", 1)
    try:
        module = import_module(module_path)
        klass = getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        print(e, file=sys.stderr)
        raise ImportError(klass_str) from e

    return klass


def _url_gen_one(
    app,
    index,
    form,
    nav_name: str,
) -> List[Any]:
    """
    generate all CRUD urls for one (app,nav_name)
    """
    ll = [
        path(f"{app}/", index, name=f"{app}"),
        path(f"{app}/{nav_name}/", index, name=f"{app}_{nav_name}"),
        path(f"{app}/{nav_name}/add/", form, name=f"{app}_{nav_name}_add"),
        path(f"{app}/{nav_name}/sort/<str:name>", index, name=f"{app}_{nav_name}_sort"),
        path(f"{app}/{nav_name}/edit/<uuid:id>", form, name=f"{app}_{nav_name}_edit"),
        path(f"{app}/{nav_name}/delete/<uuid:id>", form, name=f"{app}_{nav_name}_delete"),
    ]
    return ll


def _mk_index_delete_link(
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


def _mk_index_edit_link(
    pk: str,
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


def _default_index_field_template(
    name,
):
    return "{{ " + f"{name}" + " }}"


def _add_index_fields(
    i_fields: Dict[str, Any],  # by ref so in and out
    model_fields,
    skip_list,
) -> None:
    if model_fields:
        for k, v in model_fields.items():
            if k in skip_list:
                continue
            i_fields[v] = _default_index_field_template(k)


def _add_default_index_fields(
    model_fields,
) -> Dict[str, Any]:
    """
    Add extra columns for Delete: _D and Edit: _E
    """
    i_fields: Dict[str, Any] = {
        "_D": _mk_index_delete_link("id"),
        "_E": _mk_index_edit_link("id"),
    }
    _add_index_fields(
        i_fields=i_fields,
        model_fields=model_fields,
        skip_list=[],
    )
    return i_fields


def _get_nav_names(
    autogui_dict: Dict[str, Any],
) -> Dict[str, str]:
    """from the given autogui_dict extract all nav parts in each model
    autogui_dict: Dict[str,Any]: we pass the auto Gui dict as it holds all info
    """
    ret: Dict[str, str] = {}
    k = "models"
    for model_name, ag_model_dict in autogui_dict[k].items():
        if "nav" not in ag_model_dict:
            continue
        nav_name = ag_model_dict["nav"]
        ret[nav_name] = model_name
    return ret


def _get_my_index_fields(
    autogui_dict: Dict[str, Any],
    app_name: str,
    index_path: str,
):
    if len(autogui_dict) == 0:
        return {}

    model = map_model(
        autogui_dict,
        app_name,
        index_path,
    )
    if not model:
        return {}

    model_fields: Dict[str, str] = get_model_data_from_autogui(
        autogui_dict,
        model.__name__,
    ).get("fields")

    nav_names = _get_nav_names(autogui_dict).keys()
    for name in nav_names:
        if index_path.startswith(f"/{app_name}/{name}/"):
            return _add_default_index_fields(
                model_fields,
            )

    return {}


def _make_fields_dict_from_model(
    autogui_dict: Dict[str, Any],
    instance,
) -> Dict[str, Any]:
    ret: Dict[str, Any] = {}

    if not instance:
        return ret

    pk_name = "id"
    ret[pk_name] = getattr(instance, pk_name)

    model_name = instance.__class__.__name__
    fields = get_model_data_from_autogui(
        autogui_dict,
        model_name,
    ).get("fields")

    for name in fields.keys():
        ret[name] = getattr(instance, name)

    return ret


def _make_html_render(
    temp_string,
    item,
):
    t = Template(temp_string)
    c = Context(item)
    html = t.render(c)
    return html


# PUBLIC


def url_gen_all(
    autogui_dict: Dict[str, Any],
    app_name: str,
    index,
    form,
) -> List[str]:
    if len(autogui_dict) == 0:
        return []

    url_pattern_list = []
    nav_name_list = _get_nav_names(autogui_dict).keys()
    for nav_name in nav_name_list:
        z = _url_gen_one(
            app_name,
            index,
            form,
            nav_name,
        )
        url_pattern_list += z

    return url_pattern_list


def get_model_data_from_autogui(
    autogui_dict: Dict[str, Any],
    model_name: str,
) -> Dict[str, str]:
    """get the fields for this model from the autogui_dict"""
    k = "models"
    if model_name in autogui_dict[k]:
        return autogui_dict[k][model_name]
    return {}


def max_per_page_paginate(
    autogui_dict: Dict[str, Any],
) -> int:
    k = "max_per_page"
    if k in autogui_dict:
        return int(autogui_dict[k])
    return 15


def app_navigation(
    autogui_dict: Dict[str, Any],
    app_name: str,
) -> List[Dict[str, str]]:
    """only create the nav for this app_name"""
    nav_list = []
    nav = autogui_dict.get("navigation")
    if nav:
        for label, internal_name in nav.items():
            data = {
                "url": "/" + app_name + "/" + internal_name + "/",
                "label": label,
            }
            nav_list.append(data)
    return nav_list


def map_form(
    autogui_dict: Dict[str, Any],
    app_name: str,
    form_path: str,
    *args,
    **kwargs,
) -> Any:
    """
    autogui_dict: Dict[str, Any]"
    app_name: str:
    form_path: str:
    *args:
    **kwargs"

    """
    if len(autogui_dict) == 0:
        return None

    nav_dict = _get_nav_names(autogui_dict)
    for nav_name, model_name in nav_dict.items():
        if form_path.startswith(f"/{app_name}/{nav_name}/"):
            class_str = ".".join(
                [
                    app_name,
                    "forms",
                    model_name + "Form",
                ],
            )
            klass = _import_class(class_str)
            return klass(*args, **kwargs)
    return None


def map_model(
    autogui_dict: Dict[str, Any],
    app_name: str,
    index_path,
) -> Any:
    """ """
    if len(autogui_dict) == 0:
        return None

    nav_dict = _get_nav_names(autogui_dict)
    for nav, model_name in nav_dict.items():
        if index_path.startswith(f"/{app_name}/{nav}/"):
            class_str = ".".join(
                [
                    app_name,
                    "models",
                    model_name,
                ],
            )
            klass = _import_class(class_str)
            return klass
    return None


def get_known_apps():
    return ["aGit2Git"]  # to_do: currently hardcoded


def _add_nav_home():
    data = {
        "url": "/",
        "label": "Home",
    }
    zz = []
    zz.append(data)
    return zz


def navigation():
    # for all known apps create the nav for this app, add optional admin and home
    # return the nav as dict

    nav = {}
    nav["_home"] = _add_nav_home()

    for app_name in get_known_apps():
        # if the app has a auto_gui defined we can add its navigation data to the final navigation {}
        autogui_dict = _import_item(
            ".".join(
                [
                    app_name,
                    "autoGui",
                    "AUTO_GUI",
                ],
            ),
        )
        if autogui_dict:
            nav[app_name] = app_navigation(
                autogui_dict,
                app_name,
            )

    return nav


def get_filter_prefix() -> str:
    return "filter-"


def make_index_field_names(
    autogui_dict: Dict[str, Any],
    app_name: str,
    index_path: str,
) -> List[str]:
    names = []
    my_fields = _get_my_index_fields(
        autogui_dict,
        app_name,
        index_path,
    )
    for name, _ in my_fields.items():
        if name not in names:
            names.append(name)

    return names


def make_index_fields(
    autogui_dict: Dict[str, Any],
    app_name: str,
    index_path: str,
    page_obj,
) -> List[Dict[str, Any]]:
    data = []
    if page_obj:
        my_fields = _get_my_index_fields(
            autogui_dict,
            app_name,
            index_path,
        )
        for instance in page_obj:
            field_data = _make_fields_dict_from_model(
                autogui_dict,
                instance,
            )
            field_data["action"] = index_path
            field_data["action_clean"] = index_path.split("?")[0]

            fields = {}
            for name, v in my_fields.items():
                fields[name] = _make_html_render(
                    v,
                    field_data,
                )
            data.append(fields)

    return data
