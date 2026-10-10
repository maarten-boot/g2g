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
        for href in (
            'href="/aGit2Git/"',
            'href="/aComponents/"',
            'href="/aGit2Git/server/"',
            f'href="{COMPONENT_INDEX}"',
        ):
            self.assertIn(href, html)

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
