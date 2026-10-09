from appAutoGui.genericViews import (
    generic_form,
    generic_index,
)
from django.contrib.auth.decorators import login_required

from aGit2Git.autoGui import AUTO_GUI


@login_required
def form(
    request,
    *args,
    **kwargs,
):
    app_name = __package__
    return generic_form(
        autogui_dict=AUTO_GUI,
        app_name=app_name,
        request=request,
        *args,
        **kwargs,
    )


@login_required
def index(
    request,
    *args,
    **kwargs,
):
    app_name = __package__
    return generic_index(
        autogui_dict=AUTO_GUI,
        app_name=app_name,
        request=request,
        *args,
        **kwargs,
    )
