from typing import (
    Any,
    Dict,
    #    List,
)


AUTO_GUI = {
    "navigation": {
        "Server": "server",
        "Url": "url",
        "Script": "script",
        "CopyType": "copytype",
        "UrlPair": "urlpair",
        "Admin": "admin",
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
                # "internal": "Internal",
                "description": "Description",
                "server": "Server",
                "url": "Url",
                "branch": "Branch",
            },
            "filter": {
                "name": "name",
                "description": "description",
                "server": "server__name",
                # "internal": "internal",
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

def getFields(modelName: str) -> Dict[str, str]:
    k = "models"
    if modelName in AUTO_GUI[k]:
        return AUTO_GUI[k][modelName]
    return {}
