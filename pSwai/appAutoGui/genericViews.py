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
    makeIndexFields,
    getFilterPrefix,
    getFields,
    maxPerPagePaginate,
    navigation,
)


def debugOn() -> bool:
    return True


def _getFilterHint(
    autoGuiDict: Dict[str, Any],
    modelName: str,
    fieldName: str,
) -> str:
    # return the filter hint we use to actually filter,
    # so we can use fk fields also to filter on
    fields = getFields(autoGuiDict, modelName)
    k = "filter"

    if k not in fields:
        return None

    if fieldName not in fields[k]:
        return None

    return fields[k][fieldName]


def _doOneIndexItem(
    autoGuiDict,
    model,
    k,
    v,
    prefix,
    filterDict: Dict[str, str],
) -> None:
    if not v:
        return

    if not k.startswith(prefix):
        return

    k2 = k.split(prefix)[1]
    hint = _getFilterHint(autoGuiDict, model.__name__, k2)
    if hint is None:
        return

    filterDict[f"{hint}__icontains"] = v


def _getSearchDataWithFilterApplied(autoGuiDict, model, postData):
    prefix = getFilterPrefix()
    filterDict = {}
    for k, v in postData.items():
        _doOneIndexItem(autoGuiDict, model, k, v, prefix, filterDict)

    return model.objects.filter(**filterDict)


def _splitPath(fullPath):
    if debugOn():
        print(f"fullPath: |{fullPath}|", file=sys.stderr)

    if len(fullPath) > 0:
        if len(fullPath) > 1:
            splitPath = fullPath[1:][:-1].split("/")
        else:
            splitPath = []
    else:
        splitPath = []

    if debugOn():
        print(f"pathLen: {len(splitPath)} :: {splitPath}", file=sys.stderr)

    return splitPath


def _startContext(autoGuiDict, app_name: str, request) -> Dict[str, Any]:
    fullPath = request.get_full_path()

    title = str(fullPath)
    action = fullPath
    action_clean = fullPath.split("?")[0]
    # nav = navigation(autoGuiDict, app_name)
    nav = navigation()
    path = _splitPath(fullPath)

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


def doPagingWithSearchFilters():
    pass


def doPerPage(request, autoGuiDict, postData):
    maxPerPage = maxPerPagePaginate(autoGuiDict)
    perPage = None

    k = "perPage"
    k2 = "perPage2"
    if k in request.session:
        perPage = request.session[k]

    if debugOn():
        print(postData, file=sys.stderr)

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

    request.session[k] = perPage
    return perPage


def genericIndex(
    autoGuiDict,
    app_name,
    request,
    *args,
    **kwargs,
):
    fullPath = request.get_full_path()
    splitPath = _splitPath(fullPath)

    if len(splitPath) < 2:
        # we have no actual model now
        # we are either at the top level len==0 (home) or at the app level len ==1
        if len(splitPath) == 1:
            # gather info on this app and show that
            pass
        else:
            # gather info on the project ans show that
            pass
        pass

    model = None
    if autoGuiDict and len(autoGuiDict) and app_name:
        model = mapModel(
            autoGuiDict,
            app_name,
            fullPath,
        )

    postData = _getPostData(request)
    perPage = doPerPage(request, autoGuiDict, postData)

    page_obj = None
    fieldNames = {}

    if model:
        item_list = _getSearchDataWithFilterApplied(autoGuiDict, model, postData)
        paginator = Paginator(item_list, perPage)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        fieldNames = getFields(autoGuiDict, model.__name__).get(
            "fields",
        )

    names = []
    data = []
    if autoGuiDict and len(autoGuiDict) and app_name:
        names, data = makeIndexFields(
            autoGuiDict,
            app_name,
            fullPath,
            page_obj,
        )

    # make the filter names and filter the result set
    filterPrefix = getFilterPrefix()
    filterDict = {}
    filterDict[f"{filterPrefix}_"] = None
    for name, label in fieldNames.items():
        k = f"{filterPrefix}{name}"
        v = postData.get(k)
        filterDict[k] = v

    c1 = _startContext(
        autoGuiDict,
        app_name,
        request,
    )
    c2 = {
        "perPage": perPage,
        "page_obj": page_obj,
        "data": data,
        "names": names,
        "postData": postData,
        "filter": filterDict,
    }
    context = c1 | c2  # merge the dicts

    return render(
        request,
        f"{app_name}/index.html",
        context,
    )


def _deleteAndRedirect(
    model,
    postData,
    fullPath,
):
    instance = model.objects.get(id=postData["delete"])
    instance.delete()
    fp3 = fullPath.replace("/delete/", "/")
    fp3 = fp3.replace(postData["delete"], "")
    return redirect(f"{fp3}")


def _doValidForm(
    myForm,
    postData,
    fullPath,
    k,
    **kwargs,
):
    item = myForm.save()
    if k not in kwargs:  # no id field: we are adding
        if "_addanother" in postData:
            return redirect(f"{fullPath}")

        if "_continue" in postData:
            fp2 = fullPath.replace("/add/", "/edit/")
            return redirect(f"{fp2}{item.id}")
    else:  # we have id we are editing (delete was already done)
        if "_addanother" in postData:
            fp2 = fullPath.split("/edit/")[0] + "/add/"
            return redirect(f"{fp2}")

    return None


