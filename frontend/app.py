"""Ryde Track — Dispute Resolution Frontend (Streamlit)

Run:
    cd frontend
    pip install -r requirements.txt
    streamlit run app.py

Builds against mock data by default. When the backend is running and reachable,
the courtroom log streams real agent messages from the FastAPI endpoint.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make frontend/ importable when running `streamlit run app.py` from frontend/
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from state import load_mock_ruling, load_mock_agent_log, load_mock_evidence, stream_agent_log
from components.dispute_form import render_dispute_form
from components.courtroom_log import render_courtroom_log
from components.ruling_cards import render_ruling_card, render_evidence_card

st.set_page_config(
    page_title="Ryde Track — Dispute Resolution",
    page_icon="⚖️",
    layout="wide",
)


def main() -> None:
    st.title("Ryde Track")
    st.caption("Multi-Agent Autonomous Dispute Resolution")

    # --- Session state init ---
    if "agent_log" not in st.session_state:
        st.session_state.agent_log = []
    if "ruling" not in st.session_state:
        st.session_state.ruling = None
    if "evidence" not in st.session_state:
        st.session_state.evidence = []
    if "resolving" not in st.session_state:
        st.session_state.resolving = False

    # --- Step 1: Dispute filing form ---
    dispute_payload = render_dispute_form()

    col_resolve, col_mock, col_clear = st.columns([1, 1, 1])
    with col_resolve:
        if st.button("Resolve Dispute", type="primary", disabled=st.session_state.resolving):
            st.session_state.resolving = True
            st.session_state.agent_log = []
            st.rerun()
    with col_mock:
        if st.button("Load Mock Data"):
            st.session_state.agent_log = load_mock_agent_log()
            st.session_state.evidence = load_mock_evidence()
            st.session_state.ruling = load_mock_ruling()
    with col_clear:
        if st.button("Clear"):
            st.session_state.agent_log = []
            st.session_state.evidence = []
            st.session_state.ruling = None

    # --- Step 2: Resolve (stream agents) ---
    if st.session_state.resolving:
        with st.status("Resolving dispute...", expanded=True) as status:
            for msg in stream_agent_log(dispute_payload or {}):
                st.session_state.agent_log.append(msg)
            st.session_state.evidence = load_mock_evidence()  # TODO: use real evidence from stream
            st.session_state.ruling = load_mock_ruling()  # TODO: use real ruling from stream
            status.update(label="Resolution complete", state="complete")
        st.session_state.resolving = False

    # --- Step 3: Courtroom log ---
    if st.session_state.agent_log:
        render_courtroom_log(st.session_state.agent_log)

    # --- Step 4: Evidence cards ---
    if st.session_state.evidence:
        st.divider()
        st.subheader("Evidence")
        col_e1, col_e2 = st.columns(2)
        for i, ev in enumerate(st.session_state.evidence):
            target = col_e1 if i % 2 == 0 else col_e2
            with target:
                render_evidence_card(ev)

    # --- Step 5: Ruling cards ---
    if st.session_state.ruling:
        st.divider()
        st.subheader("Ruling")
        col_r, col_d = st.columns(2)
        with col_r:
            render_ruling_card(st.session_state.ruling, audience="rider")
        with col_d:
            render_ruling_card(st.session_state.ruling, audience="driver")


if __name__ == "__main__":
    main()
