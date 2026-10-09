# import sys

from appAutoGui.genericViews import (
    generic_form,
    generic_index,
)

from aGit2Git.autoGui import AUTO_GUI


# @login_required
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
