AUTO_GUI: dict = {
    "max_per_page": 5,
    "navigation": {  # label , internal name used on model.nav:
        "Component": "component",
        "Feature": "feature",
        "Implementation": "implementation",
        "Dependencies": "dependencies",
    },
    "models": {
        "Component": {
            "nav": "component",
            "fields": {
                "name": "Name",
                "description": "Description",
                "mainRepo": "Repo",
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
                "component": "Component",
                "feature": "Feature",
                "requested": "Requested",
                "implemented": "Implemented",
                "description": "Description",
            },
            "filter": {
                "component": "component__name",
                "feature": "feature__name",
                "requested": "requested",
                "implemented": "implemented",
                "description": "description",
            },
        },
        "Dependencies": {
            "nav": "dependencies",
            "fields": {
                "component": "Component",
                "uses": "Uses",
                "description": "Description",
            },
            "filter": {
                "component": "component__name",
                "uses": "uses__name",
                "description": "description",
            },
        },
    },
}
