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
    mapModel,
    mapForm,
    makeIndexFieldNames,
    makeIndexFields,
    getFilterPrefix,
    getModelData2,
    maxPerPagePaginate,
    navigation,
)


def debugOn() -> bool:
    return True


def _getFilterHint(
    autogui_dict: Dict[str, Any],
    modelName: str,
    fieldName: str,
) -> str:
    # return the filter hint we use to actually filter,
    # so we can use fk fields also to filter on
    fields = getModelData2(
        autogui_dict,
        modelName,
    )
    k = "filter"

    if k not in fields:
        return None

    if fieldName not in fields[k]:
        return None

    return fields[k][fieldName]


def _doOneIndexItem(
    autogui_dict,
    model,
    postdata_key,
    postdata_value,
    prefix,
) -> str | None:
    """
    remove the filter prefix leaving the field name
    and then see if we can filter on this field in autoGui
    """
    if not postdata_value:
        return None

    fieldName = postdata_key.split(prefix)[1]
    return _getFilterHint(
        autogui_dict=autogui_dict,
        modelName=model.__name__,
        fieldName=fieldName,
    )


def _getSearchDataWithFilterApplied(
    index_path: str,
    autogui_dict: Dict[str, Any],
    model: Any,
    postData: Any,
):
    """ """
    prefix = getFilterPrefix()
    filterDict = {}

    for postdata_key, postdata_value in postData.items():
        if not postdata_key.startswith(prefix):
            continue

        filter_hint = _doOneIndexItem(
            autogui_dict,
            model,
            postdata_key,
            postdata_value,
            prefix,
        )
        if filter_hint:
            filterDict[f"{filter_hint}__icontains"] = postdata_value

    return model.objects.filter(
        **filterDict,
    )


def _splitPath(
    fill_path,
):
    if debugOn():
        print(f"fill_path: |{fill_path}|", file=sys.stderr)

    splitPath = []
    if len(fill_path) > 0:
        if len(fill_path) > 1:
            splitPath = fill_path[1:][:-1].split("/")

    if debugOn():
        print(f"pathLen: {len(splitPath)} :: {splitPath}", file=sys.stderr)

    return splitPath


def _startContext(
    autogui_dict,
    app_name: str,
    request,
) -> Dict[str, Any]:
    fill_path = request.get_full_path()

    title = str(fill_path)
    action = fill_path
    action_clean = fill_path.split("?")[0]
    # nav = navigation(autogui_dict, app_name)
    nav = navigation()
    path = _splitPath(fill_path)

    if debugOn():
        print(f"path:: {path}", file=sys.stderr)
        print(f"action:: {action}", file=sys.stderr)
        print(f"action_clean:: {action_clean}", file=sys.stderr)
        print(f"navigation:: {nav}", file=sys.stderr)

    # currently only the first 2 elements can be link, and possibly the last after edit has been seen
    zpath = action_clean[1:][:-1].split("/")
    xPath = {}
    n = 0
    for idx, x in enumerate(zpath):
        if n < 2:
            xPath[x] = "/" + "/".join(zpath[: (idx + 1)]) + "/"
        else:
            xPath[x] = ""
        n += 1
        if debugOn():
            print(x, xPath[x], file=sys.stderr)

    context = {
        "title": title,
        "action": action,
        "action_clean": action_clean,
        "navigation": nav,
        "path": path,
        "xPath": xPath,
    }
    return context


def _getPostData(request):
    postData = {}
    if request.method == "POST":
        postData = request.POST
    return postData


def _deleteAndRedirect(
    model,
    postData,
    fill_path,
):
    instance = model.objects.get(id=postData["delete"])
    instance.delete()
    fp3 = fill_path.replace("/delete/", "/")
    fp3 = fp3.replace(postData["delete"], "")
    return redirect(f"{fp3}")


def _doValidForm(
    myForm,
    postData,
    fill_path,
    k,
    **kwargs,
):
    item = myForm.save()
    if k not in kwargs:  # no id field: we are adding
        if "_addanother" in postData:
            return redirect(f"{fill_path}")

        if "_continue" in postData:
            fp2 = fill_path.replace("/add/", "/edit/")
            return redirect(f"{fp2}{item.id}")
    else:  # we have id we are editing (delete was already done)
        if "_addanother" in postData:
            fp2 = fill_path.split("/edit/")[0] + "/add/"
            return redirect(f"{fp2}")

    return None


