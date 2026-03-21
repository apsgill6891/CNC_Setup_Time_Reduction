"""Simulation routines for machines, jobs, queues, and historical transitions."""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

from config import (
    DEFAULT_NOISE_LEVEL,
    DUE_DATE_PRIORITIES,
    FIXTURE_TYPES,
    HISTORICAL_JOBS,
    HISTORICAL_TRANSITIONS,
    MACHINE_CAPABILITIES,
    MACHINE_TYPE_COMPATIBILITY,
    MATERIALS,
    OPERATION_TYPES,
    PART_FAMILIES,
    QUEUE_MAX_JOBS,
    QUEUE_MIN_JOBS,
    RANDOM_SEED,
    SIZE_CLASSES,
    SIZE_CLASS_ORDER,
    TOLERANCE_CLASSES,
    TOLERANCE_ORDER,
    TOOL_FAMILIES,
)
from models import estimate_transition, is_machine_feasible
from utils import ensure_data_dir


def _rng(seed: Optional[int] = None) -> np.random.Generator:
    return np.random.default_rng(RANDOM_SEED if seed is None else seed)


def generate_machines_df() -> pd.DataFrame:
    """Return the machine master table."""
    return pd.DataFrame(MACHINE_CAPABILITIES)


def _pick_operation_for_machine(machine_type: str, rng: np.random.Generator) -> str:
    valid = [op for op, types in MACHINE_TYPE_COMPATIBILITY.items() if machine_type in types]
    probs = np.array([1.4 if op in {"turning", "milling"} else 1.0 for op in valid], dtype=float)
    probs = probs / probs.sum()
    return str(rng.choice(valid, p=probs))


def _derive_primary_tool(operation_type: str) -> str:
    mapping = {
        "turning": "turning_tools",
        "milling": "end_mills",
        "drilling": "drills",
        "tapping": "taps",
        "boring": "boring_tools",
        "finishing": "boring_tools",
        "multi_op": "multi_axis_tools",
    }
    return mapping[operation_type]


