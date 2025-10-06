import sys

from typing import (
    Any,
    Dict,
)

from django.shortcuts import (
    render,
    redirect,
)

from django.core.paginator import Paginator

from appAutoGui.xauto import (
    map_model,
    map_form,
    make_index_field_names,
    make_index_fields,
    get_filter_prefix,
    get_model_data_from_autogui,
    max_per_page_paginate,
    navigation,
)


def with_debug() -> bool:
    return True


def _get_filter_hint(
    autogui_dict: Dict[str, Any],
    model_name: str,
    field_name: str,
) -> str:
    # return the filter hint we use to actually filter,
    # so we can use fk fields also to filter on
    fields = get_model_data_from_autogui(
        autogui_dict,
        model_name,
    )
    k = "filter"
    if k not in fields:  # this model has no filters defined in auto gui
        return None
    if field_name not in fields[k]:  # this field is not filtarable in auto gui
        return None

    return fields[k][field_name]


def _get_search_data_with_filter_applied(  # pylint:disable=R0917,disable=R0913
    index_path: str,
    autogui_dict: Dict[str, Any],
    model: Any,
    post_data: Any,
    filter_dict: Dict[str, Any],
    sort_dict: Dict[str, Any],
):
    """ """
    _ = index_path
    _ = post_data
    _ = sort_dict

    prefix = get_filter_prefix()
    filters: Dict[str, Any] = {}

    for filter_key, filter_value in filter_dict.items():
        if not filter_key.startswith(prefix):
            continue
        if not filter_value:
            continue

        filter_hint = _get_filter_hint(
            autogui_dict=autogui_dict,
            model_name=model.__name__,
            field_name=filter_key.split(prefix)[1],
        )
        if filter_hint:
            filters[f"{filter_hint}__icontains"] = filter_value

    # fetch the data from the database, apply all configured filters
    return model.objects.filter(
        **filters,
    )


def _split_path(
    full_path,
):
    if with_debug():
        print(f"full_path: |{full_path}|", file=sys.stderr)

    split_path_list = []
    if len(full_path) > 0:
        if len(full_path) > 1:
            split_path_list = full_path[1:][:-1].split("/")

    if with_debug():
        print(f"pathLen: {len(split_path_list)} :: {split_path_list}", file=sys.stderr)

    return split_path_list


def _start_context(
    autogui_dict,
    app_name: str,
    request,
) -> Dict[str, Any]:
    _ = autogui_dict
    _ = app_name
    full_path = request.get_full_path()

    title = str(full_path)
    action = full_path
    action_clean = full_path.split("?")[0]
    # nav = navigation(autogui_dict, app_name)
    nav = navigation()
    path = _split_path(full_path)

    if with_debug():
        print(f"path:: {path}", file=sys.stderr)
        print(f"action:: {action}", file=sys.stderr)
        print(f"action_clean:: {action_clean}", file=sys.stderr)
        print(f"navigation:: {nav}", file=sys.stderr)

    # currently only the first 2 elements can be link, and possibly the last after edit has been seen
    zpath = action_clean[1:][:-1].split("/")
    x_path = {}
    n = 0
    for idx, x in enumerate(zpath):
        if n < 2:
            x_path[x] = "/" + "/".join(zpath[: (idx + 1)]) + "/"
        else:
            x_path[x] = ""
        n += 1
        if with_debug():
            print(x, x_path[x], file=sys.stderr)

    context = {
        "title": title,
        "action": action,
        "action_clean": action_clean,
        "navigation": nav,
        "path": path,
        "x_path": x_path,
    }
    return context


def _get_post_data(request):
    post_data = {}
    if request.method == "POST":
        post_data = request.POST
    return post_data


def _delete_and_redirect(
    model,
    post_data,
    full_path,
):
    instance = model.objects.get(id=post_data["delete"])
    instance.delete()
    fp3 = full_path.replace("/delete/", "/")
    fp3 = fp3.replace(post_data["delete"], "")
    return redirect(f"{fp3}")


