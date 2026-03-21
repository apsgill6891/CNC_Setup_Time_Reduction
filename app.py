"""Streamlit executive demo for CNC setup-time optimization."""
from __future__ import annotations

from typing import Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import (
    ANNUAL_SETUP_VOLUME,
    DEFAULT_NOISE_LEVEL,
    DEFAULT_WEIGHTS,
    FIXTURE_TYPES,
    MATERIALS,
    RANDOM_SEED,
)
from data_simulator import (
    ensure_sample_history,
    generate_current_shop_state,
    generate_incoming_job,
    generate_machines_df,
)
from optimizer import compare_scenarios, evaluate_candidate_insertions, explain_recommendation, queue_burden_summary
from utils import build_before_after_queue, format_currency, format_minutes, queue_to_display_rows

st.set_page_config(
    page_title="CNC Setup-Time Optimization Demo",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def load_base_data(seed: int) -> Dict[str, pd.DataFrame]:
    """Load sample historical data and current simulated shop state."""
    machines_df = generate_machines_df()
    jobs_history_df, transitions_history_df = ensure_sample_history(seed)
    active_df, queue_df = generate_current_shop_state(machines_df, seed=seed)
    incoming_job = generate_incoming_job(machines_df, seed=seed)
    return {
        "machines": machines_df,
        "jobs_history": jobs_history_df,
        "transitions_history": transitions_history_df,
        "active": active_df,
        "queue": queue_df,
        "incoming": pd.DataFrame([incoming_job]),
    }


if "seed" not in st.session_state:
    st.session_state.seed = RANDOM_SEED

base_data = load_base_data(st.session_state.seed)
machines_df = base_data["machines"]
queue_df = base_data["queue"]
transitions_history_df = base_data["transitions_history"]

st.sidebar.title("Simulation Controls")
if st.sidebar.button("Randomize incoming job", use_container_width=True):
    st.session_state.seed += 7
    st.rerun()
if st.sidebar.button("Reset simulation", use_container_width=True):
    st.session_state.seed = RANDOM_SEED
    st.rerun()

annual_setup_volume = st.sidebar.slider("Annual setup events assumption", 500, 10000, ANNUAL_SETUP_VOLUME, 100)
noise_level = st.sidebar.slider("Historical noise level", 0.0, 0.35, DEFAULT_NOISE_LEVEL, 0.01)

st.sidebar.subheader("Machine hourly rates")
rate_overrides = {}
for _, row in machines_df.iterrows():
    rate_overrides[row["machine_id"]] = st.sidebar.number_input(
        f"{row['machine_name']}", min_value=60.0, max_value=250.0, value=float(row["setup_hourly_rate"]), step=1.0
    )
machines_df = machines_df.copy()
machines_df["setup_hourly_rate"] = machines_df["machine_id"].map(rate_overrides)

st.sidebar.subheader("Setup scoring weights")
weights = DEFAULT_WEIGHTS.copy()
for key, value in DEFAULT_WEIGHTS.items():
    weights[key] = st.sidebar.slider(key.replace("_", " ").title(), 0.0, 30.0, float(value), 1.0)

incoming_job = base_data["incoming"].iloc[0].copy()
st.sidebar.subheader("Incoming job editor")
incoming_job["material"] = st.sidebar.selectbox(
    "Material", options=MATERIALS, index=MATERIALS.index(incoming_job["material"])
)
incoming_job["size_class"] = st.sidebar.selectbox(
    "Size class", options=["small", "medium", "large"], index=["small", "medium", "large"].index(incoming_job["size_class"])
)
incoming_job["tolerance_class"] = st.sidebar.selectbox(
    "Tolerance class", options=["standard", "tight", "ultra_tight"], index=["standard", "tight", "ultra_tight"].index(incoming_job["tolerance_class"])
)
incoming_job["fixture_type"] = st.sidebar.selectbox(
    "Fixture type", options=FIXTURE_TYPES, index=FIXTURE_TYPES.index(incoming_job["fixture_type"])
)
incoming_job["rush_flag"] = st.sidebar.toggle("Rush order", value=bool(incoming_job["rush_flag"]))
incoming_job["complexity_score"] = st.sidebar.slider("Complexity score", 1.0, 10.0, float(incoming_job["complexity_score"]), 0.1)
incoming_job["estimated_run_time_minutes"] = st.sidebar.slider(
    "Estimated runtime (minutes)", 20, 480, int(incoming_job["estimated_run_time_minutes"]), 5
)

candidate_df = evaluate_candidate_insertions(
    machines_df=machines_df,
    queue_df=queue_df,
    new_job=incoming_job,
    weights=weights,
    annual_setup_volume=annual_setup_volume,
    noise_level=0.0,
)

st.title("CNC Setup-Time Optimization Demo")
st.caption(
    "Executive-ready MVP demonstrating how smarter machine assignment and sequencing decisions reduce setup time, cost, and queue disruption."
)

if candidate_df.empty:
    st.error("No feasible machine and insertion combination exists for the current incoming job. Adjust the job inputs in the sidebar.")
    st.stop()

comparison_df = compare_scenarios(candidate_df, annual_setup_volume)
best = candidate_df.iloc[0]
manual = candidate_df[candidate_df["machine_name"] == comparison_df.iloc[1]["machine_name"]]
manual = manual[manual["insert_at"] == comparison_df.iloc[1]["insert_at"]].iloc[0]
wrong = candidate_df[candidate_df["machine_name"] == comparison_df.iloc[2]["machine_name"]]
wrong = wrong[wrong["insert_at"] == comparison_df.iloc[2]["insert_at"]].iloc[0]
explanation = explain_recommendation(best, manual, wrong)

best_cost = float(best["net_incremental_setup_cost"])
manual_cost = float(manual["net_incremental_setup_cost"])
manual_minutes = float(manual["net_incremental_setup_minutes"])
utilization_df = queue_burden_summary(queue_df, machines_df)
selected_utilization = utilization_df.loc[utilization_df["machine_id"] == best["machine_id"], "utilization_proxy"].iloc[0]
utilization_improvement = max(0.0, 1.0 - selected_utilization) * 100

# Executive Summary
st.header("1. Executive Summary")
metric_cols = st.columns(6)
metric_cols[0].metric("Recommended machine", best["machine_name"])
metric_cols[1].metric("Insertion position", int(best["insert_at"]))
metric_cols[2].metric("Setup time saved vs manual", format_minutes(manual_minutes - best["net_incremental_setup_minutes"]))
metric_cols[3].metric("Setup cost saved vs manual", format_currency(manual_cost - best_cost))
metric_cols[4].metric("Annualized savings", format_currency((manual_cost - best_cost) * annual_setup_volume))
metric_cols[5].metric("Utilization improvement proxy", f"{utilization_improvement:.0f}%")
st.info(explanation)

# Current Shop State
st.header("2. Current Shop State")
shop_cols = st.columns([1.2, 1.6])
with shop_cols[0]:
    st.subheader("Machine fleet")
    st.dataframe(
        machines_df[["machine_name", "machine_type", "setup_hourly_rate", "utilization_target"]],
        use_container_width=True,
        hide_index=True,
    )
with shop_cols[1]:
    st.subheader("Queue load by machine")
    load_chart = px.bar(
        utilization_df,
        x="machine_name",
        y="queued_runtime_minutes",
        color="machine_type",
        text="queued_runtime_minutes",
        labels={"queued_runtime_minutes": "Queued runtime (min)", "machine_name": "Machine"},
    )
    load_chart.update_layout(margin=dict(l=10, r=10, t=10, b=10), xaxis_tickangle=-25)
    st.plotly_chart(load_chart, use_container_width=True)

st.subheader("Current queues")
machine_lookup = dict(zip(machines_df["machine_id"], machines_df["machine_name"]))
st.dataframe(queue_to_display_rows(queue_df, machine_lookup), use_container_width=True, hide_index=True, height=320)

# New Incoming Job
st.header("3. New Incoming Job")
incoming_cols = st.columns([1.1, 1.3])
with incoming_cols[0]:
    incoming_display = pd.DataFrame([incoming_job]).T.reset_index()
    incoming_display.columns = ["Attribute", "Value"]
    st.table(incoming_display)
with incoming_cols[1]:
    feasibility = machines_df.copy()
    feasibility["Feasible"] = machines_df.apply(lambda row: "Yes" if row["machine_id"] in set(candidate_df["machine_id"]) else "No", axis=1)
    st.dataframe(feasibility[["machine_name", "machine_type", "Feasible"]], use_container_width=True, hide_index=True)

# Recommendation Engine
st.header("4. Recommendation Engine")
ranked_display = candidate_df[
    [
        "machine_name",
        "insert_at",
        "previous_job_id",
        "next_job_id",
        "immediate_setup_impact_minutes",
        "downstream_setup_impact_minutes",
        "net_incremental_setup_minutes",
        "net_incremental_setup_cost",
    ]
].copy()
ranked_display.columns = [
    "Machine",
    "Insert position",
    "Previous job",
    "Next job",
    "Immediate setup impact (min)",
    "Downstream impact (min)",
    "Net setup burden (min)",
    "Net setup burden ($)",
]
st.dataframe(ranked_display.round(1), use_container_width=True, hide_index=True, height=280)

candidate_chart = px.bar(
    candidate_df.head(12),
    x="machine_name",
    y="net_incremental_setup_minutes",
    color="downstream_setup_impact_minutes",
    hover_data=["insert_at", "previous_job_id", "next_job_id"],
    labels={"net_incremental_setup_minutes": "Net setup burden (min)", "machine_name": "Candidate option"},
)
candidate_chart.update_layout(margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(candidate_chart, use_container_width=True)

waterfall = go.Figure(
    go.Waterfall(
        orientation="v",
        measure=["relative", "relative", "total"],
        x=["Prev → New", "New → Next vs original", "Net incremental"],
        y=[best["prev_to_new_minutes"], best["new_to_next_minutes"] - best["original_transition_minutes"], best["net_incremental_setup_minutes"]],
    )
)
waterfall.update_layout(title="Recommended option: first- and second-order setup impact", margin=dict(l=10, r=10, t=40, b=10))
st.plotly_chart(waterfall, use_container_width=True)

before_after = build_before_after_queue(queue_df, best["machine_id"], int(best["insert_at"]), incoming_job)
st.subheader("Queue before vs after recommendation")
st.dataframe(
    before_after[["scenario", "queue_position", "job_id", "part_family", "material", "fixture_type", "estimated_run_time_minutes"]],
    use_container_width=True,
    hide_index=True,
)

st.markdown(
    f"**Second-order effect:** inserting the job here breaks the original transition from **{best['previous_job_id']} → {best['next_job_id']}**. "
    f"The optimizer estimates **{best['prev_to_new_minutes']:.1f} min** for the first changeover and **{best['new_to_next_minutes']:.1f} min** for the next one, "
    f"replacing an original **{best['original_transition_minutes']:.1f} min** handoff."
)

# Scenario Comparison
st.header("5. Scenario Comparison")
comparison_fig = px.bar(
    comparison_df,
    x="scenario",
    y="setup_minutes",
    color="scenario",
    text="machine_name",
    labels={"setup_minutes": "Net setup burden (min)", "scenario": "Scenario"},
)
comparison_fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(comparison_fig, use_container_width=True)
st.dataframe(comparison_df.round(1), use_container_width=True, hide_index=True)

# Historical Transition Insights
st.header("6. Historical Transition Insights")
insight_cols = st.columns(2)
with insight_cols[0]:
    hist_fig = px.histogram(
        transitions_history_df,
        x="actual_setup_time_minutes",
        nbins=30,
        title="Historical setup time distribution",
        labels={"actual_setup_time_minutes": "Actual setup time (min)"},
    )
    hist_fig.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(hist_fig, use_container_width=True)
with insight_cols[1]:
    heatmap_df = (
        transitions_history_df.assign(material_change=lambda df: df["same_material_flag"].map({True: "Same material", False: "Material change"}))
        .groupby(["material_change", "same_part_family_flag"], as_index=False)["actual_setup_time_minutes"]
        .mean()
    )
    heatmap_fig = px.density_heatmap(
        heatmap_df,
        x="material_change",
        y="same_part_family_flag",
        z="actual_setup_time_minutes",
        text_auto=".1f",
        labels={"same_part_family_flag": "Same part family", "actual_setup_time_minutes": "Avg setup time (min)"},
        title="Average setup burden drivers",
    )
    heatmap_fig.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(heatmap_fig, use_container_width=True)

st.subheader("Historical transition sample")
st.dataframe(transitions_history_df.head(50), use_container_width=True, hide_index=True, height=260)

# Methodology / Assumptions
st.header("7. Methodology / Assumptions")
with st.expander("How the recommendation works", expanded=True):
    st.markdown(
        """
        - Simulated history represents prior observed CNC job transitions across lathes, mills, 5-axis, mill-turn, and finishing cells.
        - Setup burden is driven by the differences between adjacent jobs: material, fixture, part family, tooling, size, tolerance, and complexity.
        - The engine tests every feasible machine and insertion point for the incoming job.
        - It measures both first-order impact (previous job to new job) and second-order impact (new job to next job, minus the transition that would have happened anyway).
        - Recommendations minimize incremental setup burden, not just immediate convenience.
        - Savings shown are directional demonstration estimates suitable for executive conversations, not production promises.
        """
    )
with st.expander("Business interpretation of the scenarios"):
    st.markdown(
        """
        - **Optimized**: chooses the best feasible machine and queue position after evaluating downstream effects.
        - **Manual default**: mimics a planner assigning the job to the first feasible machine and appending it at the end.
        - **Obvious but wrong**: mimics choosing the machine that looks most similar right now while ignoring what that insertion does to the next job.
        """
    )