def generate_random_job(job_index: int, machines_df: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    """Generate a realistic random job and ensure it maps to at least one feasible machine."""
    while True:
        operation_type = str(rng.choice(OPERATION_TYPES, p=[0.2, 0.24, 0.11, 0.09, 0.08, 0.1, 0.18]))
        complexity_score = float(np.clip(rng.normal(5.8, 2.0), 1.5, 10.0))
        part_family = str(rng.choice(PART_FAMILIES))
        required_machine_type = str(rng.choice(MACHINE_TYPE_COMPATIBILITY[operation_type]))
        material = str(rng.choice(MATERIALS, p=[0.25, 0.21, 0.22, 0.1, 0.15, 0.07]))
        size_class = str(rng.choice(SIZE_CLASSES, p=[0.38, 0.42, 0.20]))
        tolerance_class = str(rng.choice(TOLERANCE_CLASSES, p=[0.48, 0.38, 0.14]))
        fixture_type = str(rng.choice(FIXTURE_TYPES))
        tool_family_primary = _derive_primary_tool(operation_type)
        secondary_choices = [tool for tool in TOOL_FAMILIES if tool != tool_family_primary]
        tool_family_secondary = str(rng.choice(secondary_choices))
        rush_flag = bool(rng.random() < 0.16)
        batch_size = int(rng.integers(8, 320))
        estimated_run_time_minutes = float(np.clip(rng.normal(135, 65), 30, 480))
        number_of_operations = int(np.clip(round(complexity_score + rng.normal(1.2, 1.0)), 1, 9))
        due_date_priority = str(rng.choice(DUE_DATE_PRIORITIES, p=[0.15, 0.45, 0.28, 0.12]))
        job = pd.Series(
            {
                "job_id": f"JOB_{job_index:04d}",
                "part_id": f"PART_{rng.integers(1000, 9999)}",
                "part_family": part_family,
                "operation_type": operation_type,
                "required_machine_type": required_machine_type,
                "material": material,
                "size_class": size_class,
                "tolerance_class": tolerance_class,
                "number_of_operations": number_of_operations,
                "fixture_type": fixture_type,
                "tool_family_primary": tool_family_primary,
                "tool_family_secondary": tool_family_secondary,
                "tool_count": int(np.clip(rng.normal(10 + complexity_score, 4), 4, 28)),
                "estimated_run_time_minutes": estimated_run_time_minutes,
                "batch_size": batch_size,
                "due_date_priority": due_date_priority,
                "rush_flag": rush_flag,
                "complexity_score": complexity_score,
                "arrival_order": job_index,
            }
        )
        feasible = machines_df.apply(lambda row: is_machine_feasible(job, row), axis=1)
        if feasible.any():
            return job


def generate_jobs_history(machines_df: pd.DataFrame, seed: int = RANDOM_SEED, n_jobs: int = HISTORICAL_JOBS) -> pd.DataFrame:
    """Create a historical jobs table."""
    rng = _rng(seed)
    jobs = [generate_random_job(idx + 1, machines_df, rng) for idx in range(n_jobs)]
    return pd.DataFrame(jobs)


def generate_transitions_history(
    jobs_df: pd.DataFrame,
    machines_df: pd.DataFrame,
    seed: int = RANDOM_SEED,
    n_transitions: int = HISTORICAL_TRANSITIONS,
    noise_level: float = DEFAULT_NOISE_LEVEL,
) -> pd.DataFrame:
    """Create synthetic transition history with realistic setup burden and notes."""
    rng = _rng(seed + 11)
    transitions = []
    for idx in range(n_transitions):
        machine_row = machines_df.sample(1, random_state=int(seed + idx)).iloc[0]
        feasible_jobs = jobs_df[jobs_df.apply(lambda job: is_machine_feasible(job, machine_row), axis=1)]
        if len(feasible_jobs) < 2:
            continue
        pair = feasible_jobs.sample(2, replace=False, random_state=int(seed * 10 + idx))
        prev_job, next_job = pair.iloc[0], pair.iloc[1]
        estimate = estimate_transition(prev_job, next_job, machine_row, noise_level=noise_level, rng=rng)
        same_material = prev_job["material"] == next_job["material"]
        same_fixture = prev_job["fixture_type"] == next_job["fixture_type"]
        same_family = prev_job["part_family"] == next_job["part_family"]
        tooling_overlap_pct = max(0.0, min(1.0, -estimate.details["tooling_overlap_credit"] / 16.0))
        transitions.append(
            {
                "transition_id": f"TRANS_{idx + 1:05d}",
                "previous_job_id": prev_job["job_id"],
                "next_job_id": next_job["job_id"],
                "machine_id": machine_row["machine_id"],
                "same_machine_flag": True,
                "same_material_flag": same_material,
                "same_fixture_flag": same_fixture,
                "same_part_family_flag": same_family,
                "tooling_overlap_pct": tooling_overlap_pct,
                "size_change_score": abs(
                    SIZE_CLASS_ORDER[next_job["size_class"]] - SIZE_CLASS_ORDER[prev_job["size_class"]]
                )
                / 2,
                "tolerance_change_score": abs(
                    TOLERANCE_ORDER[next_job["tolerance_class"]]
                    - TOLERANCE_ORDER[prev_job["tolerance_class"]]
                )
                / 2,
                "operation_change_score": float(prev_job["operation_type"] != next_job["operation_type"]),
                "complexity_change_score": max(0.0, next_job["complexity_score"] - prev_job["complexity_score"]),
                "actual_setup_time_minutes": round(estimate.total_minutes, 2),
                "actual_setup_cost": round(estimate.total_cost, 2),
                "operator_experience_factor": round(float(rng.uniform(0.85, 1.15)), 3),
                "notes": _transition_note(same_material, same_fixture, same_family, tooling_overlap_pct),
            }
        )
    return pd.DataFrame(transitions)


def _transition_note(same_material: bool, same_fixture: bool, same_family: bool, overlap: float) -> str:
    if same_material and same_fixture and overlap > 0.65:
        return "Fast carryover setup with high tool reuse."
    if not same_material and not same_fixture:
        return "Full teardown driven by material and fixture change."
    if not same_family and overlap < 0.35:
        return "Sequence shift across families with low tooling continuity."
    return "Moderate changeover with mixed carryover benefits."


def generate_current_shop_state(machines_df: pd.DataFrame, seed: int = RANDOM_SEED) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generate current active and queued jobs for each machine."""
    rng = _rng(seed + 101)
    queue_records = []
    active_records = []
    job_counter = 5000
    for _, machine_row in machines_df.iterrows():
        queue_size = int(rng.integers(QUEUE_MIN_JOBS, QUEUE_MAX_JOBS + 1))
        machine_jobs = []
        while len(machine_jobs) < queue_size:
            candidate = generate_random_job(job_counter, machines_df, rng)
            job_counter += 1
            if is_machine_feasible(candidate, machine_row):
                candidate["machine_id"] = machine_row["machine_id"]
                machine_jobs.append(candidate)
        active_records.append(machine_jobs[0])
        queue_records.extend(machine_jobs)
    active_df = pd.DataFrame(active_records)
    queue_df = pd.DataFrame(queue_records)
    queue_df["queue_position"] = queue_df.groupby("machine_id").cumcount()
    return active_df, queue_df


def generate_incoming_job(machines_df: pd.DataFrame, seed: int = RANDOM_SEED) -> pd.Series:
    """Generate one new incoming job."""
    rng = _rng(seed + 202)
    return generate_random_job(9001, machines_df, rng)


def generate_incoming_jobs(machines_df: pd.DataFrame, count: int = 3, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Generate a small batch of new incoming requisitions."""
    rng = _rng(seed + 202)
    jobs = [generate_random_job(9001 + idx, machines_df, rng) for idx in range(count)]
    return pd.DataFrame(jobs)


def ensure_sample_history(seed: int = RANDOM_SEED) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load historical sample data if present, otherwise generate and persist it."""
    data_dir = ensure_data_dir()
    jobs_path = data_dir / "jobs_history.csv"
    transitions_path = data_dir / "transitions_history.csv"
    machines_df = generate_machines_df()

    if jobs_path.exists() and transitions_path.exists():
        return pd.read_csv(jobs_path), pd.read_csv(transitions_path)

    jobs_df = generate_jobs_history(machines_df, seed=seed)
    transitions_df = generate_transitions_history(jobs_df, machines_df, seed=seed)
    jobs_df.to_csv(jobs_path, index=False)
    transitions_df.to_csv(transitions_path, index=False)
    return jobs_df, transitions_df
