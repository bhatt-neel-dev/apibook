"""Run the endpoint anomaly-detection job (see apps.projects.anomaly).

One-shot by default so any scheduler (cron, supervisor, an mprocs tab) can own
the cadence; --loop turns it into a self-scheduling worker for the single-VM
docker-compose deployment where nothing else plays cron. Every cycle logs a
heartbeat line — G3 approval for this feature required that its silent death be
detectable, so keep that line intact.
"""

import time

from django.core.management.base import BaseCommand

from apps.projects.anomaly import WINDOW_MINUTES, anomaly_alerts_enabled, run_detection_cycle


class Command(BaseCommand):
    help = "Detect endpoint anomalies (error rate / p95 latency vs rolling baseline)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            type=int,
            nargs="?",
            const=WINDOW_MINUTES * 60,
            default=None,
            metavar="SECONDS",
            help=f"Run continuously, sleeping SECONDS between cycles (default {WINDOW_MINUTES * 60})",
        )

    def handle(self, *args, **options):
        if not anomaly_alerts_enabled():
            self.stdout.write(
                self.style.WARNING(
                    "Anomaly alerts are disabled via APILENS_ANOMALY_ALERTS; nothing to do."
                )
            )
            return

        interval = options["loop"]
        while True:
            started = time.monotonic()
            scanned, created = run_detection_cycle()
            elapsed = time.monotonic() - started
            # Heartbeat — external monitoring watches for this line going quiet.
            self.stdout.write(
                self.style.SUCCESS(
                    f"anomaly-detection heartbeat: {scanned} project(s) scanned, "
                    f"{created} alert(s) created in {elapsed:.1f}s"
                )
            )
            if interval is None:
                return
            time.sleep(max(interval - elapsed, 1.0))
