from __future__ import annotations

from collections.abc import Iterable


def normalize_selected_scenarios(keys: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(k.strip().lower() for k in (keys or ()) if k and k.strip())


def validate_selected_scenarios(keys: Iterable[str] | None) -> tuple[str, ...]:
    normalized = normalize_selected_scenarios(keys)
    if not normalized:
        raise ValueError("At least one synthetic scenario must be selected")
    return normalized


def validate_count_and_days(
    *,
    count: int,
    days: int,
    max_count: int | None = None,
    max_days: int | None = None,
) -> tuple[int, int]:
    if count < 1:
        raise ValueError("count must be at least 1")
    if max_count is not None and count > max_count:
        raise ValueError(f"count must be at most {max_count}")
    if days < 1:
        raise ValueError("days must be at least 1")
    if max_days is not None and days > max_days:
        raise ValueError(f"days must be at most {max_days}")
    return count, days
