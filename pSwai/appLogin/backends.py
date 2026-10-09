import logging

import django_auth_ldap.backend
import ldap
from ldap.filter import escape_filter_chars

logger = logging.getLogger(__name__)

# attributes a user may log in with besides sAMAccountName
LOGIN_NAME_ATTRS = ("userPrincipalName", "mail")


class LDAPBackend(django_auth_ldap.backend.LDAPBackend):
    """django_auth_ldap backend that also accepts DOMAIN\\user, the UPN (user@domain) or the mail address.

    The login name is first translated to the sAMAccountName, so the django user is always named after
    the sAMAccountName: logging in as jdoe or as jdoe@example.com gives the same django user.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username:
            username = self.to_sam_account_name(username)
        return super().authenticate(request, username=username, password=password, **kwargs)

    def to_sam_account_name(self, login_name: str) -> str:
        login_name = login_name.strip()
        if "\\" in login_name:  # DOMAIN\user
            return login_name.split("\\", 1)[1]
        if "@" not in login_name:  # already a sAMAccountName
            return login_name

        sam = self._lookup_sam_account_name(login_name)
        if sam is None:
            # unknown: keep the name, the normal search then fails and logs why (at DEBUG)
            return login_name
        logger.debug("login name %s is sAMAccountName %s", login_name, sam)
        return sam

    def _lookup_sam_account_name(self, login_name: str) -> str | None:
        """search the directory with the service account; None when not exactly one user matches"""
        value = escape_filter_chars(login_name)
        alternatives = "".join(f"({attr}={value})" for attr in LOGIN_NAME_ATTRS)
        search_filter = f"(&(objectClass=user)(|{alternatives}))"

        conn = None
        try:
            # self.ldap applies AUTH_LDAP_GLOBAL_OPTIONS (TLS verification, CA file) on first use
            conn = self.ldap.initialize(self.settings.SERVER_URI)
            for opt, opt_value in self.settings.CONNECTION_OPTIONS.items():
                conn.set_option(opt, opt_value)
            if self.settings.START_TLS:
                conn.start_tls_s()
            conn.simple_bind_s(self.settings.BIND_DN, self.settings.BIND_PASSWORD)
            results = conn.search_s(
                self.settings.USER_SEARCH.base_dn,
                ldap.SCOPE_SUBTREE,
                search_filter,
                ["sAMAccountName"],
            )
        except ldap.LDAPError as e:
            logger.warning("LDAP lookup of login name %s failed: %s", login_name, e)
            return None
        finally:
            if conn is not None:
                conn.unbind_s()

        users = [attrs for dn, attrs in results if dn]  # skip AD referrals (dn None)
        if len(users) != 1:
            logger.info("login name %s matches %d users", login_name, len(users))
            return None
        return users[0]["sAMAccountName"][0].decode()
