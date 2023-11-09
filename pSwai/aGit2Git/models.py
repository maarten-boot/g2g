# import os
import uuid

# from typing import Dict

from django.db import models

# from django.conf import settings
# from django.urls import reverse
# from django.utils import timezone

# ==============================================
# ==============================================
# Abstract Base Classes


class AbsBase(models.Model):
    # The absolute Basics for all
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creStamp = models.DateTimeField(auto_now=False, auto_now_add=True, null=False)
    updStamp = models.DateTimeField(auto_now=True, auto_now_add=False, null=True)

    class Meta:
        abstract = True

    def __repr__(self):
        return "<%d>" % (self.id)

    def __str__(self):
        return "<%d>" % (self.id)


class AbsCommonName(AbsBase):
    # having Name
    name = models.CharField(max_length=128, unique=True, null=False)
    description = models.TextField(blank=True, null=True)

    class Meta:
        abstract = True

    def __repr__(self):
        return "<%s>" % (self.name)

    def __str__(self):
        return "<%s>" % (self.name)


# ==============================================
# ==============================================
# App configuration models


class Tag(AbsCommonName):
    class Meta:
        verbose_name_plural = "Tag"
        ordering = ("name",)


class Server(AbsCommonName):
    internal = models.BooleanField(default=True)
    url = models.URLField(max_length=255, unique=True, null=False)

    class Meta:
        verbose_name_plural = "Server"
        ordering = ("name",)


class Url(AbsCommonName):
    url = models.URLField(max_length=255, unique=True, null=False)
    internal = models.BooleanField(default=True)
    server = models.ForeignKey(Server, on_delete=models.CASCADE, null=False, blank=False, related_name="server_url")
    branch = models.CharField(max_length=128, unique=False, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Url"
        indexes = [
            models.Index(fields=["name", "branch"]),
        ]
        unique_together = [["name", "branch"]]
        ordering = ("name", "branch")


class Script(AbsCommonName):
    repo = models.ForeignKey(Url, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Script"
        ordering = ("name",)


class CopyType(AbsCommonName):
    manual = models.BooleanField(default=True)
    needTag = models.BooleanField(default=False)
    script = models.ForeignKey(Script, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name_plural = "CopyType"
        ordering = ("name",)


class UrlPair(AbsCommonName):
    source = models.ForeignKey(Url, on_delete=models.CASCADE, null=False, blank=False, related_name="sourceUrl")
    target = models.ForeignKey(Url, on_delete=models.CASCADE, null=False, blank=False, related_name="targetUrl")
    copyType = models.ForeignKey(CopyType, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name_plural = "UrlPair"
        ordering = ("name",)
