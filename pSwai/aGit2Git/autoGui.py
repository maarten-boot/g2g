# import sys


AUTO_GUI: dict = {
    "max_per_page": 5,
    "navigation": {  # label , internal name used on model.nav:
        "Server": "server",
        "Repo": "repo",
        "RepoPair": "repopair",
        "CopyType": "copytype",
        "Script": "script",
    },
    "models": {
        "Server": {
            "nav": "server",  # the name used in the Navigation
            "fields": {  # field_name -> Label
                "name": "Name",
                "description": "Description",
                "url": "Url",
                "internal": "Internal",
            },
            "filter": {  # field name , filter_hint (icontains)
                "name": "name",
                "description": "description",
                "url": "url",
                "internal": "internal",
            },
        },
        "Repo": {
            "nav": "repo",
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
        "RepoPair": {
            "nav": "repopair",
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
                "copyType": "copyType__name",
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
    },
}
