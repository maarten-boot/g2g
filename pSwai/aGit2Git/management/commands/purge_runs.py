"""Delete the runs older than RUN_HISTORY_DAYS (default 90) with their output files (docs/run-design.md §5).

Run it daily (systemd timer or cron); every start of a run also purges a little, so it works without one.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from aGit2Git.run_service import purge_old_runs


class Command(BaseCommand):
    help = "Delete the runs older than RUN_HISTORY_DAYS, with their output files (never a running one)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="only count what would be deleted")

    def handle(self, *args, **options):
        count = purge_old_runs(dry_run=options["dry_run"])
        verb = "would delete" if options["dry_run"] else "deleted"
        self.stdout.write(f"{verb} {count} runs older than {settings.RUN_HISTORY_DAYS} days")
