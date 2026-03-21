# CNC Setup-Time Optimization Demo

## Project overview
This repository contains a polished Streamlit MVP that demonstrates how a CNC shop can reduce setup time and cost by making smarter machine-assignment and queue-sequencing decisions for new incoming jobs.

The app simulates a high-mix manufacturing environment inspired by companies such as JE Bearing, with multiple machine types, a live queue, synthetic historical transition data, and a transparent recommendation engine.

## Folder structure
```text
.
├── app.py
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

## How to run
Start the Streamlit app locally:
```bash
streamlit run app.py
```

## Simulation design
The demo generates:
- A fleet of seven CNC machines across lathe, mill, 5-axis, mill-turn, and secondary operations.
- More than 500 historical jobs.
- More than 1,000 historical job-to-job setup transitions.
- A current queue on each machine with an active job plus 3-6 additional jobs.
- A new incoming job that can be randomized and partially edited in the sidebar.

Historical setup times are generated from:
- Machine-type base setup time.
- Penalties for material, fixture, tooling, operation, size, tolerance, and complexity changes.
- Credits for same-family, same-fixture, and high-tooling-overlap carryover.
- Random noise and occasional outlier events to create believable shop-floor variability.

## Optimization logic
The recommendation engine uses two layers:
1. **Weighted setup scoring model**: interpretable scoring for the setup burden between two adjacent jobs.
2. **Insertion optimizer**: tests every feasible machine and insertion point for the incoming job, then measures:
   - previous job → new job setup impact,
   - new job → next job setup impact,
   - original previous → next transition,
   - net incremental setup burden,
   - estimated setup cost and annualized savings.

The app compares:
- Optimized recommendation.
- Manual default choice.
- A seemingly logical but actually suboptimal choice that focuses only on immediate similarity.

## Why this MVP is useful
This prototype is designed for executive and client-facing demos. It makes setup-time savings visible, shows why the recommendation is better than manual planning, and highlights second-order effects that are easy to miss in a spreadsheet or whiteboard scheduling process.

## Future roadmap
- Replace simulated inputs with real ERP, MES, and machine-history data.
- Train a machine-learning model to predict actual setup times from observed transitions.
- Add due-date risk and throughput optimization alongside setup minimization.
- Connect recommendations to dispatching workflows and approval steps.
- Continuously learn from actual transitions over time.