def _do_valid_form(
    my_form,
    post_data,
    full_path,
    k,
    **kwargs,
):
    item = my_form.save()
    if k not in kwargs:  # no id field: we are adding
        if "_addanother" in post_data:
            return redirect(f"{full_path}")

        if "_continue" in post_data:
            fp2 = full_path.replace("/add/", "/edit/")
            return redirect(f"{fp2}{item.id}")
    else:  # we have id we are editing (delete was already done)
        if "_addanother" in post_data:
            fp2 = full_path.split("/edit/")[0] + "/add/"
            return redirect(f"{fp2}")

    return None


def _form_init(  # pylint:disable=W1113
    k,
    request,
    app_name=None,
    autogui_dict=None,
    *args,
    **kwargs,
):
    _ = args
    if autogui_dict is None:
        autogui_dict = {}

    full_path = request.get_full_path()
    if with_debug():
        print(f"full_path: {full_path}", file=sys.stderr)

    model = map_model(autogui_dict, app_name, full_path)
    if with_debug():
        print(f"model: {model}", file=sys.stderr)

    post_data = _get_post_data(request)
    if with_debug():
        print(f"post_data: {post_data}", file=sys.stderr)

    split_path_list = _split_path(full_path)
    what = None
    if len(split_path_list) > 2:
        what = split_path_list[2]

    xid = _get_primary_key(k, **kwargs)
    model_data = get_model_data(model, xid)
    if model_data:
        # if we have data we can fill the form with the current data
        my_form = map_form(
            autogui_dict,
            app_name,
            full_path,
            instance=model_data,
        )
    else:
        # otherwise start a empty form
        my_form = map_form(
            autogui_dict,
            app_name,
            full_path,
            None,
        )

    if with_debug():
        print(f"my_form 0: {my_form} {model_data}", file=sys.stderr)

    return model, my_form, post_data, full_path, what, model_data, xid


def _get_primary_key(
    k,
    **kwargs,
):
    xid = None
    if k in kwargs:
        xid = kwargs[k]
        if with_debug():
            print(f"{k} exists: {xid}", file=sys.stderr)
    return xid


def _do_render_form_data(  # pylint:disable=R0917,disable=R0913
    request,
    app_name,
    autogui_dict,
    full_path,
    my_form,
    xid,
    what,
):
    path = _split_path(full_path)

    deleting = True if what == "delete" else False
    updating = True if what == "edit" else False

    x_del = "/".join(["", path[0], path[1], "delete", str(xid)]) if xid else None

    c1 = _start_context(autogui_dict, app_name, request)
    c2 = {
        "form": my_form,
        "id": xid,
        "delete": x_del,
        "deleting": deleting,
        "updating": updating,
    }

    context = c1 | c2  # merge the dicts

    return render(
        request,
        f"{app_name}/form.html",
        context,
    )


def _do_add_item(  # pylint:disable=R0917,disable=R0913
    k,
    model,
    my_form,
    post_data,
    full_path,
    what,
    model_data,
    xid,
    request,
    autogui_dict,
    app_name,
    **kwargs,
):
    # asser we have model
    # assert we have my_form
    # assert no xid, no model_data
    # ading a new item, we have no id yet

    _ = model
    _ = model_data

    if post_data:
        my_form = map_form(
            autogui_dict,
            app_name,
            full_path,
            post_data,
        )
        if with_debug():
            print(f"my_form 4: {my_form}", file=sys.stderr)

        if my_form.is_valid():
            resp = _do_valid_form(
                my_form,
                post_data,
                full_path,
                k,
                **kwargs,
            )
            if resp:
                return resp

    return _do_render_form_data(
        request,
        app_name,
        autogui_dict,
        full_path,
        my_form,
        xid,
        what,
    )


