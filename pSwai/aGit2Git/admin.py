# import os

from django.contrib import admin

from aGit2Git.models import CopyType as _CopyType
from aGit2Git.models import Repo as _Repo
from aGit2Git.models import RepoPair as _RepoPair
from aGit2Git.models import Run as _Run
from aGit2Git.models import Script as _Script

# from django.contrib.admin.views.main import ChangeList
# from django.urls import reverse
from aGit2Git.models import Server as _Server

LIST_PER_PAGE = 50


@admin.register(_Repo)
class Repo(admin.ModelAdmin):  # pylint:disable=E0102
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


@admin.register(_CopyType)
class CopyType(admin.ModelAdmin):  # pylint:disable=E0102
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


@admin.register(_RepoPair)
class RepoPair(admin.ModelAdmin):  # pylint:disable=E0102
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


@admin.register(_Server)
class Server(admin.ModelAdmin):  # pylint:disable=E0102
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


@admin.register(_Script)
class Script(admin.ModelAdmin):  # pylint:disable=E0102
    list_display = (
        "name",
        "repo",
        "description",
        "updStamp",
    )
    list_per_page = LIST_PER_PAGE
    search_fields = ("name",)
    list_filter = ("updStamp",)


@admin.register(_Run)
class Run(admin.ModelAdmin):  # pylint:disable=E0102
    """Run records are history: read only here (docs/run-design.md)."""

    list_display = ("script_id", "started_by_name", "started_at", "status", "result", "repo_pair")
    list_per_page = LIST_PER_PAGE
    search_fields = ("script_id", "started_by_name")
    list_filter = ("status", "started_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
