"""Dispute filing form component."""
from __future__ import annotations

import streamlit as st

from state import load_dispute_types


def render_dispute_form() -> dict | None:
    """Render the dispute filing form. Returns a dispute payload dict on submit."""
    st.subheader("File a Dispute")

    with st.form("dispute_form"):
        col1, col2 = st.columns(2)

        with col1:
            trip_id = st.text_input("Trip ID", value="TRIP-2026-09945")
            dispute_types = load_dispute_types()
            dispute_type = st.selectbox(
                "Dispute Type",
                options=[d["value"] for d in dispute_types],
                format_func=lambda v: next(
                    d["label"] for d in dispute_types if d["value"] == v
                ),
            )

        with col2:
            filed_by = st.radio(
                "Filed By",
                options=["rider", "driver"],
                horizontal=True,
            )
            st.caption("Paste a dispute ID or load from sample data")

        dispute_id = st.text_input("Dispute ID", value="DISP-002")
        description = st.text_area(
            "Description",
            value="I was at the pickup point on time but the driver never showed up.",
            height=80,
        )

        submitted = st.form_submit_button("Submit Dispute", type="primary")

    if submitted:
        return {
            "dispute_ticket": {
                "dispute_id": dispute_id,
                "trip_id": trip_id,
                "filed_by": filed_by,
                "dispute_type": dispute_type,
                "description": description,
            }
        }
    return None