def _do_edit_item(  # pylint:disable=R0917,disable=R0913
    k,
    model,
    my_form,
    post_data,
    full_path,
    what,
    model_data,
    xid,
    request,
    autogui_dict,
    app_name,
    **kwargs,
):
    _ = model
    if post_data:
        if model_data:
            # update the form with the newly posted data
            my_form = map_form(
                autogui_dict,
                app_name,
                full_path,
                post_data,
                instance=model_data,
            )
            if with_debug():
                print(f"my_form 2: {my_form}", file=sys.stderr)

            if my_form.is_valid():
                resp = _do_valid_form(
                    my_form,
                    post_data,
                    full_path,
                    k,
                    **kwargs,
                )
                if resp:
                    return resp

    return _do_render_form_data(
        request,
        app_name,
        autogui_dict,
        full_path,
        my_form,
        xid,
        what,
    )


def _do_delete_item(  # pylint:disable=R0917,disable=R0913
    k,
    model,
    my_form,
    post_data,
    full_path,
    what,
    model_data,
    xid,
    request,
    autogui_dict,
    app_name,
    **kwargs,
):
    _ = k
    _ = model_data
    _ = kwargs

    if "delete" in post_data:
        return _delete_and_redirect(
            model,
            post_data,
            full_path,
        )

    return _do_render_form_data(
        request,
        app_name,
        autogui_dict,
        full_path,
        my_form,
        xid,
        what,
    )


# PUBLIC


def get_model_data(
    model,
    xid,
):
    """
    fetch the data from a mode and a pk
    """
    model_data = None
    if model and xid:
        model_data = model.objects.get(pk=xid)
        if with_debug():
            print(f"model_data: {model_data}", file=sys.stderr)
    return model_data


def do_paging_with_search_filters():
    pass


def do_per_page(
    request: Any,
    autogui_dict: Dict[str, Any],
    post_data: Any,
) -> int | None:
    max_per_page = max_per_page_paginate(autogui_dict)

    if autogui_dict is None or len(autogui_dict) == 0:
        return None

    per_page = None
    k = "per_page"
    if k in request.session:
        per_page = request.session.get(k)

    k2 = "perPage2"
    for j in [k, k2]:
        z = post_data.get(j)
        if z:
            if int(z) != request.session[k]:
                per_page = int(z)
                per_page = max(per_page, 0)
                per_page = min(per_page, 1000)

    if per_page is None:
        per_page = max_per_page

    request.session[k] = per_page  # set the new per page in the session
    return per_page


def get_filter_dict_info(
    index_path: str,
    request: Any,
    field_names: Dict[str, Any],
) -> Dict[str, Any]:
    filter_prefix = get_filter_prefix()
    post_data = _get_post_data(request)

    filter_dict = {}
    session_key = f"{index_path}filter_dict"
    # -----------------------------------
    # if exist start with the current sesion data
    if request.session.get(session_key, False):
        filter_dict = request.session.get(session_key)

    if with_debug():
        print("FilterSession OLD", session_key, filter_dict, file=sys.stderr)

    # -----------------------------------
    filter_dict[f"{filter_prefix}_D"] = None
    filter_dict[f"{filter_prefix}_E"] = None

    for name, label in field_names.items():
        _ = label
        filter_key = f"{filter_prefix}{name}"
        if filter_key not in filter_dict:
            filter_dict[filter_key] = None

        v = post_data.get(filter_key)
        if v:
            filter_dict[filter_key] = v  # we now have a copy of the post data in filter dict
            if v == "*":
                filter_dict[filter_key] = None

    if with_debug():
        print("FilterSession New", session_key, filter_dict, file=sys.stderr)

    request.session[session_key] = filter_dict
    return filter_dict


def _get_current_page_data(  # pylint:disable=R0917,disable=R0913
    page_number: int,
    per_page: int,
    index_path: str,
    autogui_dict: Dict[str, Any],
    model: Any,
    post_data: Any,
    filter_dict: Dict[str, Any],
    sort_dict: Dict[str, Any],
) -> Any:
    item_list = _get_search_data_with_filter_applied(
        index_path=index_path,
        autogui_dict=autogui_dict,
        model=model,
        post_data=post_data,
        filter_dict=filter_dict,
        sort_dict=sort_dict,
    )
    paginator = Paginator(
        item_list,
        per_page,
    )

    return paginator.get_page(page_number)


