from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils.text import slugify

from apps.projects.models import App, Environment, Project

from .catalog import ScenarioProfile, expand_scenario_keys, get_scenario, list_scenarios
from .generator import AppTarget, SyntheticRunConfig, SyntheticTelemetryEngine
from .writers import DirectClickHouseWriter, WriteSummary

MAX_UI_INGEST_COUNT = 50_000


@dataclass(frozen=True)
class SyntheticDirectRun:
    generation: dict[str, Any]
    write: WriteSummary

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.generation,
            "mode": self.write.mode,
            "written_requests": self.write.requests,
            "written_logs": self.write.logs,
            "written_spans": self.write.spans,
        }


def scenario_options() -> list[dict[str, Any]]:
    return [_scenario_dict(scenario) for scenario in list_scenarios()]


def run_project_direct_ingest(
    *,
    project: Project,
    scenario_keys: list[str] | tuple[str, ...],
    count: int,
    days: int,
    seed: int | None = None,
    accelerator: str = "auto",
    include_logs: bool = True,
    include_spans: bool = True,
    ensure_apps: bool = True,
    app_slugs: list[str] | tuple[str, ...] | None = None,
) -> SyntheticDirectRun:
    safe_count = max(1, min(int(count), MAX_UI_INGEST_COUNT))
    safe_days = max(1, min(int(days), 365))
    keys = expand_scenario_keys(scenario_keys)

    if ensure_apps:
        ensure_project_scenario_apps(project, keys)

    targets = app_targets_for_project(project, keys, app_slugs=app_slugs)
    if not targets:
        raise ValueError("No active target apps found for the selected scenarios")

    config = SyntheticRunConfig(
        scenario_keys=keys,
        count=safe_count,
        days=safe_days,
        seed=seed,
        accelerator=accelerator,  # type: ignore[arg-type]
        include_logs=include_logs,
        include_spans=include_spans,
        project_slug=project.slug,
        app_targets=targets,
    )
    result = SyntheticTelemetryEngine(config).generate()
    write = DirectClickHouseWriter().write(result)
    return SyntheticDirectRun(generation=result.summary(), write=write)


@transaction.atomic
def ensure_project_scenario_apps(project: Project, scenario_keys: tuple[str, ...]) -> None:
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
            updates: list[str] = []
            for field, value in (
                ("name", profile.name),
                ("description", profile.description),
                ("framework", profile.framework),
                ("icon", profile.icon[:8]),
            ):
                if getattr(app, field) != value:
                    setattr(app, field, value)
                    updates.append(field)
            if not app.is_active:
                app.is_active = True
                updates.append("is_active")
            if updates:
                app.save(update_fields=updates + ["updated_at"])
            _ensure_environments(app, scenario)


def app_targets_for_project(
    project: Project,
    scenario_keys: tuple[str, ...],
    *,
    app_slugs: list[str] | tuple[str, ...] | None = None,
) -> tuple[AppTarget, ...]:
    profile_by_slug = {
        profile.slug: profile
        for key in scenario_keys
        for profile in get_scenario(key).apps
    }
    requested = [slug.strip() for slug in (app_slugs or []) if slug and slug.strip()]
    slugs = requested or list(profile_by_slug)
    apps = App.objects.filter(project=project, slug__in=slugs, is_active=True).order_by("slug")
    targets: list[AppTarget] = []
    for app in apps:
        profile = profile_by_slug.get(app.slug)
        targets.append(
            AppTarget(
                slug=app.slug,
                name=app.name,
                app_id=str(app.id),
                project_id=str(project.id),
                project_slug=project.slug,
                framework=app.framework,
                base_urls=profile.base_urls if profile else (),
            )
        )
    return tuple(targets)


def _ensure_environments(app: App, scenario: ScenarioProfile) -> None:
    colors = {
        "production": "#16a34a",
        "staging": "#2563eb",
        "development": "#9333ea",
    }
    for order, env in enumerate(scenario.environments):
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


def _scenario_dict(scenario: ScenarioProfile) -> dict[str, Any]:
    return {
        "key": scenario.key,
        "name": scenario.name,
        "industry": scenario.industry,
        "description": scenario.description,
        "product_signal": scenario.product_signal,
        "apps": len(scenario.apps),
        "endpoints": len(scenario.endpoints),
        "consumers": len(scenario.consumers),
    }
