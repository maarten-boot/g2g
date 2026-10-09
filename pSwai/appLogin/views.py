import logging

from django.contrib.auth import (
    authenticate,
    login,
    logout,
)
from django.shortcuts import (
    redirect,
    render,
)
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm

logger = logging.getLogger(__name__)

# deliberately the same for an unknown user and a wrong password
LOGIN_FAILED = "Login failed: unknown username or wrong password."


def _safe_next_url(request) -> str:
    """the ?next= url set by login_required, but only if it points back to this site"""
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return "home"


# login page
def user_login(request):
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=username, password=password)
            if user:
                logger.info("login ok for %s", username)
                login(request, user)
                return redirect(_safe_next_url(request))
            # the reason (user not found, password rejected) is logged by django_auth_ldap at DEBUG:
            # set LDAP_LOG_LEVEL=DEBUG to see it; connection/TLS errors are logged at WARNING
            # X-Real-IP is set by our nginx (django is only reachable through it)
            client = request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR")
            logger.warning("login failed for %s from %s", username, client)
            form.add_error(None, LOGIN_FAILED)
    else:
        form = LoginForm()
    return render(
        request,
        "appLogin/form.html",
        {"form": form, "next": request.POST.get("next") or request.GET.get("next", "")},
    )


# logout page
def user_logout(request):
    logout(request)
    return redirect("login")
