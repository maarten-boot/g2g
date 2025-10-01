# import sys

from aGit2Git.autoGui import AUTO_GUI
from appAutoGui.genericViews import (
    genericForm,
    genericIndex,
)


# @login_required
def form(
    request,
    *args,
    **kwargs,
):
    app_name = __package__
    return genericForm(
        autogui_dict=AUTO_GUI,
        app_name=app_name,
        request=request,
        *args,
        **kwargs,
    )


def index(
    request,
    *args,
    **kwargs,
):
    app_name = __package__
    return genericIndex(
        autogui_dict=AUTO_GUI,
        app_name=app_name,
        request=request,
        *args,
        **kwargs,
    )
