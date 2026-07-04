from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.projects.models import App, Environment, Project
from apps.projects.synthetic.catalog import expand_scenario_keys, get_scenario, list_scenarios
from apps.projects.synthetic.generator import AppTarget, SyntheticRunConfig, SyntheticTelemetryEngine
from apps.projects.synthetic.validation import validate_count_and_days
from apps.projects.synthetic.writers import DirectClickHouseWriter, HttpIngestWriter, JsonlWriter


class Command(BaseCommand):
    help = "Generate rich synthetic APILens request, log, and trace telemetry for demos, QA, and load data."

    def add_arguments(self, parser):
        parser.add_argument("--list-scenarios", action="store_true", help="Print available scenario keys and exit")
        parser.add_argument(
            "--scenario",
            action="append",
            default=[],
            help="Scenario key to generate. Repeat or pass comma-separated values. Defaults to all.",
        )
        parser.add_argument("--project-slug", default="", help="Target project slug for direct/http modes")
        parser.add_argument("--owner-email", default="", help="Owner email used with --ensure-demo-project")
        parser.add_argument(
            "--ensure-demo-project",
            action="store_true",
            help="Create/update a synthetic project, apps, and environments before generation.",
        )
        parser.add_argument("--app-slugs", default="", help="Comma-separated real app slugs to target")
        parser.add_argument("--count", type=int, default=5000, help="Number of request events to generate")
        parser.add_argument("--days", type=int, default=14, help="Past time window to cover")
        parser.add_argument("--seed", type=int, default=None, help="Fixed seed for repeatable output. Omit for hourly rotation.")
        parser.add_argument(
            "--accelerator",
            choices=("auto", "cpu", "gpu"),
            default="auto",
            help="Random planner accelerator. auto uses CUDA through CuPy/Torch when available, otherwise CPU.",
        )
        parser.add_argument(
            "--mode",
            choices=("jsonl", "http", "direct"),
            default="jsonl",
            help="Output mode. jsonl is safe; http posts to ingest; direct writes local ClickHouse.",
        )
        parser.add_argument("--output-dir", default="", help="JSONL output directory")
        parser.add_argument("--ingest-url", default="", help="Base ingest URL for --mode http, e.g. http://127.0.0.1:8001")
        parser.add_argument("--api-key", default="", help="Project API key for --mode http")
        parser.add_argument("--batch-size", type=int, default=1000, help="Write batch size, capped at 1000")
        parser.add_argument("--no-logs", action="store_true", help="Do not generate correlated log events")
        parser.add_argument("--no-spans", action="store_true", help="Do not generate correlated trace spans")
        parser.add_argument("--dry-run", action="store_true", help="Generate and summarize without writing")

    def handle(self, *args, **options):
        if options["list_scenarios"]:
            self._print_scenarios()
            return

        scenario_keys = self._scenario_keys(options["scenario"])
        mode = options["mode"]
        project = None
        project_slug = (options["project_slug"] or "").strip()

        if options["ensure_demo_project"]:
            project = self._ensure_demo_project(
                project_slug=project_slug or "synthetic-apilens-demo",
                owner_email=(options["owner_email"] or "").strip(),
                scenario_keys=scenario_keys,
            )
            project_slug = project.slug
        elif project_slug:
            try:
                project = Project.objects.get(slug=project_slug, is_active=True)
            except Project.DoesNotExist as exc:
                raise CommandError(f"Active project '{project_slug}' was not found") from exc

        if mode in {"http", "direct"} and project is None:
            raise CommandError("--project-slug or --ensure-demo-project is required for http/direct modes")
        if mode == "http" and (not options["ingest_url"] or not options["api_key"]):
            raise CommandError("--ingest-url and --api-key are required for --mode http")

        try:
            count, days = validate_count_and_days(
                count=int(options["count"]),
                days=int(options["days"]),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        app_targets = self._resolve_app_targets(
            project=project,
            app_slugs=(options["app_slugs"] or "").strip(),
            scenario_keys=scenario_keys,
        )
        if mode in {"http", "direct"} and not app_targets:
            raise CommandError("No target apps found. Pass --app-slugs or use --ensure-demo-project.")

        config = SyntheticRunConfig(
            scenario_keys=scenario_keys,
            count=count,
            days=days,
            seed=options["seed"],
            accelerator=options["accelerator"],
            include_logs=not options["no_logs"],
            include_spans=not options["no_spans"],
            project_slug=project_slug,
            app_targets=app_targets,
        )
        result = SyntheticTelemetryEngine(config).generate()
        self._print_generation_summary(result.summary())

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run complete. No data was written."))
            return

        if mode == "jsonl":
            output_dir = options["output_dir"] or self._default_output_dir()
            summary = JsonlWriter(output_dir).write(result)
        elif mode == "http":
            summary = HttpIngestWriter(
                options["ingest_url"],
                options["api_key"],
                batch_size=options["batch_size"],
            ).write(result)
        else:
            summary = DirectClickHouseWriter(batch_size=options["batch_size"]).write(result)

        self.stdout.write(
            self.style.SUCCESS(
                "Synthetic telemetry written: "
                f"mode={summary.mode}, requests={summary.requests}, logs={summary.logs}, spans={summary.spans}"
            )
        )
        if summary.output_dir:
            self.stdout.write(f"Output directory: {summary.output_dir}")
        if summary.details:
            for key, value in summary.details.items():
                self.stdout.write(f"{key}: {value}")

    def _print_scenarios(self) -> None:
        self.stdout.write("Available synthetic telemetry scenarios:")
        for scenario in list_scenarios():
            self.stdout.write(
                f"- {scenario.key}: {scenario.name} [{scenario.industry}] "
                f"apps={len(scenario.apps)} endpoints={len(scenario.endpoints)} consumers={len(scenario.consumers)}"
            )

    def _scenario_keys(self, values: list[str]) -> tuple[str, ...]:
        tokens: list[str] = []
        for raw in values:
            tokens.extend(part.strip() for part in raw.split(",") if part.strip())
        try:
            return expand_scenario_keys(tokens or ("all",))
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

    def _ensure_demo_project(self, *, project_slug: str, owner_email: str, scenario_keys: tuple[str, ...]) -> Project:
        if not owner_email:
            raise CommandError("--owner-email is required with --ensure-demo-project")
        User = get_user_model()
        user, _created = User.objects.get_or_create(
            email=owner_email.lower(),
            defaults={
                "email_verified": True,
                "auth_provider": "synthetic",
                "is_active": True,
            },
        )
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified", "updated_at"])

        slug = slugify(project_slug) or "synthetic-apilens-demo"
        project, _created = Project.objects.get_or_create(
            slug=slug,
            defaults={
                "owner": user,
                "name": "Synthetic APILens Demo",
                "description": "Synthetic telemetry project for APILens demos, QA, and regression data.",
            },
        )
        if not project.is_active:
            project.is_active = True
            project.save(update_fields=["is_active", "updated_at"])

        for scenario_key in scenario_keys:
            scenario = get_scenario(scenario_key)
            for profile in scenario.apps:
                app, _created = App.objects.get_or_create(
                    project=project,
                    slug=profile.slug,
                    defaults={
                        "name": profile.name,
                        "description": profile.description,
                        "framework": profile.framework,
                        "icon": profile.icon[:8],
                    },
                )
                updates = []
                if app.name != profile.name:
                    app.name = profile.name
                    updates.append("name")
                if app.description != profile.description:
                    app.description = profile.description
                    updates.append("description")
                if app.framework != profile.framework:
                    app.framework = profile.framework
                    updates.append("framework")
                if app.icon != profile.icon[:8]:
                    app.icon = profile.icon[:8]
                    updates.append("icon")
                if not app.is_active:
                    app.is_active = True
                    updates.append("is_active")
                if updates:
                    app.save(update_fields=updates + ["updated_at"])
                self._ensure_environments(app, scenario.environments)

        self.stdout.write(self.style.SUCCESS(f"Demo project ready: {project.slug}"))
        return project

    def _ensure_environments(self, app: App, environments) -> None:
        colors = {
            "production": "#16a34a",
            "staging": "#2563eb",
            "development": "#9333ea",
        }
        for order, env in enumerate(environments):
            slug = slugify(env.value)
            Environment.objects.get_or_create(
                app=app,
                slug=slug,
                defaults={
                    "name": env.value.title(),
                    "color": colors.get(slug, "#6b7280"),
                    "order": order,
                },
            )

    def _resolve_app_targets(self, *, project: Project | None, app_slugs: str, scenario_keys: tuple[str, ...]) -> tuple[AppTarget, ...]:
        if project is None:
            return ()
        requested = [slug.strip() for slug in app_slugs.split(",") if slug.strip()]
        queryset = App.objects.filter(project=project, is_active=True)
        if requested:
            queryset = queryset.filter(slug__in=requested)
        else:
            scenario_app_slugs = {profile.slug for key in scenario_keys for profile in get_scenario(key).apps}
            queryset = queryset.filter(slug__in=scenario_app_slugs)
        apps = list(queryset.order_by("slug"))
        found = {app.slug for app in apps}
        missing = sorted(set(requested) - found)
        if missing:
            raise CommandError(f"Target app slug(s) not found in project '{project.slug}': {', '.join(missing)}")
        return tuple(
            AppTarget(
                slug=app.slug,
                name=app.name,
                app_id=str(app.id),
                project_id=str(project.id),
                project_slug=project.slug,
                framework=app.framework,
            )
            for app in apps
        )

    def _default_output_dir(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return str(Path("synthetic-output") / stamp)

    def _print_generation_summary(self, summary: dict) -> None:
        self.stdout.write(
            "Generated synthetic telemetry: "
            f"requests={summary['requests']}, logs={summary['logs']}, spans={summary['spans']}, "
            f"scenarios={','.join(summary['scenarios'])}, accelerator={summary['accelerator_backend']}, "
            f"used_gpu={summary['used_gpu']}, seed={summary['seed']}"
        )
