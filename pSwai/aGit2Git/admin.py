# import os

from django.contrib import admin

# from django.contrib.admin.views.main import ChangeList
# from django.urls import reverse

# from aGit2Git.models import Tag
from aGit2Git.models import Server
from aGit2Git.models import Repo
from aGit2Git.models import RepoPair
from aGit2Git.models import CopyType
from aGit2Git.models import Script
from aGit2Git.models import Component
from aGit2Git.models import Feature
from aGit2Git.models import Implementation
from aGit2Git.models import Dependencies

LIST_PER_PAGE = 50


@admin.register(Repo)
class Repo(admin.ModelAdmin):
    list_display = (
        "name",
        "internal",
        "url",
        "branch",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("name",)
    list_filter = (
        "updStamp",
        "internal",
    )


@admin.register(CopyType)
class CopyType(admin.ModelAdmin):
    list_display = (
        "name",
        "description",
        "manual",
        "needTag",
        "script",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("name",)
    list_filter = (
        "updStamp",
        "manual",
        "needTag",
    )


@admin.register(RepoPair)
class RepoPair(admin.ModelAdmin):
    list_display = (
        "name",
        "description",
        "source",
        "target",
        "copyType",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("name",)
    list_filter = (
        "updStamp",
        "copyType",
    )


@admin.register(Server)
class Server(admin.ModelAdmin):
    list_display = (
        "name",
        "internal",
        "description",
        "url",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("name",)
    list_filter = (
        "updStamp",
        "internal",
    )


@admin.register(Script)
class Script(admin.ModelAdmin):
    list_display = (
        "name",
        "repo",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("name",)
    list_filter = ("updStamp",)


@admin.register(Component)
class Component(admin.ModelAdmin):
    list_display = (
        "name",
        "mainRepo",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("name",)
    list_filter = ("updStamp",)


@admin.register(Feature)
class Feature(admin.ModelAdmin):
    list_display = (
        "name",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("name",)
    list_filter = ("updStamp",)


@admin.register(Implementation)
class Implementation(admin.ModelAdmin):
    list_display = (
        "component",
        "feature",
        "requested",
        "implemented",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("component", "feature")
    list_filter = ("updStamp",)


@admin.register(Dependencies)
class Dependencies(admin.ModelAdmin):
    list_display = (
        "component",
        "uses",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("component", "uses")
    list_filter = ("updStamp",)
