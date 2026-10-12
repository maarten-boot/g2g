import io
import re
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path
from unittest import mock

from aComponents.models import Component, Dependencies
from appLogin.signals import LDAP_GROUP_DNS
from django.conf import settings
from django.contrib.auth.models import Group, Permission, User
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from aGit2Git import run_service
from aGit2Git.models import CopyType, Repo, RepoPair, Run, Script, Server

SERVER_INDEX = "/aGit2Git/server/"


def _server(name: str) -> Server:
    return Server.objects.create(name=name, url=f"https://{name}.invalid/")


class LoggedInTestCase(TestCase):
    """logged in with all rights; PermissionTests covers the users with fewer rights"""

    def setUp(self):
        self.user = User.objects.create_superuser("tester", password="not-used")
        self.client.force_login(self.user)


class LoginRequiredTests(TestCase):
    def test_anonymous_index_redirects_to_login(self):
        r = self.client.get(SERVER_INDEX)
        self.assertRedirects(r, f"/login/?next={SERVER_INDEX}", fetch_redirect_response=False)

    def test_anonymous_add_post_creates_nothing(self):
        r = self.client.post(f"{SERVER_INDEX}add/", {"name": "x", "url": "https://x.invalid/"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Server.objects.exists())

    def test_anonymous_delete_post_deletes_nothing(self):
        s = _server("keep")
        self.client.post(f"{SERVER_INDEX}delete/{s.id}", {"delete": str(s.id)})
        self.assertTrue(Server.objects.filter(id=s.id).exists())


class CrudTests(LoggedInTestCase):
    def test_add(self):
        r = self.client.post(
            f"{SERVER_INDEX}add/",
            {"name": "new", "url": "https://new.invalid/", "_continue": "Save"},
        )
        s = Server.objects.get(name="new")
        self.assertRedirects(r, f"{SERVER_INDEX}edit/{s.id}", fetch_redirect_response=False)

    def test_edit(self):
        s = _server("old")
        self.client.post(
            f"{SERVER_INDEX}edit/{s.id}",
            {"name": "renamed", "url": s.url, "_continue": "Save"},
        )
        s.refresh_from_db()
        self.assertEqual(s.name, "renamed")

    def test_edit_unknown_id_is_404(self):
        r = self.client.get(f"{SERVER_INDEX}edit/{uuid.uuid4()}")
        self.assertEqual(r.status_code, 404)

    def test_delete_get_only_asks_for_confirmation(self):
        s = _server("ask")
        r = self.client.get(f"{SERVER_INDEX}delete/{s.id}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Server.objects.filter(id=s.id).exists())

    def test_delete_post_deletes_and_redirects_to_index(self):
        s = _server("gone")
        r = self.client.post(f"{SERVER_INDEX}delete/{s.id}", {"delete": str(s.id)})
        self.assertRedirects(r, SERVER_INDEX, fetch_redirect_response=False)
        self.assertFalse(Server.objects.filter(id=s.id).exists())

    def test_delete_uses_id_from_url_not_from_post(self):
        target = _server("target")
        other = _server("other")
        self.client.post(f"{SERVER_INDEX}delete/{target.id}", {"delete": str(other.id)})
        self.assertFalse(Server.objects.filter(id=target.id).exists())
        self.assertTrue(Server.objects.filter(id=other.id).exists())

    def test_delete_unknown_id_is_404(self):
        unknown = uuid.uuid4()
        r = self.client.post(f"{SERVER_INDEX}delete/{unknown}", {"delete": str(unknown)})
        self.assertEqual(r.status_code, 404)


class PerPageTests(LoggedInTestCase):
    def test_per_page_on_fresh_session(self):
        r = self.client.post(SERVER_INDEX, {"perPage2": "10"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.session["per_page"], 10)

    def test_per_page_not_a_number_is_ignored(self):
        r = self.client.post(SERVER_INDEX, {"perPage2": "abc"})
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(self.client.session["per_page"], 1)

    def test_per_page_is_clamped(self):
        _server("one")
        for value, expected in [("0", 1), ("-5", 1), ("5000", 1000)]:
            r = self.client.post(SERVER_INDEX, {"perPage2": value})
            self.assertEqual(r.status_code, 200, value)
            self.assertEqual(self.client.session["per_page"], expected, value)

    def test_per_page_is_remembered(self):
        self.client.post(SERVER_INDEX, {"perPage2": "7"})
        self.client.get(SERVER_INDEX)
        self.assertEqual(self.client.session["per_page"], 7)


class RepoUniquenessTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        self.server = _server("git")
        self.url = "https://git.invalid/team/project.git"

    def _add_repo(self, name: str, branch: str):
        data = {"name": name, "server": self.server.id, "url": self.url, "branch": branch, "_continue": "Save"}
        return self.client.post("/aGit2Git/repo/add/", data)

    def test_same_url_different_branches_allowed(self):
        self._add_repo("project", "main")
        self._add_repo("project", "develop")
        self.assertEqual(Repo.objects.filter(url=self.url).count(), 2)

    def test_same_url_same_branch_rejected_in_form(self):
        self._add_repo("project", "main")
        r = self._add_repo("project copy", "main")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "already exists with the same branch")
        self.assertEqual(Repo.objects.filter(url=self.url).count(), 1)

    def test_empty_branch_is_stored_as_null_and_only_once(self):
        self._add_repo("project", "")
        self.assertIsNone(Repo.objects.get(url=self.url).branch)
        r = self._add_repo("project again", "")
        self.assertContains(r, "already exists with the same branch")
        self.assertEqual(Repo.objects.filter(url=self.url).count(), 1)

    def test_str_shows_branch(self):
        self._add_repo("project", "main")
        self.assertEqual(str(Repo.objects.get(url=self.url)), "project (main)")


class SelfReferenceTests(LoggedInTestCase):
    def test_repo_pair_source_must_differ_from_target(self):
        repo = Repo.objects.create(name="r", url="https://r.invalid/r.git", server=_server("srv"))
        data = {"name": "pair", "source": repo.id, "target": repo.id, "_continue": "Save"}
        r = self.client.post("/aGit2Git/repopair/add/", data)
        self.assertContains(r, "Source and target must be different repos.")
        self.assertFalse(RepoPair.objects.exists())

    def test_component_cannot_depend_on_itself(self):
        c = Component.objects.create(name="lib")
        r = self.client.post("/aComponents/dependencies/add/", {"component": c.id, "uses": c.id, "_continue": "Save"})
        self.assertContains(r, "A component cannot depend on itself.")
        self.assertFalse(Dependencies.objects.exists())

    def test_constraints_also_hold_in_the_database(self):
        a = Component.objects.create(name="a")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Dependencies.objects.create(component=a, uses=a)


class CheckDataMigrationTests(TransactionTestCase):
    """0012 must refuse to migrate when existing rows break the new constraints"""

    before = [("aGit2Git", "0011_rename_url_repo_rename_urlpair_repopair_and_more")]
    after = [("aGit2Git", "0012_check_data_for_constraints")]

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.before)
        self.executor.loader.build_graph()
        old = self.executor.loader.project_state(self.before).apps
        server = old.get_model("aGit2Git", "Server").objects.create(name="s", url="https://s.invalid/")
        Repo_ = old.get_model("aGit2Git", "Repo")
        self.repo = Repo_.objects.create(name="r", url="https://s.invalid/r.git", server=server, branch="")
        self.pair = old.get_model("aGit2Git", "RepoPair").objects.create(
            name="loop", source=self.repo, target=self.repo
        )
        self.old_apps = old

    def tearDown(self):
        # back to the latest schema for the other tests; the bad rows would block that
        self.old_apps.get_model("aGit2Git", "RepoPair").objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _migrate_forward(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)

    def test_refuses_and_changes_nothing(self):
        with self.assertRaisesRegex(RuntimeError, "repo pair 'loop' has the same repo as source and target"):
            self._migrate_forward()
        # rolled back: the empty branch was not converted
        self.assertEqual(self.old_apps.get_model("aGit2Git", "Repo").objects.get().branch, "")

    def test_passes_after_fix_and_normalises_empty_branch(self):
        self.pair.delete()
        self._migrate_forward()
        self.assertIsNone(self.old_apps.get_model("aGit2Git", "Repo").objects.get().branch)


class IndexQueryCountTests(LoggedInTestCase):
    """foreign keys shown in the index must not cost one query per row"""

    def _count_queries(self, n_repos: int) -> int:
        Repo.objects.all().delete()
        for i in range(n_repos):
            Repo.objects.create(name=f"r{i}", url=f"https://r{i}.invalid/", server=_server(f"s{n_repos}-{i}"))
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get("/aGit2Git/repo/")
        self.assertEqual(r.status_code, 200)
        return len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_rows(self):
        self.assertEqual(self._count_queries(2), self._count_queries(4))


class BooleanFilterTests(LoggedInTestCase):
    """boolean columns filter on an exact yes/no value instead of a text match"""

    def setUp(self):
        super().setUp()
        Server.objects.create(name="inside", url="https://inside.invalid/", internal=True)
        Server.objects.create(name="outside", url="https://outside.invalid/", internal=False)

    def _shown(self, value: str) -> set[str]:
        r = self.client.post(SERVER_INDEX, {"filter-internal": value})
        self.assertEqual(r.status_code, 200)
        return {name for name in ("inside", "outside") if f">{name}<" in r.content.decode()}

    def test_true_values(self):
        for value in ("yes", "Y", "true", "True", "1", "on"):
            self.assertEqual(self._shown(value), {"inside"}, value)

    def test_false_values(self):
        for value in ("no", "N", "false", "False", "0", "off"):
            self.assertEqual(self._shown(value), {"outside"}, value)

    def test_unrecognised_value_does_not_filter(self):
        self.assertEqual(self._shown("maybe"), {"inside", "outside"})

    def test_star_clears_the_filter(self):
        self._shown("no")
        self.assertEqual(self._shown("*"), {"inside", "outside"})

    def test_text_fields_still_use_contains(self):
        r = self.client.post(SERVER_INDEX, {"filter-name": "INSI"})
        self.assertContains(r, ">inside<")
        self.assertNotContains(r, ">outside<")


class SortAndClearTests(LoggedInTestCase):
    """header links sort (asc -> desc -> off), Cs clears sorting, Cf clears the filters"""

    NAMES = ("alpha", "bravo", "charlie")

    def setUp(self):
        super().setUp()
        # urls in the opposite order of the names
        for name, url in zip(
            self.NAMES, ("https://z.invalid/", "https://y.invalid/", "https://x.invalid/"), strict=True
        ):
            Server.objects.create(name=name, url=url)

    def _order(self, path=SERVER_INDEX, names=NAMES) -> list[str]:
        content = self.client.get(path).content.decode()
        return sorted((n for n in names if f">{n}<" in content), key=lambda n: content.index(f">{n}<"))

    def _click(self, query: str, path=SERVER_INDEX):
        r = self.client.get(f"{path}?{query}")
        self.assertRedirects(r, path, fetch_redirect_response=False)  # clean url, refresh does not toggle again

    def test_default_order_is_the_model_ordering(self):
        self.assertEqual(self._order(), ["alpha", "bravo", "charlie"])

    def test_header_cycles_ascending_descending_off(self):
        self._click("sort-Url")
        self.assertEqual(self._order(), ["charlie", "bravo", "alpha"])  # url ascending
        self._click("sort-Url")
        self.assertEqual(self._order(), ["alpha", "bravo", "charlie"])  # url descending
        self._click("sort-Url")
        self.assertEqual(self._order(), ["alpha", "bravo", "charlie"])  # off: model ordering
        self.assertNotIn(f"{SERVER_INDEX}sort", self.client.session)

    def test_other_column_starts_ascending(self):
        self._click("sort-Name")
        self._click("sort-Name")  # name descending
        self._click("sort-Url")
        self.assertEqual(self._order(), ["charlie", "bravo", "alpha"])

    def test_indicator_on_sorted_column(self):
        self._click("sort-Name")
        self.assertContains(self.client.get(SERVER_INDEX), "Name ▲")
        self._click("sort-Name")
        self.assertContains(self.client.get(SERVER_INDEX), "Name ▼")

    def test_clear_sorting(self):
        self._click("sort-Url")
        self._click("clear-sorting-all")
        self.assertEqual(self._order(), ["alpha", "bravo", "charlie"])

    def test_unknown_column_is_ignored(self):
        self._click("sort-NoSuchColumn")
        self.assertEqual(self._order(), ["alpha", "bravo", "charlie"])

    def test_foreign_key_column_sorts_on_the_related_name(self):
        servers = {s.name: s for s in Server.objects.all()}
        # repo names in the opposite order of their server names
        for repo, server in (("r3", "alpha"), ("r2", "bravo"), ("r1", "charlie")):
            Repo.objects.create(name=repo, url=f"https://{repo}.invalid/", server=servers[server])
        repo_index = "/aGit2Git/repo/"
        self.assertEqual(self._order(repo_index, ("r1", "r2", "r3")), ["r1", "r2", "r3"])
        self._click("sort-Server", repo_index)
        self.assertEqual(self._order(repo_index, ("r1", "r2", "r3")), ["r3", "r2", "r1"])

    def test_clear_filters(self):
        self.client.post(SERVER_INDEX, {"filter-name": "alp"})
        self.assertEqual(self._order(), ["alpha"])
        self._click("clear-filters-all")
        self.assertEqual(self._order(), ["alpha", "bravo", "charlie"])

    def test_clear_filters_keeps_other_pages_filters(self):
        self.client.post(SERVER_INDEX, {"filter-name": "alp"})
        self.client.post("/aGit2Git/repo/", {"filter-name": "x"})
        self._click("clear-filters-all")
        self.assertEqual(self.client.session["/aGit2Git/repo/filter_dict"]["filter-name"], "x")

    def test_old_sort_route_is_gone(self):
        self.assertEqual(self.client.get(f"{SERVER_INDEX}sort/Name").status_code, 404)


class AdminDateFormatTests(TestCase):
    def test_admin_list_shows_ymd_his(self):
        admin = User.objects.create_superuser("admin", password="not-used")
        self.client.force_login(admin)
        _server("dated")
        r = self.client.get("/admin/aGit2Git/server/")
        self.assertRegex(r.content.decode(), r">\d{6}-\d{6}<")


class PermissionTests(TestCase):
    """every logged-in user may view; add/change/delete need the django permission (or superuser)"""

    def setUp(self):
        self.server = _server("existing")
        self.edit_url = f"{SERVER_INDEX}edit/{self.server.id}"
        self.delete_url = f"{SERVER_INDEX}delete/{self.server.id}"

    def _login(self, *perms: str, superuser: bool = False) -> User:
        if superuser:
            user = User.objects.create_superuser("boss", password="not-used")
        else:
            user = User.objects.create_user("someone", password="not-used")
        if perms:
            group = Group.objects.create(name="g2g editors")  # a local group, as made in the admin
            group.permissions.set(Permission.objects.filter(codename__in=perms))
            user.groups.add(group)
        self.client.force_login(user)
        return user

    def _add(self):
        return self.client.post(f"{SERVER_INDEX}add/", {"name": "new", "url": "https://new.invalid/", "_continue": "1"})

    def _change(self):
        return self.client.post(self.edit_url, {"name": "renamed", "url": self.server.url, "_continue": "1"})

    def test_plain_user_can_view(self):
        self._login()
        r = self.client.get(SERVER_INDEX)
        self.assertContains(r, ">existing<")
        self.assertNotContains(r, f'href="{SERVER_INDEX}add/"')  # no New link
        r = self.client.get(self.edit_url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Read only")
        self.assertNotContains(r, 'value="Save"')

    def test_plain_user_cannot_change_anything(self):
        self._login()
        self.assertEqual(self._add().status_code, 403)
        self.assertEqual(self.client.get(f"{SERVER_INDEX}add/").status_code, 403)
        self.assertEqual(self._change().status_code, 403)
        self.assertEqual(self.client.get(self.delete_url).status_code, 403)
        self.assertEqual(self.client.post(self.delete_url, {"delete": "1"}).status_code, 403)
        self.server.refresh_from_db()
        self.assertEqual(self.server.name, "existing")
        self.assertEqual(Server.objects.count(), 1)

    def test_group_permissions_are_per_action(self):
        self._login("change_server")  # may change, not add or delete
        self.assertEqual(self._change().status_code, 200)  # saved; "Save" shows the form again
        self.server.refresh_from_db()
        self.assertEqual(self.server.name, "renamed")
        r = self.client.get(self.edit_url)
        self.assertContains(r, 'value="Save"')
        self.assertNotContains(r, "Save and add another")
        self.assertNotContains(r, self.delete_url)
        self.assertEqual(self._add().status_code, 403)
        self.assertEqual(self.client.post(self.delete_url, {"delete": "1"}).status_code, 403)

    def test_group_with_all_permissions(self):
        self._login("add_server", "change_server", "delete_server")
        self.assertContains(self.client.get(SERVER_INDEX), f'href="{SERVER_INDEX}add/"')
        self.assertEqual(self._add().status_code, 302)
        self.assertEqual(self.client.post(self.delete_url, {"delete": "1"}).status_code, 302)
        self.assertFalse(Server.objects.filter(id=self.server.id).exists())

    def test_superuser_may_do_everything(self):
        self._login(superuser=True)
        self.assertEqual(self._add().status_code, 302)
        self.assertEqual(self._change().status_code, 200)  # saved; "Save" shows the form again
        self.server.refresh_from_db()
        self.assertEqual(self.server.name, "renamed")
        self.assertEqual(self.client.post(self.delete_url, {"delete": "1"}).status_code, 302)


class AdminLinkTests(TestCase):
    def test_admin_link_only_for_staff(self):
        plain = User.objects.create_user("plain", password="not-used")
        staff = User.objects.create_user("staffer", password="not-used", is_staff=True)
        self.client.force_login(plain)
        self.assertNotContains(self.client.get(SERVER_INDEX), 'href="/admin/"')
        self.client.force_login(staff)
        self.assertContains(self.client.get(SERVER_INDEX), 'href="/admin/"')


class UrlLinkTests(TestCase):
    """url fields in the lists are links to the address, opened in a new tab"""

    def setUp(self):
        self.client.force_login(User.objects.create_user("viewer", password="not-used"))

    def test_server_and_repo_urls_are_links(self):
        server = _server("srv")
        Repo.objects.create(name="r", url="https://srv.invalid/team/r.git", server=server)
        for path, url in (
            (SERVER_INDEX, "https://srv.invalid/"),
            ("/aGit2Git/repo/", "https://srv.invalid/team/r.git"),
        ):
            self.assertContains(
                self.client.get(path),
                f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>',
                html=True,
            )

    def test_only_http_urls_become_links(self):
        # bypasses the form validation, like a value from a restored dump
        Server.objects.create(name="bad", url="javascript:alert(1)")
        r = self.client.get(SERVER_INDEX)
        self.assertContains(r, "javascript:alert(1)")
        self.assertNotContains(r, 'href="javascript:')


class BulkDeleteTests(TestCase):
    """the "Delete selected" button: confirmation (with what cascades) first, then the delete"""

    def setUp(self):
        self.a = _server("a")
        self.b = _server("b")
        self.keep = _server("keep")
        Repo.objects.create(name="r", url="https://a.invalid/r.git", server=self.a)  # deleted with server a

    def _login(self, *perms: str, superuser: bool = False):
        if superuser:
            user = User.objects.create_superuser("boss", password="not-used")
        else:
            user = User.objects.create_user("someone", password="not-used")
            user.user_permissions.set(Permission.objects.filter(codename__in=perms))
        self.client.force_login(user)

    def _post(self, *ids, confirm: bool = False):
        data = {"bulk_delete": "1", "selected": [str(i) for i in ids]}
        if confirm:
            data["confirm"] = "1"
        return self.client.post(SERVER_INDEX, data)

    def test_no_selection_boxes_or_button_without_delete_permission(self):
        self._login()
        r = self.client.get(SERVER_INDEX)
        self.assertNotContains(r, 'name="selected"')
        self.assertNotContains(r, "name='selected'")
        self.assertNotContains(r, "Delete selected")
        self.assertEqual(self._post(self.a.id, confirm=True).status_code, 403)
        self.assertEqual(Server.objects.count(), 3)

    def test_list_has_boxes_and_disabled_button(self):
        self._login(superuser=True)
        r = self.client.get(SERVER_INDEX)
        self.assertContains(r, f"name='selected' value='{self.a.id}'")
        self.assertContains(r, 'id="select-all"')
        self.assertContains(r, 'id="bulk-delete"')

    def test_first_a_confirmation_with_the_cascade(self):
        self._login(superuser=True)
        r = self._post(self.a.id, self.b.id)
        self.assertContains(r, "Delete 2 servers?")
        self.assertContains(r, "<li>1 repos</li>", html=True)
        self.assertEqual(Server.objects.count(), 3)  # nothing deleted yet

    def test_confirmed_delete(self):
        self._login(superuser=True)
        r = self._post(self.a.id, self.b.id, confirm=True)
        self.assertRedirects(r, SERVER_INDEX, fetch_redirect_response=False)
        self.assertEqual(list(Server.objects.values_list("name", flat=True)), ["keep"])
        self.assertFalse(Repo.objects.exists())

    def test_cascade_needs_delete_permission_on_the_related_items_too(self):
        self._login("delete_server", "view_server")  # may delete servers, not repos
        r = self._post(self.a.id)
        self.assertContains(r, "Delete 1 server?")
        self.assertContains(r, "You may not delete repos, so nothing is deleted.")
        self.assertNotContains(r, 'name="confirm"')
        self.assertEqual(self._post(self.a.id, confirm=True).status_code, 403)
        self.assertEqual(Server.objects.count(), 3)
        # a server without repos can be deleted with only the server permission
        self.assertEqual(self._post(self.b.id, confirm=True).status_code, 302)
        self.assertFalse(Server.objects.filter(id=self.b.id).exists())

    def test_invalid_or_empty_selection_goes_back_to_the_list(self):
        self._login(superuser=True)
        self.assertRedirects(self._post("not-an-id", confirm=True), SERVER_INDEX, fetch_redirect_response=False)
        self.assertRedirects(self._post(), SERVER_INDEX, fetch_redirect_response=False)
        self.assertEqual(Server.objects.count(), 3)


class SingleDeleteCascadeTests(TestCase):
    """the Delete page of one item shows what cascades and needs the permissions for it, as the bulk delete"""

    def setUp(self):
        self.server = _server("with-repo")
        self.empty = _server("no-repos")
        Repo.objects.create(name="r", url="https://w.invalid/r.git", server=self.server)
        self.url = f"{SERVER_INDEX}delete/{self.server.id}"

    def _login(self, *perms: str, superuser: bool = False):
        if superuser:
            user = User.objects.create_superuser("boss", password="not-used")
        else:
            user = User.objects.create_user("someone", password="not-used")
            user.user_permissions.set(Permission.objects.filter(codename__in=perms))
        self.client.force_login(user)

    def test_delete_page_shows_the_cascade(self):
        self._login(superuser=True)
        r = self.client.get(self.url)
        self.assertContains(r, "<li>1 repos</li>", html=True)
        self.assertContains(r, 'value="Delete"')

    def test_missing_permission_for_the_cascade(self):
        self._login("delete_server")
        r = self.client.get(self.url)
        self.assertContains(r, "You may not delete repos, so nothing is deleted.")
        self.assertNotContains(r, 'value="Delete"')
        self.assertEqual(self.client.post(self.url, {"delete": "1"}).status_code, 403)
        self.assertTrue(Server.objects.filter(id=self.server.id).exists())
        # nothing cascades: the server permission is enough
        r = self.client.post(f"{SERVER_INDEX}delete/{self.empty.id}", {"delete": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Server.objects.filter(id=self.empty.id).exists())


class CheckRunnerTests(TestCase):
    """manage.py check_runner: the Run configuration, step by step (docs/run-design.md)"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "a.sh").write_text("echo hi\n")
        self.runs = self.root / "runs"
        self.runs.mkdir(mode=0o700)
        self.allowlist = self.root / "scripts.toml"
        self.allowlist.write_text(
            '[groups]\nops = "CN=Ops,OU=Groups,DC=Corp"\n\n'
            '[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n\n'
            '[scripts.b]\nfile = "a.sh"\ngroups = ["local:g2g hotfix"]\n'
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args) -> str:
        out = io.StringIO()
        with override_settings(RUNNER_ALLOWLIST=str(self.allowlist), RUNNER_RUNS_DIR=str(self.runs)):
            call_command("check_runner", *args, stdout=out)
        return out.getvalue()

    def test_switched_off(self):
        out = io.StringIO()
        with override_settings(RUNNER_ALLOWLIST="", RUNNER_RUNS_DIR=""):
            call_command("check_runner", stdout=out)
        self.assertIn("Run is switched off", out.getvalue())

    def test_half_configured_fails(self):
        with (
            override_settings(RUNNER_ALLOWLIST=str(self.allowlist), RUNNER_RUNS_DIR=""),
            self.assertRaises(CommandError),
        ):
            call_command("check_runner", stdout=io.StringIO())

    def test_valid_configuration(self):
        out = self._run()
        self.assertIn("2 scripts (a, b)", out)
        self.assertIn(f"ok    runs directory {self.runs}", out)
        self.assertIn("local group 'g2g hotfix' does not exist", out)
        Group.objects.create(name="g2g hotfix")
        self.assertIn("local groups exist: g2g hotfix", self._run())

    def test_invalid_allowlist_fails_with_the_reason(self):
        self.allowlist.write_text('[scripts.a]\nfile = "a.sh"\ngroups = ["ops"]\n')  # ops is not in [groups]
        out = io.StringIO()
        with (
            override_settings(RUNNER_ALLOWLIST=str(self.allowlist), RUNNER_RUNS_DIR=str(self.runs)),
            self.assertRaises(CommandError),
        ):
            call_command("check_runner", stdout=out)
        self.assertIn("FAIL  allowlist", out.getvalue())
        self.assertIn("'ops' is not in [groups]", out.getvalue())

    def test_user_shows_the_scripts_they_may_run(self):
        user = User.objects.create_user("jdoe", password="not-used")
        user.groups.add(Group.objects.create(name="g2g hotfix"))
        ldap_user = mock.Mock(dn="CN=John Doe,OU=Users,DC=Corp", group_dns={"cn=ops, ou=groups,dc=corp"})
        with (
            mock.patch("django_auth_ldap.backend._LDAPUser", return_value=ldap_user),
            mock.patch("appLogin.backends.LDAPBackend.to_sam_account_name", return_value="jdoe"),
        ):
            out = self._run("--user", "john.doe@corp")
        self.assertIn("user jdoe may run: a, b", out)  # a through the LDAP group (other spelling), b through local


class RunTests(TransactionTestCase):
    """Run step 2: start a script, follow it, download its output (docs/run-design.md; Flask spec §16).

    TransactionTestCase: the run's thread has its own database connection and must see the rows."""

    SCRIPTS = {
        "ok": 'echo "hello $RUNNER_USER"\necho bye\n',
        "fail": "echo oops\nexit 3\n",
        "slow": "echo start\nsleep 3\necho end\n",
        "html": 'echo "<b>bold</b>"\n',
        "env": "env\n",
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "scripts").mkdir()
        for name, body in self.SCRIPTS.items():
            (root / "scripts" / f"{name}.sh").write_text(body)
        entries = "".join(f'[scripts.{n}]\nfile = "{n}.sh"\ngroups = ["local:runners"]\n\n' for n in self.SCRIPTS)
        (root / "scripts.toml").write_text(entries)
        self.runs = root / "runs"
        self.settings = override_settings(RUNNER_ALLOWLIST=str(root / "scripts.toml"), RUNNER_RUNS_DIR=str(self.runs))
        self.settings.enable()
        run_service.reset_runner()
        self.runner_user = User.objects.create_user("runner", password="not-used")
        self.runner_user.groups.add(Group.objects.create(name="runners"))
        self.client.force_login(self.runner_user)
        self.scripts = {n: Script.objects.create(name=n, allowlist_id=n) for n in self.SCRIPTS}

    def tearDown(self):
        for _ in range(100):  # let a run that is still going finish, so its thread does not outlive the test
            if not Run.objects.filter(status=Run.RUNNING).exists():
                break
            time.sleep(0.1)
        self.settings.disable()
        run_service.reset_runner()
        self.tmp.cleanup()

    def _start(self, name: str):
        return self.client.post(f"/aGit2Git/script/run/{self.scripts[name].id}")

    def _finished(self, run_id) -> Run:
        for _ in range(100):
            run = Run.objects.get(pk=run_id)
            if not run.running:
                return run
            time.sleep(0.1)
        raise AssertionError("the run did not finish")

    def _run_id(self, response) -> str:
        self.assertEqual(response.status_code, 303)
        return response["Location"].rsplit("/", 1)[1]

    def test_a_run_from_start_to_download(self):
        run_id = self._run_id(self._start("ok"))
        run = self._finished(run_id)
        self.assertEqual((run.status, run.exit_code, run.script_id), ("succeeded", 0, "ok"))
        self.assertEqual((run.started_by, run.started_by_name), (self.runner_user, "runner"))
        self.assertIsNotNone(run.pid)
        self.assertGreater(run.output_bytes, 0)
        page = self.client.get(f"/aGit2Git/run/{run_id}")
        self.assertContains(page, "hello runner")
        self.assertContains(page, "Download the output")
        download = self.client.get(f"/aGit2Git/run/{run_id}/download")
        self.assertEqual(download["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("attachment", download["Content-Disposition"])
        body = b"".join(download.streaming_content)
        self.assertIn(b"hello runner\nbye\n", body)
        self.assertIn(b"[exit code 0]", body)

    def test_a_failing_script(self):
        run = self._finished(self._run_id(self._start("fail")))
        self.assertEqual((run.status, run.exit_code), ("failed", 3))

    def test_others_may_not_run_or_see_it(self):
        run_id = self._run_id(self._start("ok"))
        self._finished(run_id)
        self.client.force_login(User.objects.create_user("other", password="not-used"))
        self.assertEqual(self._start("ok").status_code, 403)
        for url in (f"/aGit2Git/run/{run_id}", f"/aGit2Git/run/{run_id}/output", f"/aGit2Git/run/{run_id}/download"):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_one_run_at_a_time(self):
        first = self._run_id(self._start("slow"))
        second = self._start("slow")  # still running: sent to the run that is going
        self.assertRedirects(second, f"/aGit2Git/run/{first}?busy=1", fetch_redirect_response=False)
        self.assertContains(self.client.get(f"/aGit2Git/run/{first}?busy=1"), "This script is already running")
        self.assertEqual(self.client.get(f"/aGit2Git/run/{first}/download").status_code, 409)  # not finished
        self._finished(first)
        self.assertEqual(self._start("slow").status_code, 303)  # and again once it has finished

    def test_live_output_from_an_offset(self):
        run_id = self._run_id(self._start("ok"))
        self._finished(run_id)
        whole = self.client.get(f"/aGit2Git/run/{run_id}/output?offset=0")
        self.assertEqual(whole["X-Run-Status"], "succeeded")
        self.assertEqual(int(whole["X-Next-Offset"]), len(whole.content))
        rest = self.client.get(f"/aGit2Git/run/{run_id}/output?offset=6")
        self.assertEqual(rest.content, whole.content[6:])
        self.assertEqual(self.client.get(f"/aGit2Git/run/{run_id}/output?offset=nonsense").status_code, 200)

    def test_output_is_never_markup(self):
        run_id = self._run_id(self._start("html"))
        self._finished(run_id)
        page = self.client.get(f"/aGit2Git/run/{run_id}")
        self.assertContains(page, "&lt;b&gt;bold&lt;/b&gt;")
        self.assertNotContains(page, "<b>bold</b>")

    def test_the_script_does_not_see_the_server_secrets(self):
        run_id = self._run_id(self._start("env"))
        self._finished(run_id)
        env = output_path_of(run_id).read_text()
        self.assertIn("RUNNER_SCRIPT=env", env)
        for secret in ("DJANGO_SECRET_KEY", "LDAP_BIND_PW", "POSTGRES_PASSWORD", "DJANGO_DATABASE_URL"):
            self.assertNotIn(secret, env)

    def test_run_off_or_unknown(self):
        with override_settings(RUNNER_ALLOWLIST="", RUNNER_RUNS_DIR=""):
            run_service.reset_runner()
            self.assertEqual(self._start("ok").status_code, 503)
        run_service.reset_runner()
        no_id = Script.objects.create(name="no id")
        self.assertEqual(self.client.post(f"/aGit2Git/script/run/{no_id.id}").status_code, 404)
        gone = Script.objects.create(name="gone", allowlist_id="not-in-allowlist")
        self.assertEqual(self.client.post(f"/aGit2Git/script/run/{gone.id}").status_code, 404)
        self.assertEqual(self.client.get(f"/aGit2Git/script/run/{self.scripts['ok'].id}").status_code, 405)

    def test_run_panel_on_the_script_page(self):
        page = self.client.get(f"/aGit2Git/script/edit/{self.scripts['ok'].id}")
        self.assertContains(page, f'action="/aGit2Git/script/run/{self.scripts["ok"].id}"')
        self.client.force_login(User.objects.create_user("other", password="not-used"))
        page = self.client.get(f"/aGit2Git/script/edit/{self.scripts['ok'].id}")
        self.assertContains(page, "This cannot be run: you may not run its script.")
        self.assertNotContains(page, "/aGit2Git/script/run/")


def output_path_of(run_id) -> Path:
    return run_service.output_path(Run.objects.get(pk=run_id))


class LoginGroupsTests(TestCase):
    """the LDAP group DNs are kept in the session at login, for the Run permissions"""

    def test_ldap_user_groups_go_into_the_session(self):
        user = User.objects.create_user("jdoe", password="not-used")
        user.ldap_user = mock.Mock(group_dns={"CN=B,DC=Corp", "cn=a,dc=corp"})
        request = mock.Mock(session={})
        user_logged_in.send(sender=User, request=request, user=user)
        self.assertEqual(request.session[LDAP_GROUP_DNS], ["CN=B,DC=Corp", "cn=a,dc=corp"])

    def test_a_local_user_has_none(self):
        request = mock.Mock(session={})
        user_logged_in.send(sender=User, request=request, user=User.objects.create_user("local", password="x"))
        self.assertEqual(request.session[LDAP_GROUP_DNS], [])


class RepoPairRunTests(RunTests):
    """Run step 3: the Run button on a repo pair (its copy type's script), the run list, the menu entry"""

    def setUp(self):
        super().setUp()
        server = _server("srv")
        source = Repo.objects.create(name="src", url="https://srv.invalid/src.git", server=server)
        target = Repo.objects.create(name="dst", url="https://srv.invalid/dst.git", server=server)
        self.copy_type = CopyType.objects.create(name="manual copy", manual=True, script=self.scripts["ok"])
        self.pair = RepoPair.objects.create(name="pair", source=source, target=target, copyType=self.copy_type)

    def _pair_page(self):
        return self.client.get(f"/aGit2Git/repopair/edit/{self.pair.id}")

    def _start_pair(self):
        return self.client.post(f"/aGit2Git/repopair/run/{self.pair.id}")

    def test_a_runnable_pair(self):
        self.assertContains(self._pair_page(), f'action="/aGit2Git/repopair/run/{self.pair.id}"')
        run = self._finished(self._run_id(self._start_pair()))
        self.assertEqual((run.status, run.script_id, run.repo_pair), ("succeeded", "ok", self.pair))
        page = self._pair_page()
        self.assertContains(page, f'href="/aGit2Git/run/{run.id}"')  # its last runs
        self.assertContains(self.client.get(f"/aGit2Git/run/{run.id}"), "Repo pair")

    def test_why_a_pair_cannot_run(self):
        no_id = Script.objects.create(name="no id")
        gone = Script.objects.create(name="gone", allowlist_id="not-in-allowlist")
        cases = [
            ({"copyType": None}, {}, "this repo pair has no copy type"),
            ({}, {"manual": False}, "its copy type manual copy is not manual"),
            ({}, {"script": None}, "its copy type manual copy has no script"),
            ({}, {"script": no_id}, "the script no id has no allowlist id"),
            ({}, {"script": gone}, "the allowlist id not-in-allowlist is not in the allowlist"),
        ]
        for pair_fields, type_fields, reason in cases:
            CopyType.objects.filter(pk=self.copy_type.pk).update(
                **({"manual": True, "script": self.scripts["ok"]} | type_fields)
            )
            RepoPair.objects.filter(pk=self.pair.pk).update(**({"copyType": self.copy_type} | pair_fields))
            self.assertContains(self._pair_page(), f"This cannot be run: {reason}.", msg_prefix=reason)
            self.assertNotContains(self._pair_page(), "/aGit2Git/repopair/run/", msg_prefix=reason)
            self.assertIn(self._start_pair().status_code, (404, 409), reason)
        self.assertFalse(Run.objects.exists())

    def test_others_may_not_run_the_pair(self):
        self.client.force_login(User.objects.create_user("other", password="not-used"))
        self.assertContains(self._pair_page(), "This cannot be run: you may not run its script.")
        self.assertEqual(self._start_pair().status_code, 403)

    def test_the_run_list_shows_only_runs_the_user_may_see(self):
        mine = self._finished(self._run_id(self._start_pair()))
        hidden = Run.objects.create(script_id="not-in-allowlist", started_by_name="x", status="succeeded")
        page = self.client.get("/aGit2Git/run/")
        self.assertContains(page, f'href="/aGit2Git/run/{mine.id}"')
        self.assertContains(page, f'href="/aGit2Git/repopair/edit/{self.pair.id}"')
        self.assertNotContains(page, str(hidden.id))
        self.client.force_login(User.objects.create_user("other", password="not-used"))
        self.assertContains(self.client.get("/aGit2Git/run/"), "No runs yet")

    def test_menu_entry(self):
        html = self.client.get("/aGit2Git/run/").content.decode()
        active = re.findall(r'<a class="nav-link active" aria-current="true"\s+href="([^"]+)">([^<]+)</a>', html)
        self.assertEqual(active, [("/aGit2Git/run/", "Runs")])
        run = self._finished(self._run_id(self._start_pair()))  # a run's page: the menu, with Runs highlighted
        html = self.client.get(f"/aGit2Git/run/{run.id}").content.decode()
        active = re.findall(r'<a class="nav-link active" aria-current="true"\s+href="([^"]+)">([^<]+)</a>', html)
        self.assertEqual(active, [("/aGit2Git/run/", "Runs")])


class RunHousekeepingTests(RunTests):
    """Run step 4: purging old runs, interrupted runs after a restart, reloading the allowlist"""

    def setUp(self):
        super().setUp()
        cache.delete(run_service.GENERATION_KEY)
        self.allowlist = Path(settings.RUNNER_ALLOWLIST)

    def _old_run(self, days: int, status: str = "succeeded") -> Run:
        run = Run.objects.create(script_id="ok", started_by_name="x", status=status)
        Run.objects.filter(pk=run.pk).update(started_at=timezone.now() - timedelta(days=days))
        self.runs.mkdir(exist_ok=True)
        run_service.output_path(run).write_text("old output\n")
        return Run.objects.get(pk=run.pk)

    def test_purge_runs_command(self):
        old, recent = self._old_run(100), self._old_run(10)
        out = io.StringIO()
        call_command("purge_runs", "--dry-run", stdout=out)
        self.assertIn("would delete 1 runs older than 90 days", out.getvalue())
        self.assertTrue(Run.objects.filter(pk=old.pk).exists())
        call_command("purge_runs", stdout=io.StringIO())
        self.assertFalse(Run.objects.filter(pk=old.pk).exists())
        self.assertFalse(run_service.output_path(old).exists())
        self.assertTrue(Run.objects.filter(pk=recent.pk).exists())
        self.assertTrue(run_service.output_path(recent).exists())

    def test_purge_never_deletes_a_running_run(self):
        running = self._old_run(100, status=Run.RUNNING)
        self.assertEqual(run_service.purge_old_runs(), 0)
        self.assertTrue(Run.objects.filter(pk=running.pk).exists())

    def test_starting_a_run_purges_old_ones(self):
        old = self._old_run(100)
        self._finished(self._run_id(self._start("ok")))
        self.assertFalse(Run.objects.filter(pk=old.pk).exists())

    def test_runs_cut_short_by_a_restart_are_marked_interrupted(self):
        orphan = Run.objects.create(script_id="ok", started_by_name="x")  # running, but nobody holds its lock
        run_service.reset_runner()
        runner = run_service.get_runner()  # a "new process": marks it
        orphan.refresh_from_db()
        self.assertEqual(orphan.status, "interrupted")
        self.assertIsNotNone(orphan.finished_at)

        held = runner.locks.acquire("slow", "someone")  # a run that is really going (in "another process")
        try:
            going = Run.objects.create(script_id="slow", started_by_name="someone")
            too_old = Run.objects.create(script_id="slow", started_by_name="someone")
            Run.objects.filter(pk=too_old.pk).update(started_at=timezone.now() - timedelta(hours=2))
            run_service.mark_interrupted_runs(runner)
            going.refresh_from_db()
            too_old.refresh_from_db()
            self.assertEqual(going.status, Run.RUNNING)  # its lock is held
            self.assertEqual(too_old.status, "interrupted")  # longer than any timeout allows
        finally:
            held.release()

    def _reload(self):
        return self.client.post("/aGit2Git/run/reload", follow=True)

    def test_reload_shows_what_changed(self):
        run_service.get_runner()  # this process has its allowlist already
        self.allowlist.write_text(
            self.allowlist.read_text() + '[scripts.new]\nfile = "ok.sh"\ngroups = ["local:runners"]\n'
        )
        self.assertContains(self._reload(), "The allowlist was reloaded; added: new.")
        self.assertIn("new", run_service.get_runner().scripts)

    def test_an_invalid_allowlist_keeps_the_previous_one(self):
        run_service.get_runner()  # this process has its allowlist already
        self.allowlist.write_text("broken [[[")
        page = self._reload()
        self.assertContains(page, "The allowlist could not be reloaded; the previous one stays in force.")
        self.assertNotContains(page, "Reason:")  # the reason is for staff
        self.assertEqual(self._finished(self._run_id(self._start("ok"))).status, "succeeded")  # still runs
        self.runner_user.is_staff = True
        self.runner_user.save()
        self.client.session.pop("runner_reload_at", None)
        session = self.client.session
        session["runner_reload_at"] = 0
        session.save()
        self.assertContains(self._reload(), "Reason: invalid TOML")

    def test_reload_is_rate_limited(self):
        self._reload()
        self.assertContains(self._reload(), "was reloaded a moment ago")

    def test_another_process_picks_up_a_reload(self):
        runner = run_service.get_runner()
        self.allowlist.write_text(
            self.allowlist.read_text() + '[scripts.new]\nfile = "ok.sh"\ngroups = ["local:runners"]\n'
        )
        self.assertNotIn("new", runner.scripts)  # this "process" has not been told yet
        cache.set(run_service.GENERATION_KEY, 41, timeout=None)  # "another process" reloaded
        self.assertIn("new", run_service.get_runner().scripts)
