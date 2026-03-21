# CNC Setup-Time Optimization Demo

## Project overview
This repository contains a Streamlit MVP that demonstrates how a CNC shop can reduce setup time and cost by making smarter machine-assignment and queue-sequencing decisions for new part requisitions.

The app simulates a high-mix manufacturing environment inspired by companies such as JE Bearing, with multiple machine types, synthetic historical transition data, live queues, and a requisition workbench that shows why the recommended scheduling move is better than manual planning.

## Folder structure
```text
.
├── app.py
├── streamlit_app.py
├── config.py
├── data_simulator.py
├── models.py
├── optimizer.py
├── requirements.txt
├── sample_data/
│   ├── jobs_history.csv
│   └── transitions_history.csv
├── utils.py
└── README.md
```

## How to install
1. Create and activate a Python virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## How to run locally
Start the Streamlit simulator:
```bash
streamlit run app.py
```

## How to deploy
If you are using Streamlit Community Cloud or another hosted Streamlit service, point the deployment at `streamlit_app.py` or `app.py`. If you point a website at the repository homepage instead, you may only see the README rather than the live simulator.

## Simulator design
The demo generates:
- A fleet of seven CNC machines across lathe, mill, 5-axis, mill-turn, and secondary operations.
- More than 500 historical jobs.
- More than 1,000 historical job-to-job setup transitions.
- A current queue on each machine with active and queued work.
- A configurable batch of new part requisitions that can be randomized and edited in the sidebar.

Historical setup times are generated from:
- Machine-type base setup time.
- Penalties for material, fixture, tooling, operation, size, tolerance, and complexity changes.
- Credits for same-family, same-fixture, and high-tooling-overlap carryover.
- Random noise and occasional outlier events to create believable shop-floor variability.

## Optimization logic
The recommendation engine uses two layers:
1. **Weighted setup scoring model**: interpretable scoring for the setup burden between two adjacent jobs.
2. **Insertion optimizer**: tests every feasible machine and insertion point for the incoming requisition, then measures:
   - previous job → new job setup impact,
   - new job → next job setup impact,
   - original previous → next transition,
   - net incremental setup burden,
   - estimated setup cost and annualized savings.

The app compares:
- Optimized recommendation.
- Manual default choice.
- A seemingly logical but actually suboptimal choice that focuses only on immediate similarity.
- Batch-level cumulative impact across multiple new requisitions.

## Why this MVP is useful
This prototype is designed for executive and client-facing demos. It makes setup-time savings visible, shows why the recommendation is better than manual planning, and highlights second-order effects that are easy to miss in spreadsheet-style scheduling.

## Future roadmap
- Replace simulated inputs with real ERP, MES, and machine-history data.
- Train a machine-learning model to predict actual setup times from observed transitions.
- Add due-date risk and throughput optimization alongside setup minimization.
- Connect recommendations to dispatching workflows and approval steps.
- Continuously learn from actual transitions over time.