def _formInit(
    k,
    request,
    app_name=None,
    autogui_dict={},
    *args,
    **kwargs,
):
    fill_path = request.get_full_path()
    if debugOn():
        print(f"fill_path: {fill_path}", file=sys.stderr)

    model = mapModel(autogui_dict, app_name, fill_path)
    if debugOn():
        print(f"model: {model}", file=sys.stderr)

    postData = _getPostData(request)
    if debugOn():
        print(f"postData: {postData}", file=sys.stderr)

    splitPath = _splitPath(fill_path)
    what = None
    if len(splitPath) > 2:
        what = splitPath[2]

    xId = _getPrimaryKey(k, **kwargs)
    mData = getModelData(model, xId)
    if mData:
        # if we have data we can fill the form with the current data
        myForm = mapForm(
            autogui_dict,
            app_name,
            fill_path,
            instance=mData,
        )
    else:
        # otherwise start a empty form
        myForm = mapForm(
            autogui_dict,
            app_name,
            fill_path,
            None,
        )

    if debugOn():
        print(f"myForm 0: {myForm} {mData}", file=sys.stderr)

    return model, myForm, postData, fill_path, what, mData, xId


def _getPrimaryKey(
    k,
    **kwargs,
):
    xId = None
    if k in kwargs:
        xId = kwargs[k]
        if debugOn():
            print(f"{k} exists: {xId}", file=sys.stderr)
    return xId


def _doRenderFormData(
    request,
    app_name,
    autogui_dict,
    fill_path,
    myForm,
    xId,
    what,
):
    path = _splitPath(fill_path)

    deleting = True if what == "delete" else False
    updating = True if what == "edit" else False

    xDel = "/".join(["", path[0], path[1], "delete", str(xId)]) if xId else None

    c1 = _startContext(autogui_dict, app_name, request)
    c2 = {
        "form": myForm,
        "id": xId,
        "delete": xDel,
        "deleting": deleting,
        "updating": updating,
    }

    context = c1 | c2  # merge the dicts

    return render(
        request,
        f"{app_name}/form.html",
        context,
    )


def _doAddItem(
    k,
    model,
    myForm,
    postData,
    fill_path,
    what,
    mData,
    xId,
    request,
    autogui_dict,
    app_name,
    **kwargs,
):
    # asser we have model
    # assert we have myForm
    # assert no xId, no mData
    # ading a new item, we have no id yet

    if postData:
        myForm = mapForm(
            autogui_dict,
            app_name,
            fill_path,
            postData,
        )
        if debugOn():
            print(f"myForm 4: {myForm}", file=sys.stderr)

        if myForm.is_valid():
            resp = _doValidForm(
                myForm,
                postData,
                fill_path,
                k,
                **kwargs,
            )
            if resp:
                return resp

    return _doRenderFormData(
        request,
        app_name,
        autogui_dict,
        fill_path,
        myForm,
        xId,
        what,
    )


def _doEditItem(
    k,
    model,
    myForm,
    postData,
    fill_path,
    what,
    mData,
    xId,
    request,
    autogui_dict,
    app_name,
    **kwargs,
):
    if postData:
        if mData:
            # update the form with the newly posted data
            myForm = mapForm(
                autogui_dict,
                app_name,
                fill_path,
                postData,
                instance=mData,
            )
            if debugOn():
                print(f"myForm 2: {myForm}", file=sys.stderr)

            if myForm.is_valid():
                resp = _doValidForm(
                    myForm,
                    postData,
                    fill_path,
                    k,
                    **kwargs,
                )
                if resp:
                    return resp

    return _doRenderFormData(
        request,
        app_name,
        autogui_dict,
        fill_path,
        myForm,
        xId,
        what,
    )


def _doDeleteItem(
    k,
    model,
    myForm,
    postData,
    fill_path,
    what,
    mData,
    xId,
    request,
    autogui_dict,
    app_name,
    **kwargs,
):
    if "delete" in postData:
        return _deleteAndRedirect(
            model,
            postData,
            fill_path,
        )

    return _doRenderFormData(
        request,
        app_name,
        autogui_dict,
        fill_path,
        myForm,
        xId,
        what,
    )


# PUBLIC


def getModelData(
    model,
    xId,
):
    """
    fetch the data from a mode and a pk
    """
    mData = None
    if model and xId:
        mData = model.objects.get(pk=xId)
        if debugOn():
            print(f"mData: {mData}", file=sys.stderr)
    return mData


def doPagingWithSearchFilters():
    pass


def doPerPage(
    request: Any,
    autogui_dict: Dict[str, Any],
    postData: Any,
) -> int | None:
    maxPerPage = maxPerPagePaginate(autogui_dict)

    if autogui_dict is None or len(autogui_dict) == 0:
        return None

    perPage = None
    k = "perPage"
    if k in request.session:
        perPage = request.session.get(k)

    k2 = "perPage2"
    for j in [k, k2]:
        z = postData.get(j)
        if z:
            if int(z) != request.session[k]:
                perPage = int(z)
                if perPage <= 0:
                    perPage = maxPerPage
                if perPage > 1000:
                    perPage = 1000

    if perPage is None:
        perPage = maxPerPage

    request.session[k] = perPage  # set the new per page in the session
    return perPage


