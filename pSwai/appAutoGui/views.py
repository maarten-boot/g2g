from appAutoGui.genericViews import (
    generic_index,
)


def index(
    request,
    *args,
    **kwargs,
):
    """the home page; logging in is done by appLogin (/login/)"""
    app_name = __package__
    return generic_index(
        autogui_dict={},
        app_name=app_name,
        request=request,
        *args,
        **kwargs,
    )
