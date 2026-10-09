from unittest import mock

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings

from appLogin.backends import LDAPBackend

PASSWORD = "local-test-password"


# LDAP is not reachable from tests: authenticate against local users only
@override_settings(AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend"])
class LoginTests(TestCase):
    def setUp(self):
        User.objects.create_user("tester", password=PASSWORD)

    def _login(self, next_url: str):
        return self.client.post("/login/", {"username": "tester", "password": PASSWORD, "next": next_url})

    def test_login_page_keeps_next(self):
        r = self.client.get("/login/?next=/aGit2Git/repo/")
        self.assertContains(r, 'name="next" value="/aGit2Git/repo/"')

    def test_login_redirects_to_next(self):
        r = self._login("/aGit2Git/repo/")
        self.assertRedirects(r, "/aGit2Git/repo/", fetch_redirect_response=False)

    def test_login_rejects_external_next(self):
        r = self._login("https://evil.example/")
        self.assertRedirects(r, "/", fetch_redirect_response=False)

    def test_wrong_password_stays_on_login_page(self):
        with self.assertLogs("appLogin.views", level="WARNING") as logs:
            r = self.client.post("/login/", {"username": "tester", "password": "wrong"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(r, "Login failed: unknown username or wrong password.")
        self.assertIn("login failed for tester", logs.output[0])
        self.assertNotIn("wrong", logs.output[0])  # never log the password


class LoginNameTests(SimpleTestCase):
    """UPN, mail and DOMAIN\\user are translated to the sAMAccountName before the LDAP login"""

    def setUp(self):
        self.backend = LDAPBackend()

    def test_sam_account_name_is_used_as_is(self):
        with mock.patch.object(LDAPBackend, "_lookup_sam_account_name") as lookup:
            self.assertEqual(self.backend.to_sam_account_name("jdoe"), "jdoe")
        lookup.assert_not_called()

    def test_domain_prefix_is_removed(self):
        self.assertEqual(self.backend.to_sam_account_name("EXAMPLE\\jdoe"), "jdoe")

    def test_upn_or_mail_is_looked_up(self):
        with mock.patch.object(LDAPBackend, "_lookup_sam_account_name", return_value="jdoe") as lookup:
            self.assertEqual(self.backend.to_sam_account_name("john.doe@example.com"), "jdoe")
        lookup.assert_called_once_with("john.doe@example.com")

    def test_unknown_upn_is_kept(self):
        with mock.patch.object(LDAPBackend, "_lookup_sam_account_name", return_value=None):
            self.assertEqual(self.backend.to_sam_account_name("nobody@example.com"), "nobody@example.com")

    def test_authenticate_uses_the_sam_account_name(self):
        with (
            mock.patch.object(LDAPBackend, "_lookup_sam_account_name", return_value="jdoe"),
            mock.patch("django_auth_ldap.backend.LDAPBackend.authenticate", return_value=None) as parent,
        ):
            self.backend.authenticate(None, username="john.doe@example.com", password="pw")
        parent.assert_called_once_with(None, username="jdoe", password="pw")

    def _lookup_with(self, results):
        conn = mock.Mock()
        conn.search_s.return_value = results
        ldap_module = mock.Mock(initialize=mock.Mock(return_value=conn))
        with mock.patch.object(LDAPBackend, "ldap", new_callable=mock.PropertyMock, return_value=ldap_module):
            sam = self.backend._lookup_sam_account_name("j*doe)(x@example.com")
        return sam, conn

    def test_lookup_escapes_the_filter_and_skips_referrals(self):
        sam, conn = self._lookup_with([("CN=jdoe,DC=example", {"sAMAccountName": [b"jdoe"]}), (None, ["ldap://ref"])])
        self.assertEqual(sam, "jdoe")
        search_filter = conn.search_s.call_args.args[2]
        self.assertIn(r"(userPrincipalName=j\2adoe\29\28x@example.com)", search_filter)
        self.assertIn(r"(mail=j\2adoe\29\28x@example.com)", search_filter)
        conn.unbind_s.assert_called_once()

    def test_lookup_ambiguous_returns_none(self):
        sam, _ = self._lookup_with(
            [("CN=a,DC=example", {"sAMAccountName": [b"a"]}), ("CN=b,DC=example", {"sAMAccountName": [b"b"]})]
        )
        self.assertIsNone(sam)
