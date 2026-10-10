from django.contrib import admin

from aComponents.models import Component as _Component
from aComponents.models import Dependencies as _Dependencies
from aComponents.models import Feature as _Feature
from aComponents.models import Implementation as _Implementation

LIST_PER_PAGE = 50


@admin.register(_Component)
class Component(admin.ModelAdmin):  # pylint:disable=E0102
    list_display = (
        "name",
        "mainRepo",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("name",)
    list_filter = ("updStamp",)


@admin.register(_Feature)
class Feature(admin.ModelAdmin):  # pylint:disable=E0102
    list_display = (
        "name",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("name",)
    list_filter = ("updStamp",)


@admin.register(_Implementation)
class Implementation(admin.ModelAdmin):  # pylint:disable=E0102
    list_display = (
        "component",
        "feature",
        "requested",
        "implemented",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("component__name", "feature__name")
    list_filter = ("updStamp",)


@admin.register(_Dependencies)
class Dependencies(admin.ModelAdmin):  # pylint:disable=E0102
    list_display = (
        "component",
        "uses",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("component__name", "uses__name")
    list_filter = ("updStamp",)
