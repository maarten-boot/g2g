from aGit2Git.autoGui import AUTO_GUI
from django.test import SimpleTestCase

from appAutoGui.xauto import _get_form_class, get_known_apps


class AutoGuiTests(SimpleTestCase):
    def test_known_apps_are_the_apps_with_an_autogui(self):
        self.assertEqual(get_known_apps(), ["aGit2Git"])

    def test_form_is_generated_from_the_autogui_fields(self):
        form_class = _get_form_class(AUTO_GUI, "aGit2Git", "Repo")
        self.assertEqual(list(form_class.base_fields), list(AUTO_GUI["models"]["Repo"]["fields"]))
