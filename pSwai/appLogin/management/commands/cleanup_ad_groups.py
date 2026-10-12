"""Find (and with --delete remove) django groups whose name is no longer an AD group.

Until AUTH_LDAP_MIRROR_GROUPS was turned off, every AD group of a user was copied into a django group.
Those copies are not updated anymore. Groups that still exist in AD are kept: a django group named like an
AD group gives its permissions to that AD group (AUTH_LDAP_FIND_GROUP_PERMS). A group that is not in AD but
has permissions is a local group made on purpose: it is reported and kept.
"""

import ldap
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from ldap.filter import escape_filter_chars

from appLogin.backends import LDAPBackend


class Command(BaseCommand):
    help = "Report (default) or --delete django groups that no longer exist in AD and carry no permissions."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="delete the groups instead of only reporting")

    def handle(self, *args, **options):
        backend = LDAPBackend()
        base_dn = backend.settings.GROUP_SEARCH.base_dn
        groups = list(Group.objects.annotate(members=Count("user", distinct=True), perms=Count("permissions")))

        try:
            with backend.service_connection() as conn:
                in_ad = {group.name for group in groups if self._exists(conn, base_dn, group.name)}
        except ldap.LDAPError as e:
            raise CommandError(f"cannot check the groups in AD, nothing changed: {e}") from e

        gone = [g for g in groups if g.name not in in_ad]
        to_delete = [g for g in gone if g.perms == 0]
        kept_local = [g for g in gone if g.perms > 0]

        self.stdout.write(f"django groups: {len(groups)}, still in AD: {len(in_ad)}, not in AD: {len(gone)}")
        for g in kept_local:
            self.stdout.write(f"  keep   {g.name!r}: not in AD, but has {g.perms} permissions (a local group)")
        for g in to_delete:
            self.stdout.write(f"  {'delete' if options['delete'] else 'would delete'} {g.name!r} ({g.members} members)")

        if options["delete"]:
            Group.objects.filter(pk__in=[g.pk for g in to_delete]).delete()
            self.stdout.write(self.style.SUCCESS(f"deleted {len(to_delete)} groups"))
        elif to_delete:
            self.stdout.write("dry run: nothing deleted, run again with --delete")

    @staticmethod
    def _exists(conn, base_dn: str, name: str) -> bool:
        results = conn.search_s(
            base_dn,
            ldap.SCOPE_SUBTREE,
            f"(&(objectClass=group)(cn={escape_filter_chars(name)}))",
            ["cn"],
        )
        return any(dn for dn, _ in results)  # skip AD referrals (dn None)
