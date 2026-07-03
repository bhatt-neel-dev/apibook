"""Synthetic telemetry generation for APILens demo, QA, and load data."""

from .accelerators import RandomPlanner
from .catalog import SCENARIOS, expand_scenario_keys, get_scenario, list_scenarios
from .generator import (
    AppTarget,
    GenerationResult,
    SyntheticTelemetryEngine,
    SyntheticRunConfig,
)
from .writers import DirectClickHouseWriter, HttpIngestWriter, JsonlWriter

__all__ = [
    "AppTarget",
    "DirectClickHouseWriter",
    "GenerationResult",
    "HttpIngestWriter",
    "JsonlWriter",
    "RandomPlanner",
    "SCENARIOS",
    "SyntheticRunConfig",
    "SyntheticTelemetryEngine",
    "expand_scenario_keys",
    "get_scenario",
    "list_scenarios",
]