def make_index_path(
    request: Any,
) -> str:
    full_path = request.get_full_path()
    index_path = full_path
    split_path_list = _split_path(full_path)

    if len(split_path_list) > 2:
        index_path = "/" + "/".join(split_path_list[:2]) + "/"

    return index_path


def generic_index(  # pylint:disable= R0914
    autogui_dict,
    app_name,
    request,
    *args,
    **kwargs,
):
    index_path = make_index_path(request=request)

    _ = args
    _ = kwargs

    model = None
    if autogui_dict and len(autogui_dict) and app_name:
        model = map_model(
            autogui_dict,
            app_name,
            index_path,
        )

    field_names = {}
    if model:
        field_names = get_model_data_from_autogui(
            autogui_dict,
            model.__name__,
        ).get(
            "fields",
        )

    post_data = _get_post_data(request)
    per_page = do_per_page(
        request,
        autogui_dict,
        post_data,  # we are looking for page size info and page offset
    )

    names = make_index_field_names(
        autogui_dict,
        app_name,
        index_path,
    )

    page_obj = None
    page_data = []
    filter_dict = {}
    sort_dict = {}
    if model:
        page_number = request.GET.get("page")

        # --- filter
        filter_dict = get_filter_dict_info(
            index_path,
            request,
            field_names,
        )
        #         # --- sort
        #         if request.session.get('sort'):
        #             sort_dict = request.session.get('sort')
        #
        #         for colName in names:
        #             x = request.GET.get('sort')
        #             if x:
        #             sort_dict[colName] = "-"
        #         request.session['sort'] = sort_dict

        # --- get data
        # get the current page of data we are about to prepare for display
        page_obj = _get_current_page_data(
            page_number=page_number,
            per_page=per_page,
            index_path=index_path,
            autogui_dict=autogui_dict,
            model=model,
            post_data=post_data,
            filter_dict=filter_dict,
            sort_dict=sort_dict,
        )
    # --- get page data
    if page_obj:
        page_data = make_index_fields(
            autogui_dict,
            app_name,
            index_path,
            page_obj,  # the one page we will show
        )

    # ---- prepare for display
    c1 = _start_context(
        autogui_dict,
        app_name,
        request,
    )
    c2 = {
        "perPage": per_page,
        "page_obj": page_obj,
        "data": page_data,
        "colNames": names,
        "postData": post_data,
        "filter": filter_dict,
        "sort": sort_dict,
    }
    context = c1 | c2  # merge the dicts

    return render(
        request,
        f"{app_name}/index.html",
        context,
    )


# @login_required
def generic_form(
    autogui_dict,
    app_name,
    request,
    *args,
    **kwargs,
):
    # request.session
    k = "id"
    model, my_form, post_data, full_path, what, model_data, xid = _form_init(
        k,
        request,
        app_name,
        autogui_dict,
        *args,
        **kwargs,
    )

    if what == "add":
        # we see add as get and as post
        return _do_add_item(
            k,
            model,
            my_form,
            post_data,
            full_path,
            what,
            model_data,
            xid,
            request,
            autogui_dict,
            app_name,
            **kwargs,
        )

    if what == "delete":
        # we see delete as get and as post
        return _do_delete_item(
            k,
            model,
            my_form,
            post_data,
            full_path,
            what,
            model_data,
            xid,
            request,
            autogui_dict,
            app_name,
            **kwargs,
        )

    if what == "edit":
        return _do_edit_item(
            k,
            model,
            my_form,
            post_data,
            full_path,
            what,
            model_data,
            xid,
            request,
            autogui_dict,
            app_name,
            **kwargs,
        )

    if what == "sort":
        return None

    # not add, edit or delete, sort
    if with_debug():
        print("not one of [add, edit, delete, sort]", file=sys.stderr)

    return _do_render_form_data(
        request,
        app_name,
        autogui_dict,
        full_path,
        my_form,
        xid,
        what,
    )
