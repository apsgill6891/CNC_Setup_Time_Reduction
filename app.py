"""Streamlit executive demo for CNC setup-time optimization."""
from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import (
    ANNUAL_SETUP_VOLUME,
    DEFAULT_NOISE_LEVEL,
    DEFAULT_WEIGHTS,
    DUE_DATE_PRIORITIES,
    FIXTURE_TYPES,
    MACHINE_TYPE_COMPATIBILITY,
    MATERIALS,
    OPERATION_TYPES,
    PART_FAMILIES,
    RANDOM_SEED,
    SIZE_CLASSES,
    TOLERANCE_CLASSES,
)
from data_simulator import (
    generate_current_shop_state,
    generate_jobs_history,
    generate_incoming_jobs,
    generate_machines_df,
    generate_transitions_history,
)
from optimizer import (
    compare_scenarios,
    evaluate_candidate_insertions,
    explain_recommendation,
    queue_burden_summary,
    simulate_requisition_batch,
)
from utils import build_before_after_queue, format_currency, format_minutes, queue_to_display_rows

st.set_page_config(
    page_title="CNC Setup-Time Optimization Demo",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def load_base_data(seed: int) -> Dict[str, pd.DataFrame]:
    """Load reusable base datasets for the simulator."""
    machines_df = generate_machines_df()
    jobs_history_df = generate_jobs_history(machines_df, seed=seed, n_jobs=180)
    transitions_history_df = generate_transitions_history(
        jobs_history_df, machines_df, seed=seed, n_transitions=360, noise_level=DEFAULT_NOISE_LEVEL
    )
    _active_df, queue_df = generate_current_shop_state(machines_df, seed=seed)
    return {
        "machines": machines_df,
        "jobs_history": jobs_history_df,
        "transitions_history": transitions_history_df,
        "queue": queue_df,
    }


def initialize_state() -> None:
    """Initialize persistent Streamlit state."""
    st.session_state.setdefault("seed", RANDOM_SEED)
    st.session_state.setdefault("requisition_count", 3)
    st.session_state.setdefault("dataset_key", "Baseline sample")



def build_requisition_batch(machines_df: pd.DataFrame, seed: int, count: int) -> pd.DataFrame:
    """Create a reproducible requisition batch for the workbench."""
    return generate_incoming_jobs(machines_df, count=count, seed=seed).copy().reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_sample_dataset_catalog() -> Dict[str, Dict[str, object]]:
    """Build deterministic sample datasets users can run end-to-end."""
    dataset_specs = [
        {"name": "Baseline sample", "seed": RANDOM_SEED, "noise": 0.12, "requisitions": 3},
        {"name": "High-mix titanium", "seed": RANDOM_SEED + 81, "noise": 0.2, "requisitions": 4},
        {"name": "Rush-heavy queue", "seed": RANDOM_SEED + 143, "noise": 0.26, "requisitions": 5},
    ]
    machines_df = generate_machines_df()
    catalog: Dict[str, Dict[str, object]] = {}
    for spec in dataset_specs:
        jobs_df = generate_jobs_history(machines_df, seed=spec["seed"], n_jobs=180)
        transitions_df = generate_transitions_history(
            jobs_df, machines_df, seed=spec["seed"], n_transitions=360, noise_level=float(spec["noise"])
        )
        _active_df, queue_df = generate_current_shop_state(machines_df, seed=spec["seed"])
        requisitions_df = generate_incoming_jobs(machines_df, count=spec["requisitions"], seed=spec["seed"] + 301)
        catalog[spec["name"]] = {
            "seed": spec["seed"],
            "noise_level": spec["noise"],
            "machines_df": machines_df.copy(),
            "jobs_history_df": jobs_df.copy(),
            "transitions_history_df": transitions_df.copy(),
            "queue_df": queue_df.copy(),
            "requisitions_df": requisitions_df.copy().reset_index(drop=True),
        }
    return catalog



def editable_requisition_fields(requisition: pd.Series) -> pd.Series:
    """Expose the selected requisition in the sidebar for editing."""
    primary_tool_lookup = {
        "turning": "turning_tools",
        "milling": "end_mills",
        "drilling": "drills",
        "tapping": "taps",
        "boring": "boring_tools",
        "finishing": "boring_tools",
        "multi_op": "multi_axis_tools",
    }
    requisition = requisition.copy()
    st.sidebar.subheader("Selected requisition")
    requisition["part_family"] = st.sidebar.selectbox(
        "Part family", PART_FAMILIES, index=PART_FAMILIES.index(requisition["part_family"])
    )
    requisition["operation_type"] = st.sidebar.selectbox(
        "Operation type", OPERATION_TYPES, index=OPERATION_TYPES.index(requisition["operation_type"])
    )
    requisition["material"] = st.sidebar.selectbox(
        "Material", MATERIALS, index=MATERIALS.index(requisition["material"])
    )
    requisition["size_class"] = st.sidebar.selectbox(
        "Size class", SIZE_CLASSES, index=SIZE_CLASSES.index(requisition["size_class"])
    )
    requisition["tolerance_class"] = st.sidebar.selectbox(
        "Tolerance class", TOLERANCE_CLASSES, index=TOLERANCE_CLASSES.index(requisition["tolerance_class"])
    )
    requisition["fixture_type"] = st.sidebar.selectbox(
        "Fixture type", FIXTURE_TYPES, index=FIXTURE_TYPES.index(requisition["fixture_type"])
    )
    requisition["due_date_priority"] = st.sidebar.selectbox(
        "Due date priority",
        DUE_DATE_PRIORITIES,
        index=DUE_DATE_PRIORITIES.index(requisition["due_date_priority"]),
    )
    requisition["rush_flag"] = st.sidebar.toggle("Rush order", value=bool(requisition["rush_flag"]))
    requisition["complexity_score"] = st.sidebar.slider(
        "Complexity score", min_value=1.0, max_value=10.0, value=float(requisition["complexity_score"]), step=0.1
    )
    requisition["number_of_operations"] = st.sidebar.slider(
        "Number of operations", min_value=1, max_value=10, value=int(requisition["number_of_operations"]), step=1
    )
    requisition["estimated_run_time_minutes"] = st.sidebar.slider(
        "Estimated runtime (minutes)", min_value=20, max_value=480, value=int(requisition["estimated_run_time_minutes"]), step=5
    )
    requisition["batch_size"] = st.sidebar.slider(
        "Batch size", min_value=1, max_value=500, value=int(requisition["batch_size"]), step=1
    )
    requisition["required_machine_type"] = MACHINE_TYPE_COMPATIBILITY[requisition["operation_type"]][0]
    requisition["tool_family_primary"] = primary_tool_lookup[requisition["operation_type"]]
    return requisition



def render_top_metrics(best: pd.Series, comparison_df: pd.DataFrame, utilization_df: pd.DataFrame, annual_setup_volume: int) -> None:
    """Render executive KPI cards."""
    manual = comparison_df.loc[comparison_df["scenario"] == "Manual default"].iloc[0]
    selected_utilization = utilization_df.loc[
        utilization_df["machine_name"] == best["machine_name"], "utilization_proxy"
    ].iloc[0]
    utilization_improvement = max(0.0, 1.0 - float(selected_utilization)) * 100
    metric_cols = st.columns(6)
    metric_cols[0].metric("Recommended machine", str(best["machine_name"]))
    metric_cols[1].metric("Insertion position", int(best["insert_at"]))
    metric_cols[2].metric(
        "Setup time saved vs manual",
        format_minutes(float(manual["setup_minutes"]) - float(best["net_incremental_setup_minutes"])),
    )
    metric_cols[3].metric(
        "Setup cost saved vs manual",
        format_currency(float(manual["setup_cost"]) - float(best["net_incremental_setup_cost"])),
    )
    metric_cols[4].metric(
        "Annualized savings",
        format_currency((float(manual["setup_cost"]) - float(best["net_incremental_setup_cost"])) * annual_setup_volume),
    )
    metric_cols[5].metric("Utilization improvement proxy", f"{utilization_improvement:.0f}%")



def recommendation_context(candidate_df: pd.DataFrame, comparison_df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Resolve scenario rows for explanation rendering."""
    best = candidate_df.iloc[0]
    manual_row = comparison_df.loc[comparison_df["scenario"] == "Manual default"].iloc[0]
    wrong_row = comparison_df.loc[comparison_df["scenario"] == "Obvious but wrong"].iloc[0]
    manual = candidate_df[
        (candidate_df["machine_name"] == manual_row["machine_name"]) & (candidate_df["insert_at"] == manual_row["insert_at"])
    ].iloc[0]
    wrong = candidate_df[
        (candidate_df["machine_name"] == wrong_row["machine_name"]) & (candidate_df["insert_at"] == wrong_row["insert_at"])
    ].iloc[0]
    return best, manual, wrong



def main() -> None:
    """Render the full CNC scheduling simulator experience."""
    initialize_state()
    st.sidebar.title("Simulation Controls")
    dataset_catalog = load_sample_dataset_catalog()
    dataset_names = list(dataset_catalog.keys())
    st.session_state.dataset_key = st.sidebar.selectbox(
        "Sample data pack",
        dataset_names,
        index=dataset_names.index(st.session_state.dataset_key) if st.session_state.dataset_key in dataset_names else 0,
        help="Each sample pack includes machine queues, requisitions, and history so all modules run immediately.",
    )
    selected_dataset = dataset_catalog[st.session_state.dataset_key]
    machines_df = selected_dataset["machines_df"].copy()
    queue_df = selected_dataset["queue_df"].copy()
    transitions_history_df = selected_dataset["transitions_history_df"].copy()
    requisitions_df = selected_dataset["requisitions_df"].copy()
    st.session_state.requisition_count = len(requisitions_df)

    uploaded_requisitions = st.sidebar.file_uploader("Optional: upload requisition CSV", type=["csv"])
    required_req_columns = [
        "job_id",
        "part_family",
        "operation_type",
        "material",
        "size_class",
        "tolerance_class",
        "fixture_type",
        "estimated_run_time_minutes",
        "batch_size",
        "rush_flag",
        "complexity_score",
        "number_of_operations",
        "due_date_priority",
        "required_machine_type",
        "tool_family_primary",
    ]
    if uploaded_requisitions is not None:
        uploaded_df = pd.read_csv(uploaded_requisitions)
        missing_columns = [col for col in required_req_columns if col not in uploaded_df.columns]
        if missing_columns:
            st.sidebar.error(f"CSV missing required columns: {', '.join(missing_columns)}")
            st.stop()
        requisitions_df = uploaded_df[required_req_columns].copy().reset_index(drop=True)
        st.sidebar.success(f"Loaded {len(requisitions_df)} requisitions from CSV.")

    st.sidebar.caption(
        "Click through modules below to run: (1) candidate insertion engine, (2) scenario comparison, (3) batch simulation."
    )

    annual_setup_volume = st.sidebar.slider(
        "Annual setup events assumption", min_value=500, max_value=10000, value=ANNUAL_SETUP_VOLUME, step=100
    )
    noise_level = st.sidebar.slider(
        "Historical noise level",
        0.0,
        0.35,
        float(selected_dataset["noise_level"]) if uploaded_requisitions is None else DEFAULT_NOISE_LEVEL,
        0.01,
    )

    st.sidebar.subheader("Machine hourly rates")
    rate_overrides = {}
    for _, row in machines_df.iterrows():
        rate_overrides[row["machine_id"]] = st.sidebar.number_input(
            row["machine_name"], min_value=60.0, max_value=250.0, value=float(row["setup_hourly_rate"]), step=1.0
        )
    machines_df["setup_hourly_rate"] = machines_df["machine_id"].map(rate_overrides)

    st.sidebar.subheader("Setup scoring weights")
    weights = DEFAULT_WEIGHTS.copy()
    for key, value in DEFAULT_WEIGHTS.items():
        weights[key] = st.sidebar.slider(key.replace("_", " ").title(), 0.0, 30.0, float(value), 1.0)

    selected_idx = st.sidebar.selectbox(
        "Active requisition", options=list(range(len(requisitions_df))), format_func=lambda i: requisitions_df.loc[i, "job_id"]
    )
    requisitions_df.loc[selected_idx] = editable_requisition_fields(requisitions_df.loc[selected_idx])
    selected_requisition = requisitions_df.loc[selected_idx].copy()

    candidate_df = evaluate_candidate_insertions(
        machines_df=machines_df,
        queue_df=queue_df,
        new_job=selected_requisition,
        weights=weights,
        annual_setup_volume=annual_setup_volume,
        noise_level=0.0,
    )

    st.title("CNC Setup-Time Optimization Simulator")
    st.caption(
        "A requisition-driven manufacturing demo showing how a high-mix CNC shop can place new parts into the schedule with lower setup burden and better downstream outcomes."
    )

    if candidate_df.empty:
        st.error(
            "No feasible machine and insertion combination exists for the selected requisition. Adjust the requisition in the sidebar."
        )
        st.stop()

    comparison_df = compare_scenarios(candidate_df, annual_setup_volume)
    best, manual, wrong = recommendation_context(candidate_df, comparison_df)
    explanation = explain_recommendation(best, manual, wrong)
    utilization_df = queue_burden_summary(queue_df, machines_df)
    batch_summary_df = simulate_requisition_batch(
        machines_df=machines_df,
        base_queue_df=queue_df,
        requisitions_df=requisitions_df,
        weights=weights,
        annual_setup_volume=annual_setup_volume,
    )

    render_top_metrics(best, comparison_df, utilization_df, annual_setup_volume)
    module_status_cols = st.columns(3)
    module_status_cols[0].success(f"Module 1: Candidate engine ran ({len(candidate_df)} insertion options)")
    module_status_cols[1].success(f"Module 2: Scenario comparison ran ({len(comparison_df)} strategies)")
    module_status_cols[2].success(f"Module 3: Batch simulation ran ({len(batch_summary_df)} strategy totals)")
    st.info(explanation)

    exec_tab, shop_tab, requisition_tab, engine_tab, compare_tab, history_tab, method_tab = st.tabs(
        [
            "Executive Summary",
            "Current Shop State",
            "New Part Requisitions",
            "Recommendation Engine",
            "Scenario Comparison",
            "Historical Insights",
            "Methodology",
        ]
    )

    with exec_tab:
        left, right = st.columns([1.1, 1.4])
        with left:
            st.subheader("Why the recommendation wins")
            st.markdown(
                f"""
                **Selected requisition:** {selected_requisition['job_id']} / {selected_requisition['part_family']} / {selected_requisition['material']}  
                **Recommended machine:** {best['machine_name']}  
                **Best insertion position:** {int(best['insert_at'])}  
                **Net setup burden:** {best['net_incremental_setup_minutes']:.1f} minutes  
                **Manual default burden:** {manual['net_incremental_setup_minutes']:.1f} minutes
                """
            )
            st.markdown(
                f"The recommended choice breaks the original **{best['previous_job_id']} → {best['next_job_id']}** transition, "
                f"then replaces it with **{best['previous_job_id']} → {selected_requisition['job_id']}** and "
                f"**{selected_requisition['job_id']} → {best['next_job_id']}**. This produces a smaller total penalty "
                f"than the manual or obvious alternatives."
            )
        with right:
            scenario_fig = px.bar(
                comparison_df,
                x="scenario",
                y="setup_minutes",
                color="scenario",
                text="machine_name",
                labels={"setup_minutes": "Net setup burden (min)", "scenario": "Decision path"},
            )
            scenario_fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(scenario_fig, use_container_width=True)

    with shop_tab:
        fleet_col, queue_col = st.columns([1.0, 1.5])
        with fleet_col:
            st.subheader("Machine fleet")
            st.dataframe(
                machines_df[["machine_name", "machine_type", "setup_hourly_rate", "utilization_target"]],
                use_container_width=True,
                hide_index=True,
            )
        with queue_col:
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
        st.subheader("Current machine queues")
        machine_lookup = dict(zip(machines_df["machine_id"], machines_df["machine_name"]))
        st.dataframe(queue_to_display_rows(queue_df, machine_lookup), use_container_width=True, hide_index=True, height=340)

    with requisition_tab:
        st.subheader("Incoming requisition batch")
        requisition_display = requisitions_df[
            [
                "job_id",
                "part_family",
                "operation_type",
                "material",
                "size_class",
                "tolerance_class",
                "fixture_type",
                "estimated_run_time_minutes",
                "batch_size",
                "rush_flag",
            ]
        ].copy()
        requisition_display.columns = [
            "Requisition",
            "Part family",
            "Operation",
            "Material",
            "Size",
            "Tolerance",
            "Fixture",
            "Runtime (min)",
            "Batch size",
            "Rush",
        ]
        st.dataframe(requisition_display, use_container_width=True, hide_index=True)

        st.subheader("Batch-level scheduling impact")
        batch_fig = px.bar(
            batch_summary_df,
            x="strategy",
            y="total_setup_minutes",
            color="strategy",
            text="total_setup_cost",
            labels={"total_setup_minutes": "Total setup burden for requisition batch (min)", "strategy": "Scheduling strategy"},
        )
        batch_fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(batch_fig, use_container_width=True)
        st.dataframe(batch_summary_df.round(1), use_container_width=True, hide_index=True)

    with engine_tab:
        st.subheader("Ranked candidate insertion options")
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
            "Immediate impact (min)",
            "Second-order impact (min)",
            "Net burden (min)",
            "Net burden ($)",
        ]
        st.dataframe(ranked_display.round(1), use_container_width=True, hide_index=True, height=320)

        chart_left, chart_right = st.columns(2)
        with chart_left:
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
        with chart_right:
            waterfall = go.Figure(
                go.Waterfall(
                    orientation="v",
                    measure=["relative", "relative", "total"],
                    x=["Prev → New", "New → Next minus original", "Net incremental"],
                    y=[
                        best["prev_to_new_minutes"],
                        best["new_to_next_minutes"] - best["original_transition_minutes"],
                        best["net_incremental_setup_minutes"],
                    ],
                )
            )
            waterfall.update_layout(
                title="Recommended option: first- and second-order setup impact",
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(waterfall, use_container_width=True)

        before_after = build_before_after_queue(queue_df, best["machine_id"], int(best["insert_at"]), selected_requisition)
        st.subheader("Queue before vs after recommendation")
        st.dataframe(
            before_after[
                ["scenario", "queue_position", "job_id", "part_family", "material", "fixture_type", "estimated_run_time_minutes"]
            ],
            use_container_width=True,
            hide_index=True,
        )

    with compare_tab:
        st.subheader("Optimized vs manual vs obvious-but-wrong")
        st.dataframe(comparison_df.round(1), use_container_width=True, hide_index=True)
        st.markdown(
            f"""
            **Plain-English explanation**  
            {explanation}  

            The manual path would add **{manual['net_incremental_setup_minutes']:.1f} minutes**, while the obvious choice would add
            **{wrong['net_incremental_setup_minutes']:.1f} minutes** because it overweights local similarity and underweights what happens to the next queued part.
            """
        )

    with history_tab:
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
                transitions_history_df.assign(
                    material_change=lambda df: df["same_material_flag"].map({True: "Same material", False: "Material change"})
                )
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
        st.dataframe(transitions_history_df.head(50), use_container_width=True, hide_index=True, height=280)
        st.caption(
            f"Historical transitions reflect the chosen noise level of {noise_level:.2f}; higher values widen the spread of observed setups for demo purposes."
        )

    with method_tab:
        with st.expander("How the simulator works", expanded=True):
            st.markdown(
                """
                - The simulator models a high-mix CNC shop with lathes, mills, 5-axis, mill-turn, and finishing resources.
                - New part requisitions are evaluated against machine compatibility, material support, size range, and complexity constraints.
                - For each feasible insertion point, the engine estimates the setup from the previous job to the new part and from the new part to the next job.
                - It then subtracts the transition that would have happened anyway to calculate true incremental burden.
                - This approach makes second-order effects visible: some inserts look attractive locally, but create expensive changeovers later.
                - Batch-level summaries show how repeated planner defaults can accumulate into large annual cost exposure.
                """
            )
        with st.expander("Why the Streamlit page previously looked like a README"):
            st.markdown(
                """
                If a deployment target is pointed at the repository homepage instead of the Streamlit entry file, it can display the README rather than the simulator UI.
                This repo now includes both `app.py` and a `streamlit_app.py` wrapper so Streamlit Cloud or other hosts have an explicit app entrypoint.
                """
            )


if __name__ == "__main__":
    main()
