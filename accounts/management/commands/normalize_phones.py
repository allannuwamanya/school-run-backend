import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction


def normalize(phone: str) -> str:
    """Mirrors the frontend's normalizePhone() (src/lib/phone.ts in both the
    web and mobile repos) so DB values match what login/register now send."""
    digits = re.sub(r"[^\d+]", "", phone.strip())
    if digits.startswith("+256"):
        return digits
    if digits.startswith("256"):
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+256{digits[1:]}"
    return digits


class Command(BaseCommand):
    help = (
        "One-time cleanup: normalizes every CustomUser.phone to +256XXXXXXXXX. "
        "Pre-existing accounts (created before the frontend started normalizing "
        "on submit) can have stray spaces/dashes or a missing +256 prefix, which "
        "makes the exact-match phone lookup at login fail even with the right "
        "password. Safe to re-run — it's a no-op once everything is canonical."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would change without saving."
        )

    def handle(self, *args, **options):
        User = get_user_model()
        dry_run = options["dry_run"]
        changed = 0
        skipped = 0

        for user in User.objects.exclude(phone__isnull=True).exclude(phone=""):
            cleaned = normalize(user.phone)
            if cleaned == user.phone:
                continue

            self.stdout.write(f"{user.id}: {user.phone!r} -> {cleaned!r}")
            if dry_run:
                changed += 1
                continue

            try:
                with transaction.atomic():
                    user.phone = cleaned
                    user.save(update_fields=["phone"])
                changed += 1
            except IntegrityError:
                self.stderr.write(
                    self.style.ERROR(
                        f"  skipped {user.id}: {cleaned!r} is already taken by another account"
                    )
                )
                skipped += 1

        verb = "Would change" if dry_run else "Changed"
        self.stdout.write(self.style.SUCCESS(f"{verb} {changed} phone number(s), {skipped} skipped."))
