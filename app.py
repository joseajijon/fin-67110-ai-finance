#!/usr/bin/env python3
"""Streamlit page for the fixed-order FIN 67110 agent team."""

from pathlib import Path

import streamlit as st

from agent_team import NODE_ORDER, run_team


st.set_page_config(page_title="FIN 67110 Equity Research Desk", layout="wide")
st.title("Equity Research Agent Team")
st.caption("Fixed order: " + " → ".join(NODE_ORDER))

with st.form("run-team"):
    ticker = st.text_input("Ticker").strip().upper()
    peers = st.text_input("Optional peer tickers")
    filed = st.text_input("Optional filing-time override", placeholder="YYYY-MM-DDTHH:MM:SS Eastern")
    submitted = st.form_submit_button("Run agent team")

if submitted:
    status = st.status("Running", expanded=True)
    node_line = status.empty()
    seen: list[str] = []

    def emit(name: str) -> None:
        seen.append(name)
        node_line.write(" → ".join(seen))

    try:
        run_dir = run_team(ticker, peers, filed.strip() or None, "gpt-5-mini", emit=emit)
        status.update(label="Complete", state="complete", expanded=False)
        report = (Path(run_dir) / "verified_report.md").read_text(encoding="utf-8")
        st.markdown(report)
        st.caption(f"Saved run: {run_dir}")
    except Exception as exc:
        status.update(label="Run failed", state="error", expanded=True)
        st.error(str(exc))

