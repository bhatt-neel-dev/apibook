"""False-positive report for anomaly alerts.

The launch guardrail (ANOMALY-ALERTS-PLAN.md, PRD §5) is a
dismissal-without-view rate under 40%: an alert nobody bothered to open
before dismissing is our best proxy for "the detector cried wolf". This
report is the input to the day-7/14/30 refine-or-rollback decision.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.projects.models import AlertEvent


class Command(BaseCommand):
    help = "Report the anomaly-alert false-positive proxy rate (dismissed without view)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=7, help="Trailing window in days (default 7)"
        )

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(days=options["days"])
        window = AlertEvent.objects.filter(created_at__gte=since)

        total = window.count()
        viewed = window.filter(viewed_at__isnull=False).count()
        dismissed = window.filter(status=AlertEvent.Status.DISMISSED)
        dismissed_total = dismissed.count()
        dismissed_unviewed = dismissed.filter(viewed_at__isnull=True).count()

        self.stdout.write(f"Anomaly alerts, trailing {options['days']}d:")
        self.stdout.write(f"  created:                  {total}")
        self.stdout.write(f"  viewed (clicked through): {viewed}")
        self.stdout.write(f"  dismissed:                {dismissed_total}")
        self.stdout.write(f"  dismissed WITHOUT view:   {dismissed_unviewed}")

        if dismissed_total == 0:
            self.stdout.write(self.style.SUCCESS("  FP proxy rate: n/a (nothing dismissed yet)"))
            return

        rate = dismissed_unviewed / dismissed_total * 100
        line = f"  FP proxy rate: {rate:.0f}% (guardrail: < 40%)"
        if rate < 40:
            self.stdout.write(self.style.SUCCESS(line))
        else:
            self.stdout.write(self.style.ERROR(line + "  <- GUARDRAIL BREACHED"))