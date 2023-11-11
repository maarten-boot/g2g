# import sys

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


def _getFilterHint(
    AUTO_GUI: Dict[str, Any],
    modelName: str,
    fieldName: str,
) -> str:
    # return the filter hint we use to actually filter,
    # so we can use fk fields also to filter on
    fields = getFields(AUTO_GUI, modelName)
    k = "filter"

    if k not in fields:
        return None

    if fieldName not in fields[k]:
        return None

    return fields[k][fieldName]


def _doOneIndexItem(
    AUTO_GUI,
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
    hint = _getFilterHint(AUTO_GUI, model.__name__, k2)
    if hint is None:
        return

    filterDict[f"{hint}__icontains"] = v


def _getSearchDataWithFilterApplied(AUTO_GUI, model, pData):
    prefix = getFilterPrefix()
    filterDict = {}
    for k, v in pData.items():
        _doOneIndexItem(AUTO_GUI, model, k, v, prefix, filterDict)

    return model.objects.filter(**filterDict)


def _startContext(AUTO_GUI, app_name: str, request) -> Dict[str, Any]:
    fp = request.get_full_path()
    context = {
        "title": f"{fp}",
        "navigation": navigation(AUTO_GUI, app_name),
        "action": fp,
        "action_clean": fp.split("?")[0],
        "path": fp[1:][:-1].split("/"),
    }
    return context


def genericIndex(
    AUTO_GUI,
    app_name,
    request,
    *args,
    **kwargs,
):
    fPrefix = getFilterPrefix()
    fp = request.get_full_path()

    maxPerPage = maxPerPagePaginate(AUTO_GUI)
    perPage = maxPerPage

    pData = {}
    if request.method == "POST":
        pData = request.POST

    page_obj = None
    xNames = {}
    model = mapModel(
        AUTO_GUI,
        app_name,
        fp,
    )

    if model:
        item_list = _getSearchDataWithFilterApplied(AUTO_GUI, model, pData)
        paginator = Paginator(item_list, perPage)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        xNames = getFields(AUTO_GUI, model.__name__).get(
            "fields",
        )

    names, data = makeIndexFields(
        AUTO_GUI,
        app_name,
        fp,
        page_obj,
    )

    fDict = {}
    fDict[f"{fPrefix}_"] = None
    for name, label in xNames.items():
        k = f"{fPrefix}{name}"
        v = pData.get(k)
        fDict[k] = v

    c1 = _startContext(
        AUTO_GUI,
        app_name,
        request,
    )
    c2 = {
        "perPage": perPage,
        "page_obj": page_obj,
        "data": data,
        "names": names,
        "pData": pData,
        "filter": fDict,
    }
    context = c1 | c2  # merge the dicts
    return render(
        request,
        f"{app_name}/index.html",
        context,
    )


def _deleteAndRedirect(
    model,
    pData,
    fp,
):
    instance = model.objects.get(id=pData["delete"])
    instance.delete()
    fp3 = fp.replace("/delete/", "/")
    fp3 = fp3.replace(pData["delete"], "")
    return redirect(f"{fp3}")


def _doValidForm(
    xForm,
    pData,
    fp,
    k,
    **kwargs,
):
    item = xForm.save()
    if k not in kwargs:
        if "_addanother" in pData:
            return redirect(f"{fp}")

        if "_continue" in pData:
            fp2 = fp.replace("/add/", "/edit/")
            return redirect(f"{fp2}{item.id}")
    else:
        if "_addanother" in pData:
            fp2 = fp.split("/edit/")[0] + "/add/"
            return redirect(f"{fp2}")

    return None


# @login_required
def genericForm(
    AUTO_GUI,
    app_name,
    request,
    *args,
    **kwargs,
):
    # used for add, edit, delete
    fp = request.get_full_path()
    xForm = mapForm(
        AUTO_GUI,
        app_name,
        fp,
        None,
    )

    k = "id"
    xId = None
    model = None
    if k in kwargs:
        # if we have a id, fetch the data
        xId = kwargs[k]
        model = mapModel(AUTO_GUI, app_name, fp)
        if model:
            mData = model.objects.get(pk=kwargs[k])
            xForm = mapForm(
                AUTO_GUI,
                app_name,
                fp,
                instance=mData,
            )

    if request.method == "POST":
        pData = request.POST

        if "delete" in pData:
            return _deleteAndRedirect(
                model,
                pData,
                fp,
            )

        if model:
            xForm = mapForm(
                AUTO_GUI,
                app_name,
                fp,
                pData,
                instance=mData,
            )
        else:
            xForm = mapForm(
                AUTO_GUI,
                app_name,
                fp,
                pData,
            )

        if xForm.is_valid():
            resp = _doValidForm(
                xForm,
                pData,
                fp,
                k,
                **kwargs,
            )
            if resp:
                return resp

    path = fp[1:].split("/")

    deleting = False
    if fp.startswith(f"/{path[0]}/{path[1]}/delete/"):
        deleting = True

    updating = False
    if fp.startswith(f"/{path[0]}/{path[1]}/edit/"):
        updating = True

    c1 = _startContext(AUTO_GUI, app_name, request)
    c2 = {
        "form": xForm,
        "id": xId,
        "delete": "/".join(["", path[0], path[1], "delete", str(xId)]),
        "deleting": deleting,
        "updating": updating,
    }
    context = c1 | c2  # merge the dicts

    return render(
        request,
        f"{app_name}/form.html",
        context,
    )
