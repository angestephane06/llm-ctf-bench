"""Compare models and replay agent traces: `make dashboard`."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

RESULTS = Path(__file__).resolve().parents[1] / "results"

st.set_page_config(page_title="llm-ctf-bench", layout="wide")
st.title("llm-ctf-bench")

campaigns = sorted(p for p in RESULTS.iterdir() if (p / "summary.csv").exists())
if not campaigns:
    st.info("No campaign yet. Run `make smoke` or `make eval`.")
    st.stop()

campaign = st.sidebar.selectbox("Campaign", campaigns, format_func=lambda p: p.name)
summary = pd.read_csv(campaign / "summary.csv")
episodes = pd.read_csv(campaign / "episodes.csv")
metadata_file = campaign / "metadata.json"

overall = summary[summary["category"] == "ALL"].set_index("model")
st.subheader("Success rate by model")
cols = st.columns(len(overall))
for col, (model, row) in zip(cols, overall.iterrows(), strict=True):
    col.metric(
        model,
        f"{row['success_rate']:.0%}",
        help=f"{row['solved']}/{row['episodes']} episodes, std across seeds "
        f"{row['success_std']:.2f}",
    )
st.bar_chart(overall["success_rate"])

st.subheader("By category")
by_cat = summary[summary["category"] != "ALL"].pivot(
    index="category", columns="model", values="success_rate"
)
st.dataframe(by_cat.style.format("{:.0%}"), use_container_width=True)

st.subheader("Cost and behaviour")
st.dataframe(
    overall[
        [
            "mean_turns",
            "mean_turns_solved",
            "mean_wall_time_s",
            "total_tokens",
            "seen_not_submitted",
            "errors",
        ]
    ],
    use_container_width=True,
)

st.subheader("Trace viewer")
c1, c2, c3 = st.columns(3)
model = c1.selectbox("Model", sorted(episodes["model"].unique()))
task_id = c2.selectbox("Task", sorted(episodes["task_id"].unique()))
seed = c3.selectbox("Seed", sorted(episodes["seed"].unique()))
slug = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in model)
trace_file = campaign / "traces" / slug / f"task{task_id}_seed{seed}.json"
if not trace_file.exists():
    st.warning("No trace for this combination.")
else:
    trace = json.loads(trace_file.read_text(encoding="utf-8"))
    verdict = "solved" if trace["solved"] else trace["stop_reason"]
    st.markdown(
        f"**{verdict}** in {trace['turns']} turns, {trace['wall_time_s']:.0f}s, "
        f"{trace['submissions']} submission(s), flag seen: {trace['flag_seen']}"
    )
    for step in trace["steps"]:
        with st.expander(f"Turn {step['turn']}: {step['action']} {step['content'][:80]}"):
            st.markdown("**Model reply**")
            st.code(step["reply"], language="markdown")
            st.markdown("**Observation**")
            st.code(step["observation"], language="text")

if metadata_file.exists():
    with st.sidebar.expander("Reproducibility metadata"):
        st.json(json.loads(metadata_file.read_text(encoding="utf-8")))
