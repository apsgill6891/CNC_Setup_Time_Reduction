"""Insertion optimizer and scenario comparison logic."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd

from models import estimate_transition, is_machine_feasible, tooling_overlap, utilization_proxy
from utils import annualize_savings, summarize_transition_drivers


def evaluate_candidate_insertions(
    machines_df: pd.DataFrame,
    queue_df: pd.DataFrame,
    new_job: pd.Series,
    weights: Dict[str, float],
    annual_setup_volume: int,
    noise_level: float = 0.0,
) -> pd.DataFrame:
    """Evaluate every feasible machine and insertion point for the new job."""
    candidates: List[Dict[str, object]] = []
    for _, machine_row in machines_df.iterrows():
        if not is_machine_feasible(new_job, machine_row):
            continue
        machine_queue = queue_df[queue_df["machine_id"] == machine_row["machine_id"]].reset_index(drop=True)
        for insert_at in range(len(machine_queue) + 1):
            previous_job = machine_queue.iloc[insert_at - 1] if insert_at > 0 else None
            next_job = machine_queue.iloc[insert_at] if insert_at < len(machine_queue) else None
            original = estimate_transition(previous_job, next_job, machine_row, weights=weights, noise_level=noise_level)
            prev_to_new = estimate_transition(previous_job, new_job, machine_row, weights=weights, noise_level=noise_level)
            new_to_next = estimate_transition(new_job, next_job, machine_row, weights=weights, noise_level=noise_level)
            immediate_impact = prev_to_new.total_minutes
            downstream_impact = new_to_next.total_minutes - original.total_minutes
            incremental_minutes = prev_to_new.total_minutes + new_to_next.total_minutes - original.total_minutes
            incremental_cost = prev_to_new.total_cost + new_to_next.total_cost - original.total_cost
            local_similarity = tooling_overlap(previous_job, new_job) if previous_job is not None else 0.0
            candidates.append(
                {
                    "machine_id": machine_row["machine_id"],
                    "machine_name": machine_row["machine_name"],
                    "machine_type": machine_row["machine_type"],
                    "insert_at": insert_at,
                    "queue_length": len(machine_queue),
                    "previous_job_id": previous_job["job_id"] if previous_job is not None else "START",
                    "next_job_id": next_job["job_id"] if next_job is not None else "END",
                    "original_transition_minutes": original.total_minutes,
                    "prev_to_new_minutes": prev_to_new.total_minutes,
                    "new_to_next_minutes": new_to_next.total_minutes,
                    "immediate_setup_impact_minutes": immediate_impact,
                    "downstream_setup_impact_minutes": downstream_impact,
                    "net_incremental_setup_minutes": incremental_minutes,
                    "net_incremental_setup_cost": incremental_cost,
                    "annualized_cost_impact": annualize_savings(incremental_cost, annual_setup_volume),
                    "local_similarity_score": local_similarity,
                    "original_transition_note": summarize_transition_drivers(
                        pd.Series(
                            {
                                "same_material_flag": previous_job is not None and next_job is not None and previous_job["material"] == next_job["material"],
                                "same_fixture_flag": previous_job is not None and next_job is not None and previous_job["fixture_type"] == next_job["fixture_type"],
                                "same_part_family_flag": previous_job is not None and next_job is not None and previous_job["part_family"] == next_job["part_family"],
                                "tooling_overlap_pct": tooling_overlap(previous_job, next_job) if previous_job is not None and next_job is not None else 0.0,
                                "tolerance_change_score": 0.0,
                                "size_change_score": 0.0,
                            }
                        )
                    ),
                }
            )
    candidate_df = pd.DataFrame(candidates)
    if candidate_df.empty:
        return candidate_df
    return candidate_df.sort_values("net_incremental_setup_minutes", ascending=True).reset_index(drop=True)


def select_manual_decision(candidate_df: pd.DataFrame) -> pd.Series:
    """Manual heuristic: first feasible machine, append to end of queue."""
    ordered = candidate_df.sort_values(["machine_id", "insert_at"]).copy()
    manual = ordered.groupby("machine_id").tail(1).sort_values("machine_id").iloc[0]
    return manual


def select_wrong_obvious_decision(candidate_df: pd.DataFrame) -> pd.Series:
    """Obvious-but-wrong heuristic: maximize local similarity only."""
    wrong = candidate_df.sort_values(
        ["local_similarity_score", "prev_to_new_minutes"], ascending=[False, True]
    ).iloc[0]
    return wrong


def compare_scenarios(candidate_df: pd.DataFrame, annual_setup_volume: int) -> pd.DataFrame:
    """Compare optimized, manual, and obvious-but-wrong scenarios."""
    best = candidate_df.iloc[0]
    manual = select_manual_decision(candidate_df)
    wrong = select_wrong_obvious_decision(candidate_df)

    rows = []
    for label, row in [("Optimized", best), ("Manual default", manual), ("Obvious but wrong", wrong)]:
        rows.append(
            {
                "scenario": label,
                "machine_name": row["machine_name"],
                "insert_at": int(row["insert_at"]),
                "setup_minutes": row["net_incremental_setup_minutes"],
                "setup_cost": row["net_incremental_setup_cost"],
                "annualized_cost": row["net_incremental_setup_cost"] * annual_setup_volume,
                "downstream_effect": row["downstream_setup_impact_minutes"],
                "first_order_effect": row["immediate_setup_impact_minutes"],
            }
        )
    comparison = pd.DataFrame(rows)
    best_minutes = float(best["net_incremental_setup_minutes"])
    best_cost = float(best["net_incremental_setup_cost"])
    comparison["minutes_vs_optimized"] = comparison["setup_minutes"] - best_minutes
    comparison["cost_vs_optimized"] = comparison["setup_cost"] - best_cost
    return comparison


def explain_recommendation(best: pd.Series, manual: pd.Series, wrong: pd.Series) -> str:
    """Generate plain-English explanation for executive audiences."""
    manual_gap = manual["net_incremental_setup_minutes"] - best["net_incremental_setup_minutes"]
    wrong_gap = wrong["net_incremental_setup_minutes"] - best["net_incremental_setup_minutes"]
    explanation = (
        f"This recommendation places the new job on {best['machine_name']} at queue position {int(best['insert_at'])}. "
        f"It reduces setup burden by {manual_gap:.1f} minutes versus the planner's likely default choice and by "
        f"{wrong_gap:.1f} minutes versus the seemingly obvious option. "
        f"The optimizer favors the position because it limits the downstream penalty after the insertion, rather than "
        f"chasing only the most similar current job."
    )
    if best["downstream_setup_impact_minutes"] < manual["downstream_setup_impact_minutes"]:
        explanation += (
            " In business terms, it preserves a better transition later in the queue and avoids a more disruptive "
            "fixture, material, or tooling reset."
        )
    return explanation


def queue_burden_summary(queue_df: pd.DataFrame, machines_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize queue burden and utilization proxy by machine."""
    return utilization_proxy(queue_df, machines_df)


