# import sys
from typing import (
    Any,
    Dict,
    #    List,
)


from aGit2Git.xauto import (
    AUTO_GUI as AG,
    mapModel,
    mapForm,
    maxPerPagePaginate,
    makeIndexFields,
    getFields,
    getFilterPrefix,
)

from django.shortcuts import (
    render,
    redirect,
)

from django.core.paginator import Paginator


def empty(request):
    # this func should be totally generic all custom data must come frpm xauto
    return redirect("index")


def navigation():
    # this func should be totally generic all custom data must come frpm xauto

    zz = AG["navigation"]
    rr = []
    for k, v in zz.items():
        data = {
            "url": v + "/",
            "label": k,
        }
        rr.append(data)
    return rr


def getFilterHint(modelName, fieldName):
    # this func should be totally generic all custom data must come frpm xauto

    fields = getFields(modelName)
    k = "filter"

    if k not in fields:
        return None

    if fieldName not in fields[k]:
        return None

    return fields[k][fieldName]


def getIndexData(model, pData):
    # this func should be totally generic all custom data must come frpm xauto
    fp = getFilterPrefix()
    zArgs = {}
    for k, v in pData.items():
        if not v:
            continue
        if not k.startswith(fp):
            continue

        k2 = k.split(fp)[1]
        hint = getFilterHint(model.__name__, k2)
        if hint is None:
            continue

        zArgs[f"{hint}__icontains"] = v

    return model.objects.filter(**zArgs)


def startContext(request) -> Dict[str, Any]:
    # this func should be totally generic all custom data must come frpm xauto

    fp = request.get_full_path()
    app_name = __package__
    context = {
        "title": f"{app_name}{fp}",
        "navigation": navigation(),
        "action": fp,
        "path": fp[1:].split("/"),
    }
    return context


def index(request, *args, **kwargs):
    # this func should be totally generic all custom data must come frpm xauto
    fPrefix = getFilterPrefix()
    fp = request.get_full_path()
    app_name = __package__
    # xForm = mapForm(fp, None)

    maxPerPage = maxPerPagePaginate()
    perPage = maxPerPage

    pData = {}
    if request.method == "POST":
        pData = request.POST

    page_obj = None
    xNames = {}
    model = mapModel(fp)
    if model:
        item_list = getIndexData(model, pData)
        paginator = Paginator(item_list, perPage)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        xNames = getFields(model.__name__).get("fields")

    names, data = makeIndexFields(fp, page_obj)

    fDict = {}
    fDict[f"{fPrefix}_"] = None
    for name, label in xNames.items():
        k = f"{fPrefix}{name}"
        v = pData.get(k)
        fDict[k] = v

    c1 = startContext(request)
    c2 = {
        "perPage": perPage,
        "page_obj": page_obj,
        "data": data,
        "names": names,
        "pData": pData,
        "filter": fDict,
    }
    context = c1 | c2  # merge the dicts
    return render(request, f"{app_name}/index.html", context)


# @login_required
def form(request, *args, **kwargs):
    # this func should be totally generic all custom data must come frpm xauto
    # used for add, edit, delete
    fp = request.get_full_path()
    app_name = __package__
    xForm = mapForm(fp, None)

    # if we have a id, fetch the data
    k = "id"
    xId = None
    model = None
    if k in kwargs:
        xId = kwargs[k]
        model = mapModel(fp)
        if model:
            mData = model.objects.get(pk=kwargs[k])
            xForm = mapForm(fp, instance=mData)

    if request.method == "POST":
        pData = request.POST
        if "delete" in pData:
            instance = model.objects.get(id=pData["delete"])
            instance.delete()
            fp3 = fp.replace("/delete/", "/")
            fp3 = fp3.replace(pData["delete"], "")
            return redirect(f"{fp3}")

        if model:
            xForm = mapForm(fp, pData, instance=mData)
        else:
            xForm = mapForm(fp, pData)

        if xForm.is_valid():
            item = xForm.save()
            if k not in kwargs:
                fp2 = fp.replace("/add/", "/edit/")
                return redirect(f"{fp2}{item.id}")
        xId = kwargs[k]

    path = fp[1:].split("/")

    deleting = False
    if "/delete/" in fp:
        deleting = True

    updating = False
    if "/edit/" in fp:
        updating = True

    c1 = startContext(request)
    c2 = {
        "form": xForm,
        "id": xId,
        "delete": "/".join(["", path[0], "delete", str(xId)]),
        "deleting": deleting,
        "updating": updating,
    }
    context = c1 | c2  # merge the dicts

    return render(request, f"{app_name}/form.html", context)
