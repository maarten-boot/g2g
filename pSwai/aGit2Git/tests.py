import uuid

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from aGit2Git.models import Component, Dependencies, Repo, RepoPair, Server

SERVER_INDEX = "/aGit2Git/server/"


def _server(name: str) -> Server:
    return Server.objects.create(name=name, url=f"https://{name}.invalid/")


class LoggedInTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tester", password="not-used")
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
        r = self.client.post("/aGit2Git/dependencies/add/", {"component": c.id, "uses": c.id, "_continue": "Save"})
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
