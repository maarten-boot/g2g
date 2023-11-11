# from django.urls import path

# from aGit2Git import views
from aGit2Git.autoGui import (
    urlGenAll,
)


urlpatterns = [
    # path("", views.index, name="index"),
]

urlpatterns += urlGenAll(__package__)
