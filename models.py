"""Transparent setup-time scoring model and feasibility rules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd

from config import (
    BASE_SETUP_MINUTES,
    DEFAULT_WEIGHTS,
    MACHINE_TYPE_COMPATIBILITY,
    MATERIAL_CHANGE_PENALTY,
    PRIORITY_ORDER,
    SIZE_CLASS_ORDER,
    TOLERANCE_ORDER,
)


@dataclass
class TransitionEstimate:
    """Detailed setup estimate for a transition between two jobs."""

    total_minutes: float
    total_cost: float
    details: Dict[str, float]


def tooling_overlap(previous_job: pd.Series, next_job: pd.Series) -> float:
    """Estimate tooling overlap from primary/secondary tool families and count similarity."""
    score = 0.0
    if previous_job["tool_family_primary"] == next_job["tool_family_primary"]:
        score += 0.5
    if previous_job["tool_family_secondary"] == next_job["tool_family_secondary"]:
        score += 0.25
    if previous_job["tool_family_primary"] == next_job["tool_family_secondary"]:
        score += 0.1
    if previous_job["tool_family_secondary"] == next_job["tool_family_primary"]:
        score += 0.1
    count_gap = abs(previous_job["tool_count"] - next_job["tool_count"])
    score += max(0.0, 0.15 - count_gap * 0.01)
    return float(np.clip(score, 0.0, 1.0))


def get_material_penalty(previous_material: str, next_material: str) -> float:
    """Return a symmetric material-change penalty."""
    if previous_material == next_material:
        return 0.0
    if (previous_material, next_material) in MATERIAL_CHANGE_PENALTY:
        return float(MATERIAL_CHANGE_PENALTY[(previous_material, next_material)])
    if (next_material, previous_material) in MATERIAL_CHANGE_PENALTY:
        return float(MATERIAL_CHANGE_PENALTY[(next_material, previous_material)])
    return 12.0


def estimate_transition(
    previous_job: Optional[pd.Series],
    next_job: Optional[pd.Series],
    machine_row: pd.Series,
    weights: Optional[Dict[str, float]] = None,
    noise_level: float = 0.0,
    rng: Optional[np.random.Generator] = None,
) -> TransitionEstimate:
    """Estimate setup burden for two adjacent jobs on a machine."""
    if previous_job is None or next_job is None:
        return TransitionEstimate(total_minutes=0.0, total_cost=0.0, details={"base": 0.0})

    weights = weights or DEFAULT_WEIGHTS
    rng = rng or np.random.default_rng(0)
    machine_type = machine_row["machine_type"]
    base = float(BASE_SETUP_MINUTES[machine_type])
    overlap = tooling_overlap(previous_job, next_job)

    size_delta = abs(SIZE_CLASS_ORDER[next_job["size_class"]] - SIZE_CLASS_ORDER[previous_job["size_class"]])
    tolerance_delta = max(0, TOLERANCE_ORDER[next_job["tolerance_class"]] - TOLERANCE_ORDER[previous_job["tolerance_class"]])
    operation_delta = float(previous_job["operation_type"] != next_job["operation_type"])
    fixture_delta = float(previous_job["fixture_type"] != next_job["fixture_type"])
    family_delta = float(previous_job["part_family"] != next_job["part_family"])
    rush_delta = float(bool(next_job["rush_flag"]))
    tool_delta = float(previous_job["tool_family_primary"] != next_job["tool_family_primary"])
    complexity_delta = max(0.0, float(next_job["complexity_score"] - previous_job["complexity_score"]))
    material_penalty = get_material_penalty(previous_job["material"], next_job["material"])
    same_family = float(previous_job["part_family"] == next_job["part_family"])
    same_fixture = float(previous_job["fixture_type"] == next_job["fixture_type"])

    details = {
        "base": base,
        "material_change": material_penalty * weights["material_change"] / 10.0,
        "fixture_change": fixture_delta * weights["fixture_change"],
        "part_family_change": family_delta * weights["part_family_change"],
        "tool_mismatch": tool_delta * weights["tool_mismatch"],
        "tolerance_increase": tolerance_delta * weights["tolerance_increase"],
        "operation_change": operation_delta * weights["operation_change"],
        "complexity_change": complexity_delta * weights["complexity_change"],
        "size_change": size_delta * weights["size_change"],
        "rush_penalty": rush_delta * weights["rush_penalty"],
        "tooling_overlap_credit": -overlap * weights["tooling_overlap_credit"],
        "same_family_credit": -same_family * weights["same_family_credit"],
        "same_fixture_credit": -same_fixture * weights["same_fixture_credit"],
    }
    total = sum(details.values())

    if noise_level > 0:
        total += rng.normal(0, base * noise_level)
        if rng.random() < 0.06:
            total += rng.uniform(12, 35)

    total = max(8.0, total)
    hourly_rate = float(machine_row["setup_hourly_rate"])
    total_cost = total / 60.0 * hourly_rate
    return TransitionEstimate(total_minutes=total, total_cost=total_cost, details=details)


def is_machine_feasible(job: pd.Series, machine_row: pd.Series) -> bool:
    """Check whether a machine can process the job."""
    if machine_row["machine_type"] not in MACHINE_TYPE_COMPATIBILITY[job["operation_type"]]:
        return False
    if job["material"] not in machine_row["supported_materials"]:
        return False
    if job["size_class"] not in machine_row["supported_size_classes"]:
        return False
    if job["tolerance_class"] == "ultra_tight" and machine_row["machine_type"] == "secondary":
        return False
    if job["complexity_score"] >= 8.5 and machine_row["machine_type"] not in {"5_axis", "mill_turn"}:
        return False
    return True


def utilization_proxy(queue_df: pd.DataFrame, machines_df: pd.DataFrame) -> pd.DataFrame:
    """Estimate queue loading as a utilization proxy for visualization."""
    queue_load = (
        queue_df.groupby("machine_id")["estimated_run_time_minutes"].sum().rename("queued_runtime_minutes").reset_index()
    )
    merged = machines_df.merge(queue_load, on="machine_id", how="left").fillna({"queued_runtime_minutes": 0})
    max_runtime = max(float(merged["queued_runtime_minutes"].max()), 1.0)
    merged["utilization_proxy"] = merged["queued_runtime_minutes"] / max_runtime
    merged["target_gap"] = merged["utilization_target"] - merged["utilization_proxy"]
    return merged.sort_values("utilization_proxy", ascending=False)


def due_priority_score(priority: str) -> int:
    """Translate due date priority to an ordinal score."""
    return PRIORITY_ORDER.get(priority, 1)
