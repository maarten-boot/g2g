"""
URL configuration for pSwai project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import sys

from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.conf.urls.static import static
from django.conf import settings
from django.urls import (
    include,
    path,
)


from appAutoGui import views  # the project view is outside of all apps

for appName in settings.INSTALLED_APPS:
    if appName.startswith("django."):
        continue
    print(f"i see {appName}", file=sys.stderr)
    # now see if we have file autoGui.py
    # and if we have urls.py

urlpatterns = [
    path("admin/", admin.site.urls, name="admin"),
    path("", views.index, name="home"),
    path("", include("appLogin.urls")),
    path("", include("aGit2Git.urls")),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
