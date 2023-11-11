# import sys

from typing import (
    # Any,
    Dict,
    List,
)

from django.urls import path

from aGit2Git import views


AUTO_GUI = {
    "max_per_page": 5,
    "navigation": {
        "Server": "server",
        "Url": "url",
        "Script": "script",
        "CopyType": "copytype",
        "UrlPair": "urlpair",
    },
    "models": {
        "Server": {
            "nav": "server",
            "fields": {
                "name": "Name",
                "description": "Description",
                "url": "Url",
                "internal": "Internal",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "url": "url",
                "internal": "internal",
            },
        },
        "Url": {
            "nav": "url",
            "fields": {
                "name": "Name",
                "description": "Description",
                "server": "Server",
                "url": "Url",
                "branch": "Branch",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "server": "server__name",
                "url": "url",
                "branch": "branch",
            },
        },
        "Script": {
            "nav": "script",
            "fields": {
                "name": "Name",
                "description": "Description",
                "repo": "Repository",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "repo": "repo__name",
            },
        },
        "CopyType": {
            "nav": "copytype",
            "fields": {
                "name": "Name",
                "description": "Description",
                "manual": "Manual",
                "needTag": "NeedTag",
                "script": "Script",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "manual": "manual",
                "needTag": "needTag",
                "script": "script__name",
            },
        },
        "UrlPair": {
            "nav": "urlpair",
            "fields": {
                "name": "Name",
                "description": "Description",
                "copyType": "CopyType",
                "source": "Source",
                "target": "Target",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "source": "source__name",
                "target": "target__name",
                "copyType": "copyType",
            },
        },
    },
}


def getNavNames() -> Dict[str, str]:
    ret = {}
    k = "models"
    for name, v in AUTO_GUI[k].items():
        if "nav" not in v:
            continue
        ret[v["nav"]] = name
    return ret


def _urlGenOne(app, k):
    ll = [
        path(f"{app}/{k}/", views.index, name=f"{app}_{k}"),
        path(f"{app}/{k}/add/", views.form, name=f"{app}_{k}_add"),
        path(f"{app}/{k}/edit/<uuid:id>", views.form, name=f"{app}_{k}_edit"),
        path(f"{app}/{k}/delete/<uuid:id>", views.form, name=f"{app}_{k}_delete"),
    ]

    # print(ll, file=sys.stderr)
    return ll


def urlGenAll(app: str) -> List[str]:
    xList = getNavNames().keys()
    urlPatternList = []
    for item in xList:
        z = _urlGenOne(app, item)
        urlPatternList += z

    # print(urlPatternList, file=sys.stderr)
    return urlPatternList


def getFields(modelName: str) -> Dict[str, str]:
    k = "models"
    if modelName in AUTO_GUI[k]:
        return AUTO_GUI[k][modelName]
    return {}


def maxPerPagePaginate() -> int:
    k = "max_per_page"
    if k in AUTO_GUI:
        return int(AUTO_GUI[k])
    return 15


def navigation():
    # this func should be totally generic all custom data must come frpm xauto
    app_name = __package__
    zz = AUTO_GUI["navigation"]
    rr = []
    for k, v in zz.items():
        data = {
            "url": "/" + app_name + "/" + v + "/",
            "label": k,
        }
        rr.append(data)
    return rr
