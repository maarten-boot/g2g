import datetime

from aGit2Git.autoGui import AUTO_GUI
from django.test import SimpleTestCase

from appAutoGui.xauto import _get_form_class, get_known_apps


class AutoGuiTests(SimpleTestCase):
    def test_known_apps_are_the_apps_with_an_autogui(self):
        self.assertEqual(get_known_apps(), ["aGit2Git"])

    def test_form_is_generated_from_the_autogui_fields(self):
        form_class = _get_form_class(AUTO_GUI, "aGit2Git", "Repo")
        self.assertEqual(list(form_class.base_fields), list(AUTO_GUI["models"]["Repo"]["fields"]))


class LoggingConfigTests(SimpleTestCase):
    def test_a_logger_per_project_app_only(self):
        from django.conf import settings

        loggers = settings.LOGGING["loggers"]
        for app in ("aGit2Git", "appAutoGui", "appLogin"):
            self.assertIn(app, loggers)
        self.assertFalse([name for name in loggers if name.startswith("django.")])


class DateFormatTests(SimpleTestCase):
    def test_datetimes_render_as_ymd_his(self):
        from django.template import Context, Template

        moment = datetime.datetime(2026, 10, 10, 9, 30, 15)
        self.assertEqual(Template("{{ d }}").render(Context({"d": moment})), "261010-093015")


class LogHandlerTests(SimpleTestCase):
    def test_unknown_handlers_from_an_old_env_are_ignored(self):
        import io
        import os
        from contextlib import redirect_stderr
        from unittest import mock

        from pSwai import settings as project_settings

        with mock.patch.dict(os.environ, {"G2G_TEST_HANDLERS": "console,mail_admins,file"}):
            err = io.StringIO()
            with redirect_stderr(err):
                handlers = project_settings._log_handlers("G2G_TEST_HANDLERS")
        self.assertEqual(handlers, ["console"])
        self.assertIn("ignoring unknown log handlers ['mail_admins', 'file']", err.getvalue())
