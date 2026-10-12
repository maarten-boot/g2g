from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

# The session key holding the user's LDAP group DNs, read once at login (docs/run-design.md §4). The groups come
# from the server's own record of the session, never from anything the browser sends (Flask spec §14.6).
LDAP_GROUP_DNS = "ldap_group_dns"


@receiver(user_logged_in)
def remember_ldap_groups(sender, request, user, **kwargs):
    ldap_user = getattr(user, "ldap_user", None)  # set by django-auth-ldap; absent for local users
    request.session[LDAP_GROUP_DNS] = sorted(ldap_user.group_dns) if ldap_user is not None else []
