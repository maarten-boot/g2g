import sys

from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth import (
    logout,
    login,
    authenticate,
)

from appAutoGui import forms

from appAutoGui.genericViews import (
    genericForm,
    genericIndex,
)

TWO_WEEKS_IN_SECONDS = int(60 * 60 * 24 * 7 * 2)


# @login_required
def form(request, *args, **kwargs):
    app_name = __package__
    return genericForm({}, app_name, request, *args, **kwargs)


def index(request, *args, **kwargs):
    """force mandatory login before you can access the index (search) page"""
    if request.method == "POST" and request.user.is_authenticated is False:
        print(f"HH: {request.POST}", file=sys.stderr)
        xform = forms.LoginForm(request.POST)
        if xform.is_valid():
            remember_me = False
            username = xform.cleaned_data["loginName"]
            password = xform.cleaned_data["loginPassword"]
            # remember_me = xform.cleaned_data["loginCheck"]
            print(f"HH: {username}, {password}", file=sys.stderr)

            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                if not remember_me:
                    request.session.set_expiry(0)
                else:
                    request.session.set_expiry(TWO_WEEKS_IN_SECONDS)
            else:
                print("user not valid", file=sys.stderr)
        else:
            print("form not valid", file=sys.stderr)

        return redirect(settings.LOGIN_URL)

    app_name = __package__
    return genericIndex({}, app_name, request, *args, **kwargs)


def logout_view(request):
    logout(request)
    return redirect(f"{settings.LOGIN_URL}")


def login_view(request):
    if request.method != "POST":
        form = forms.LoginForm()
        return redirect(settings.LOGIN_URL)

    form = forms.LoginForm(request.POST)
    if form.is_valid():
        username = form.cleaned_data["loginName"]
        password = form.cleaned_data["loginPassword"]
        remember_me = form.cleaned_data["loginCheck"]

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if not remember_me:
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(TWO_WEEKS_IN_SECONDS)

    return redirect(settings.LOGIN_URL)