def apply_insertion(queue_df: pd.DataFrame, machine_id: str, insert_at: int, new_job: pd.Series) -> pd.DataFrame:
    """Return a new queue with the selected job inserted on the selected machine."""
    queue_copy = queue_df.copy()
    machine_queue = queue_copy[queue_copy["machine_id"] == machine_id].copy().reset_index(drop=True)
    inserted = pd.concat([machine_queue.iloc[:insert_at], pd.DataFrame([new_job]), machine_queue.iloc[insert_at:]], ignore_index=True)
    inserted["machine_id"] = machine_id
    other = queue_copy[queue_copy["machine_id"] != machine_id].copy()
    combined = pd.concat([other, inserted], ignore_index=True)
    combined["queue_position"] = combined.groupby("machine_id").cumcount()
    return combined


def simulate_requisition_batch(
    machines_df: pd.DataFrame,
    base_queue_df: pd.DataFrame,
    requisitions_df: pd.DataFrame,
    weights: Dict[str, float],
    annual_setup_volume: int,
) -> pd.DataFrame:
    """Simulate cumulative setup burden for a batch of requisitions under different strategies."""
    summaries = []
    for strategy in ["optimized", "manual", "obvious"]:
        queue_df = base_queue_df.copy()
        total_minutes = 0.0
        total_cost = 0.0
        feasible_count = 0
        for _, req in requisitions_df.iterrows():
            candidates = evaluate_candidate_insertions(
                machines_df=machines_df,
                queue_df=queue_df,
                new_job=req,
                weights=weights,
                annual_setup_volume=annual_setup_volume,
            )
            if candidates.empty:
                continue
            feasible_count += 1
            if strategy == "optimized":
                choice = candidates.iloc[0]
                label = "Optimized batch"
            elif strategy == "manual":
                choice = select_manual_decision(candidates)
                label = "Manual batch"
            else:
                choice = select_wrong_obvious_decision(candidates)
                label = "Obvious-choice batch"
            total_minutes += float(choice["net_incremental_setup_minutes"])
            total_cost += float(choice["net_incremental_setup_cost"])
            queue_df = apply_insertion(queue_df, str(choice["machine_id"]), int(choice["insert_at"]), req)
        summaries.append(
            {
                "strategy": label,
                "requisitions_scheduled": feasible_count,
                "total_setup_minutes": total_minutes,
                "total_setup_cost": total_cost,
                "annualized_cost_proxy": total_cost * annual_setup_volume,
            }
        )
    return pd.DataFrame(summaries)
