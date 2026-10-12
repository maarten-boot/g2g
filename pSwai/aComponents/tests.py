import re

from aGit2Git.models import Repo, Server
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from aComponents.models import Component, Dependencies, Feature, Implementation

COMPONENT_INDEX = "/aComponents/component/"


class ComponentPagesTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("tester", password="not-used"))

    def test_crud_under_the_new_app(self):
        repo = Repo.objects.create(
            name="r", url="https://r.invalid/r.git", server=Server.objects.create(name="s", url="https://s.invalid/")
        )
        r = self.client.post(f"{COMPONENT_INDEX}add/", {"name": "lib", "mainRepo": repo.id, "_continue": "1"})
        component = Component.objects.get(name="lib")
        self.assertRedirects(r, f"{COMPONENT_INDEX}edit/{component.id}", fetch_redirect_response=False)
        self.assertEqual(component.mainRepo, repo)
        self.assertContains(self.client.get(COMPONENT_INDEX), ">lib<")

    def test_old_urls_are_gone(self):
        self.assertEqual(self.client.get("/aGit2Git/component/").status_code, 404)

    def test_menu_has_a_section_per_app(self):
        html = self.client.get(COMPONENT_INDEX).content.decode()
        for part in (
            'data-bs-target="#nav-aGit2Git"',
            'data-bs-target="#nav-aComponents"',
            'href="/aGit2Git/server/"',
            f'href="{COMPONENT_INDEX}"',
        ):
            self.assertIn(part, html)

    def test_tables_and_content_types_belong_to_the_new_app(self):
        self.assertEqual(Component._meta.db_table, "aComponents_component")
        for model in (Component, Feature, Implementation, Dependencies):
            self.assertEqual(ContentType.objects.get_for_model(model).app_label, "aComponents")
        self.assertFalse(ContentType.objects.filter(app_label="aGit2Git", model="component").exists())


class MoveMigrationTests(TransactionTestCase):
    """the data in the aGit2Git tables survives the move to aComponents"""

    before = [("aGit2Git", "0013_constraints_and_cleanup"), ("aComponents", None)]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_rows_relations_and_content_types_move(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old = executor.loader.project_state([("aGit2Git", "0013_constraints_and_cleanup")]).apps
        server = old.get_model("aGit2Git", "Server").objects.create(name="s", url="https://s.invalid/")
        repo = old.get_model("aGit2Git", "Repo").objects.create(name="r", url="https://r.invalid/", server=server)
        OldComponent = old.get_model("aGit2Git", "Component")
        lib = OldComponent.objects.create(name="lib", mainRepo=repo)
        app = OldComponent.objects.create(name="app")
        feature = old.get_model("aGit2Git", "Feature").objects.create(name="login")
        old.get_model("aGit2Git", "Implementation").objects.create(component=lib, feature=feature, implemented=True)
        old.get_model("aGit2Git", "Dependencies").objects.create(component=app, uses=lib)
        old_ct = ContentType.objects.get_or_create(app_label="aGit2Git", model="component")[0]

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

        new = executor.loader.project_state(executor.loader.graph.leaf_nodes()).apps
        Component_ = new.get_model("aComponents", "Component")
        moved = Component_.objects.get(id=lib.id)
        self.assertEqual(moved.mainRepo_id, repo.id)
        self.assertEqual(new.get_model("aComponents", "Implementation").objects.get().feature_id, feature.id)
        self.assertEqual(new.get_model("aComponents", "Dependencies").objects.get().uses_id, lib.id)
        old_ct.refresh_from_db()
        self.assertEqual(old_ct.app_label, "aComponents")  # same row: admin history and permissions moved along


class MenuSectionTests(TestCase):
    """the left menu has a collapsible section per app, open for the app you are in"""

    def setUp(self):
        self.client.force_login(User.objects.create_user("viewer", password="not-used"))

    def _sections(self, path: str) -> dict[str, bool]:
        html = self.client.get(path).content.decode()
        return {app: bool(show) for show, app in re.findall(r'<div class="collapse( show)?" id="nav-(\w+)">', html)}

    def test_open_for_the_current_app_only(self):
        self.assertEqual(self._sections(COMPONENT_INDEX), {"aGit2Git": False, "aComponents": True})
        self.assertEqual(self._sections("/aGit2Git/server/"), {"aGit2Git": True, "aComponents": False})

    def test_all_collapsed_on_the_home_page(self):
        self.assertEqual(self._sections("/"), {"aGit2Git": False, "aComponents": False})

    def test_toggle_button_controls_the_section(self):
        html = self.client.get(COMPONENT_INDEX).content.decode()
        self.assertIn('data-bs-target="#nav-aComponents"', html)
        self.assertIn('aria-controls="nav-aGit2Git"', html)


class ForeignKeyLinkTests(TestCase):
    """foreign key cells in the lists link to the page of the related item, also in the other app"""

    def setUp(self):
        self.client.force_login(User.objects.create_user("viewer", password="not-used"))
        self.server = Server.objects.create(name="srv", url="https://srv.invalid/")
        self.repo = Repo.objects.create(name="repo1", url="https://srv.invalid/r.git", server=self.server)

    def test_same_app(self):
        r = self.client.get("/aGit2Git/repo/")
        self.assertContains(r, f'<a href="/aGit2Git/server/edit/{self.server.id}">srv</a>', html=True)

    def test_other_app(self):
        Component.objects.create(name="lib", mainRepo=self.repo)
        r = self.client.get(COMPONENT_INDEX)
        self.assertContains(r, f'<a href="/aGit2Git/repo/edit/{self.repo.id}">repo1</a>', html=True)

    def test_empty_foreign_key_is_an_empty_cell(self):
        Component.objects.create(name="lonely")
        r = self.client.get(COMPONENT_INDEX)
        self.assertContains(r, ">lonely<")
        self.assertNotContains(r, ">None<")

    def test_two_foreign_keys(self):
        lib = Component.objects.create(name="lib")
        login = Feature.objects.create(name="login")
        Implementation.objects.create(component=lib, feature=login)
        r = self.client.get("/aComponents/implementation/")
        self.assertContains(r, f'<a href="/aComponents/component/edit/{lib.id}">lib</a>', html=True)
        self.assertContains(r, f'<a href="/aComponents/feature/edit/{login.id}">login</a>', html=True)


class MenuHighlightTests(TestCase):
    """the menu item of a model stays highlighted on its add/edit pages, e.g. after following a link"""

    def setUp(self):
        self.client.force_login(User.objects.create_user("viewer", password="not-used"))

    def _active(self, path: str) -> list[str]:
        html = self.client.get(path).content.decode()
        return re.findall(r'<a class="nav-link active" aria-current="true"\s+href="([^"]+)"', html)

    def test_edit_page_highlights_its_model(self):
        server = Server.objects.create(name="srv", url="https://srv.invalid/")
        self.assertEqual(self._active(f"/aGit2Git/server/edit/{server.id}"), ["/aGit2Git/server/"])

    def test_similar_names_do_not_both_light_up(self):
        self.assertEqual(self._active("/aGit2Git/repopair/"), ["/aGit2Git/repopair/"])
        self.assertEqual(self._active("/aGit2Git/repo/"), ["/aGit2Git/repo/"])
