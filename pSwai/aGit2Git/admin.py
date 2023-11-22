# import os

from django.contrib import admin

# from django.contrib.admin.views.main import ChangeList
# from django.urls import reverse

# from aGit2Git.models import Tag
from aGit2Git.models import Url
from aGit2Git.models import CopyType
from aGit2Git.models import UrlPair
from aGit2Git.models import Server
from aGit2Git.models import Script

LIST_PER_PAGE = 50


@admin.register(Url)
class Url(admin.ModelAdmin):
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


@admin.register(UrlPair)
class UrlPair(admin.ModelAdmin):
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
