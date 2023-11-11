# from django.urls import path

from appAutoGui.xauto import urlGenAll

from aGit2Git import views
from aGit2Git.autoGui import AUTO_GUI

urlpatterns = []
urlpatterns += urlGenAll(
    AUTO_GUI,
    __package__,
    views.index,
    views.form,
)
