# import sys

from typing import (
    Dict,
)

AUTO_GUI: Dict = {
    "max_per_page": 5,
    "navigation": {
        "Server": "server",
        "Url": "url",
        "UrlPair": "urlpair",
        "Script": "script",
        "CopyType": "copytype",
        "Component": "component",
        "Feature": "feature",
        "Implementation": "implementation",
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
        "Component": {
            "nav": "component",
            "fields": {
                "name": "Name",
                "description": "Description",
                "mainRepo": "Url",
                "internal": "Internal",
            },
            "filter": {
                "name": "name",
                "mainRepo": "mainRepo__name",
                "description": "description",
                "internal": "internal",
            },
        },
        "Feature": {
            "nav": "feature",
            "fields": {
                "name": "Name",
                "description": "Description",
            },
            "filter": {
                "name": "name",
                "description": "description",
            },
        },
        "Implementation": {
            "nav": "implementation",
            "fields": {
                "component": "component__name",
                "feature": "feature__name",
                "implemented": "Implemented",
                "description": "Description",
            },
            "filter": {
                "component": "component",
                "feature": "feature",
                "implemented": "implemented",
                "description": "description",
            },
        },
    },
}
