# from django.urls import path

from appAutoGui.xauto import url_gen_all

from aGit2Git import views
from aGit2Git.autoGui import AUTO_GUI

urlpatterns = []
urlpatterns += url_gen_all(
    AUTO_GUI,
    __package__,
    views.index,
    views.form,
)