def _formInit(k, request, app_name=None, autoGuiDict={}, *args, **kwargs):
    fullPath = request.get_full_path()
    if debugOn():
        print(f"fullPath: {fullPath}", file=sys.stderr)

    model = mapModel(autoGuiDict, app_name, fullPath)
    if debugOn():
        print(f"model: {model}", file=sys.stderr)

    postData = _getPostData(request)
    if debugOn():
        print(f"postData: {postData}", file=sys.stderr)

    splitPath = _splitPath(fullPath)
    what = None
    if len(splitPath) > 2:
        what = splitPath[2]

    xId = _getPrimaryKey(k, **kwargs)
    mData = getModelData(model, xId)
    if mData:
        # if we have data we can fill the form with the current data
        myForm = mapForm(
            autoGuiDict,
            app_name,
            fullPath,
            instance=mData,
        )
    else:
        # otherwise start a empty form
        myForm = mapForm(
            autoGuiDict,
            app_name,
            fullPath,
            None,
        )

    if debugOn():
        print(f"myForm 0: {myForm} {mData}", file=sys.stderr)

    return model, myForm, postData, fullPath, what, mData, xId


def _getPrimaryKey(k, **kwargs):
    xId = None
    if k in kwargs:
        xId = kwargs[k]
        if debugOn():
            print(f"{k} exists: {xId}", file=sys.stderr)
    return xId


def getModelData(model, xId):
    mData = None
    if model and xId:
        mData = model.objects.get(pk=xId)
        if debugOn():
            print(f"mData: {mData}", file=sys.stderr)
    return mData


def _doRenderFormData(request, app_name, autoGuiDict, fullPath, myForm, xId, what):
    path = _splitPath(fullPath)

    deleting = True if what == "delete" else False
    updating = True if what == "edit" else False

    xDel = "/".join(["", path[0], path[1], "delete", str(xId)]) if xId else None

    c1 = _startContext(autoGuiDict, app_name, request)
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


def _doAddItem(k, model, myForm, postData, fullPath, what, mData, xId, request, autoGuiDict, app_name, **kwargs):
    # asser we have model
    # assert we have myForm
    # assert no xId, no mData
    # ading a new item, we have no id yet

    if postData:
        myForm = mapForm(
            autoGuiDict,
            app_name,
            fullPath,
            postData,
        )
        if debugOn():
            print(f"myForm 4: {myForm}", file=sys.stderr)

        if myForm.is_valid():
            resp = _doValidForm(
                myForm,
                postData,
                fullPath,
                k,
                **kwargs,
            )
            if resp:
                return resp

    return _doRenderFormData(
        request,
        app_name,
        autoGuiDict,
        fullPath,
        myForm,
        xId,
        what,
    )


def _doEditItem(k, model, myForm, postData, fullPath, what, mData, xId, request, autoGuiDict, app_name, **kwargs):
    if postData:
        if mData:
            # update the form with the newly posted data
            myForm = mapForm(
                autoGuiDict,
                app_name,
                fullPath,
                postData,
                instance=mData,
            )
            if debugOn():
                print(f"myForm 2: {myForm}", file=sys.stderr)

            if myForm.is_valid():
                resp = _doValidForm(
                    myForm,
                    postData,
                    fullPath,
                    k,
                    **kwargs,
                )
                if resp:
                    return resp

    return _doRenderFormData(
        request,
        app_name,
        autoGuiDict,
        fullPath,
        myForm,
        xId,
        what,
    )


def _doDeleteItem(k, model, myForm, postData, fullPath, what, mData, xId, request, autoGuiDict, app_name, **kwargs):
    if "delete" in postData:
        return _deleteAndRedirect(
            model,
            postData,
            fullPath,
        )

    return _doRenderFormData(
        request,
        app_name,
        autoGuiDict,
        fullPath,
        myForm,
        xId,
        what,
    )


# @login_required
def genericForm(
    autoGuiDict,
    app_name,
    request,
    *args,
    **kwargs,
):
    k = "id"
    model, myForm, postData, fullPath, what, mData, xId = _formInit(
        k,
        request,
        app_name,
        autoGuiDict,
        *args,
        **kwargs,
    )

    if what == "add":
        # we see add as get and as post
        return _doAddItem(k, model, myForm, postData, fullPath, what, mData, xId, request, autoGuiDict, app_name, **kwargs)

    if what == "delete":
        # we see delete as get and as post
        return _doDeleteItem(k, model, myForm, postData, fullPath, what, mData, xId, request, autoGuiDict, app_name, **kwargs)

    if what == "edit":
        return _doEditItem(k, model, myForm, postData, fullPath, what, mData, xId, request, autoGuiDict, app_name, **kwargs)

    # not add, edit or delete
    if debugOn():
        print("not one of [add, edit, delete]", file=sys.stderr)

    return _doRenderFormData(
        request,
        app_name,
        autoGuiDict,
        fullPath,
        myForm,
        xId,
        what,
    )
