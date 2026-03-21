"""Utility helpers for formatting, caching, and chart preparation."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "sample_data"


def ensure_data_dir() -> Path:
    """Create the sample data directory if it does not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def format_minutes(value: float) -> str:
    """Format minutes with one decimal place."""
    return f"{value:,.1f} min"


def format_currency(value: float) -> str:
    """Format a numeric value as USD."""
    return f"${value:,.0f}"


def safe_round(value: Optional[float], digits: int = 1) -> float:
    """Round a float while guarding against None values."""
    return round(float(value or 0.0), digits)


def queue_to_display_rows(queue_df: pd.DataFrame, machine_name_lookup: dict[str, str]) -> pd.DataFrame:
    """Create a user-friendly queue table for display."""
    if queue_df.empty:
        return pd.DataFrame()

    display_df = queue_df.copy()
    display_df["machine_name"] = display_df["machine_id"].map(machine_name_lookup)
    display_df["queue_position"] = display_df.groupby("machine_id").cumcount()
    cols = [
        "machine_name",
        "queue_position",
        "job_id",
        "part_family",
        "operation_type",
        "material",
        "fixture_type",
        "tool_family_primary",
        "estimated_run_time_minutes",
        "batch_size",
        "due_date_priority",
    ]
    return display_df[cols]


def build_before_after_queue(
    queue_df: pd.DataFrame,
    selected_machine: str,
    insertion_index: int,
    new_job: pd.Series,
) -> pd.DataFrame:
    """Return a single machine queue with an inserted job for before/after display."""
    machine_queue = queue_df[queue_df["machine_id"] == selected_machine].copy().reset_index(drop=True)
    before = machine_queue.copy()
    before["scenario"] = "Before"

    after = pd.concat(
        [machine_queue.iloc[:insertion_index], pd.DataFrame([new_job]), machine_queue.iloc[insertion_index:]],
        ignore_index=True,
    )
    after["scenario"] = "After"
    after["queue_position"] = after.index
    before["queue_position"] = before.index
    return pd.concat([before, after], ignore_index=True)


def summarize_transition_drivers(transition_row: pd.Series) -> str:
    """Create a short text summary of key transition drivers."""
    drivers: list[str] = []
    if not bool(transition_row.get("same_material_flag", True)):
        drivers.append("material change")
    if not bool(transition_row.get("same_fixture_flag", True)):
        drivers.append("fixture change")
    if not bool(transition_row.get("same_part_family_flag", True)):
        drivers.append("part family change")
    if transition_row.get("tooling_overlap_pct", 1.0) < 0.35:
        drivers.append("low tooling overlap")
    if transition_row.get("tolerance_change_score", 0.0) > 0.5:
        drivers.append("tighter tolerance demand")
    if transition_row.get("size_change_score", 0.0) > 0.5:
        drivers.append("size shift")
    return ", ".join(drivers) if drivers else "stable carryover setup"


def annualize_savings(cost_savings: float, annual_setup_volume: int) -> float:
    """Annualize savings from a single setup event using an assumed annual setup count."""
    return cost_savings * annual_setup_volume


def normalize_series(series: Iterable[float]) -> pd.Series:
    """Normalize numeric values into a 0-1 range for display proxies."""
    s = pd.Series(list(series), dtype=float)
    if s.empty or s.max() == s.min():
        return pd.Series([0.0] * len(s))
    return (s - s.min()) / (s.max() - s.min())