def getFilterDictInfo(
    index_path: str,
    request: Any,
    fieldNames: Dict[str, Any],
) -> Dict[str, Any]:
    filter_prefix = getFilterPrefix()
    postData = _getPostData(request)

    filter_dict = {}
    session_key = f"{index_path}filter_dict"
    # -----------------------------------
    # if exist start with the current sesion data
    if request.session.get(session_key, False):
        filter_dict = request.session.get(session_key)

    if debugOn():
        print("FilterSession OLD", session_key, filter_dict, file=sys.stderr)

    # -----------------------------------
    filter_dict[f"{filter_prefix}_D"] = None
    filter_dict[f"{filter_prefix}_E"] = None

    for name, label in fieldNames.items():
        filter_key = f"{filter_prefix}{name}"
        if filter_key not in filter_dict:
            filter_dict[filter_key] = None

        v = postData.get(filter_key)
        if v:
            filter_dict[filter_key] = v  # we now have a copy of the post data in filter dict
            if v == "*":
                filter_dict[filter_key] = None

    if debugOn():
        print("FilterSession New", session_key, filter_dict, file=sys.stderr)

    request.session[session_key] = filter_dict
    return filter_dict


def genericIndex(
    autogui_dict,
    app_name,
    request,
    *args,
    **kwargs,
):
    fill_path = request.get_full_path()
    splitPath = _splitPath(fill_path)
    if len(splitPath) < 2:
        # we are either at the top level len==0 (home) or at the app level len==1
        if len(splitPath) == 1:
            # gather info on this app and show that
            pass
        else:
            # gather info on the project and show that
            pass
        pass

    index_path = fill_path
    if len(splitPath) > 2:
        index_path = "/" + "/".join(splitPath[:2]) + "/"

    model = None
    fieldNames = {}
    if autogui_dict and len(autogui_dict) and app_name:
        model = mapModel(
            autogui_dict,
            app_name,
            index_path,
        )

    if model:
        fieldNames = getModelData2(
            autogui_dict,
            model.__name__,
        ).get(
            "fields",
        )

    postData = _getPostData(request)
    perPage = doPerPage(
        request,
        autogui_dict,
        postData,  # we are looking for page size info and page offset
    )

    page_obj = None
    data = []
    filterDict = {}
    sortDict = {}
    names = makeIndexFieldNames(
        autogui_dict,
        app_name,
        index_path,
    )
    if model:
        # --- filter
        filterDict = getFilterDictInfo(
            index_path,
            request,
            fieldNames,
        )
        #         # --- sort
        #         if request.session.get('sort'):
        #             sortDict = request.session.get('sort')
        #
        #         for colName in names:
        #             x = request.GET.get('sort')
        #             if x:
        #             sortDict[colName] = "-"
        #         request.session['sort'] = sortDict

        # --- get data
        # get the current page of data we are about to prepare for display
        item_list = _getSearchDataWithFilterApplied(
            index_path,
            autogui_dict,
            model,
            filterDict,
            # postData,  # we are looking for filter hints
        )
        paginator = Paginator(
            item_list,
            perPage,
        )
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(
            page_number,
        )
        # --- get page
        if page_obj:
            names, data = makeIndexFields(
                autogui_dict,
                app_name,
                index_path,
                page_obj,  # the one page we will show
            )

    # ---- prepare for display
    c1 = _startContext(
        autogui_dict,
        app_name,
        request,
    )
    c2 = {
        "perPage": perPage,
        "page_obj": page_obj,
        "data": data,
        "colNames": names,
        "postData": postData,
        "filter": filterDict,
        "sort": sortDict,
    }
    context = c1 | c2  # merge the dicts

    return render(
        request,
        f"{app_name}/index.html",
        context,
    )


# @login_required
def genericForm(
    autogui_dict,
    app_name,
    request,
    *args,
    **kwargs,
):
    # request.session
    k = "id"
    model, myForm, postData, fill_path, what, mData, xId = _formInit(
        k,
        request,
        app_name,
        autogui_dict,
        *args,
        **kwargs,
    )

    if what == "add":
        # we see add as get and as post
        return _doAddItem(
            k,
            model,
            myForm,
            postData,
            fill_path,
            what,
            mData,
            xId,
            request,
            autogui_dict,
            app_name,
            **kwargs,
        )

    if what == "delete":
        # we see delete as get and as post
        return _doDeleteItem(
            k,
            model,
            myForm,
            postData,
            fill_path,
            what,
            mData,
            xId,
            request,
            autogui_dict,
            app_name,
            **kwargs,
        )

    if what == "edit":
        return _doEditItem(
            k,
            model,
            myForm,
            postData,
            fill_path,
            what,
            mData,
            xId,
            request,
            autogui_dict,
            app_name,
            **kwargs,
        )

    if what == "sort":
        return None

    # not add, edit or delete, sort
    if debugOn():
        print("not one of [add, edit, delete, sort]", file=sys.stderr)

    return _doRenderFormData(
        request,
        app_name,
        autogui_dict,
        fill_path,
        myForm,
        xId,
        what,
    )
