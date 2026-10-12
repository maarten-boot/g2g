from appAutoGui.xauto import url_gen_all
from django.urls import path

from aGit2Git import run_views, views
from aGit2Git.autoGui import AUTO_GUI

urlpatterns = [
    # Run (docs/run-design.md §7)
    path("aGit2Git/script/run/<uuid:pk>", run_views.start_script, name="aGit2Git_script_run"),
    path("aGit2Git/repopair/run/<uuid:pk>", run_views.start_pair, name="aGit2Git_repopair_run"),
    path("aGit2Git/run/", run_views.run_list, name="aGit2Git_run_list"),
    path("aGit2Git/run/reload", run_views.reload_view, name="aGit2Git_run_reload"),
    path("aGit2Git/run/<uuid:run_id>", run_views.run_page, name="aGit2Git_run"),
    path("aGit2Git/run/<uuid:run_id>/output", run_views.run_output, name="aGit2Git_run_output"),
    path("aGit2Git/run/<uuid:run_id>/download", run_views.run_download, name="aGit2Git_run_download"),
]
urlpatterns += url_gen_all(
    AUTO_GUI,
    __package__,
    views.index,
    views.form,
)
