"""
Management command: import records.csv + Attachments/ from a Kintone backup.

Usage
-----
    python manage.py import_kintone_records \\
        --org-id 7 \\
        --csv C:\\KintoneBackup\\records.csv \\
        --attachments C:\\KintoneBackup\\Attachments

Options
-------
--org-id         (required) Primary key of the Organization to import into
--csv            (required) Absolute path to records.csv
--attachments    (optional) Absolute path to the Attachments/ root directory.
                 Omit to skip document upload (import client profiles only).
--link-column    (optional) Override the unique column name (default: auto-detect)
--user-id        (optional) User PK used as the "actor" for audit logs
                 (defaults to the first superuser found)
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.kintone_flatfile_import import import_kintone_records
from core.models import Organization


class Command(BaseCommand):
    help = "Import records.csv + Attachments/ folder from a Kintone backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--org-id",
            type=int,
            required=True,
            help="Primary key of the target Organization.",
        )
        parser.add_argument(
            "--csv",
            required=True,
            metavar="PATH",
            help="Absolute path to records.csv.",
        )
        parser.add_argument(
            "--attachments",
            default=None,
            metavar="DIR",
            help="Absolute path to the Attachments/ root directory "
                 "(omit to skip document upload).",
        )
        parser.add_argument(
            "--link-column",
            default="",
            metavar="COL",
            help="Override the unique column name (default: auto-detect).",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="User PK to record as the import actor (default: first superuser).",
        )

    def handle(self, *args, **options):
        org_id          = options["org_id"]
        csv_path        = options["csv"]
        attachments_dir = options["attachments"]
        link_column     = options["link_column"]
        user_id         = options["user_id"]

        # ── Resolve organization ────────────────────────────────────────────
        try:
            org = Organization.objects.get(pk=org_id)
        except Organization.DoesNotExist:
            raise CommandError(f"Organization with pk={org_id} does not exist.")

        # ── Resolve actor ───────────────────────────────────────────────────
        if user_id is not None:
            try:
                actor = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                raise CommandError(f"User with pk={user_id} does not exist.")
        else:
            actor = User.objects.filter(is_superuser=True).order_by("id").first()
            if actor is None:
                raise CommandError(
                    "No superuser found. Create one first or supply --user-id."
                )

        self.stdout.write(f"Office  : {org.name} (pk={org.pk})")
        self.stdout.write(f"Actor   : {actor.username} (pk={actor.pk})")
        self.stdout.write(f"CSV     : {csv_path}")
        self.stdout.write(f"Attachments: {attachments_dir or '(skipped)'}")
        self.stdout.write("")
        self.stdout.write("Starting import …  (this may take several minutes for large attachment sets)")

        try:
            result = import_kintone_records(
                organization=org,
                actor=actor,
                csv_path=csv_path,
                attachments_dir=attachments_dir,
                link_column=link_column,
            )
        except Exception as exc:
            raise CommandError(f"Import failed: {exc}") from exc

        # ── Summary ─────────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Import complete"))
        self.stdout.write(f"  Clients created          : {result['clients_created']}")
        self.stdout.write(f"  Clients updated (existed): {result['clients_skipped']}")
        self.stdout.write(f"  Documents uploaded        : {result['documents_created']}")
        self.stdout.write(f"  Documents skipped (exist) : {result['documents_skipped']}")
        self.stdout.write(f"  Warnings / errors         : {result['error_count']}")

        if result["errors"]:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Warnings:"))
            for err in result["errors"]:
                self.stdout.write(f"  • {err}")
