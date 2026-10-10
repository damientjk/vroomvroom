"""Dispute filing form component."""
from __future__ import annotations

import streamlit as st

from state import load_dispute_types

# Defaults per dispute type, taken from the sample dataset (data/DISP-00x.json).
SAMPLE_DEFAULTS = {
    "no_show_charge": {
        "dispute_id": "DISP-002",
        "trip_id": "TRIP-2026-09945",
        "description": (
            "I was at the pickup point at Tiong Bahru Plaza on time but the driver "
            "never showed up. The app charged me a $5.00 cancellation fee for a "
            "'no-show'. I want the charge reversed."
        ),
    },
    "route_deviation": {
        "dispute_id": "DISP-001",
        "trip_id": "TRIP-2026-10012",
        "description": (
            "The driver took a significantly longer route from Tiong Bahru Plaza to "
            "VivoCity instead of the direct route. I want a refund for the extra distance."
        ),
    },
}


def _apply_defaults() -> None:
    """When the dispute type changes, reset the fields to that type's sample case."""
    defaults = SAMPLE_DEFAULTS[st.session_state.form_dispute_type]
    st.session_state.form_dispute_id = defaults["dispute_id"]
    st.session_state.form_trip_id = defaults["trip_id"]
    st.session_state.form_description = defaults["description"]


def render_dispute_form() -> dict | None:
    """Render the dispute filing form. Returns a dispute payload dict on submit."""
    st.subheader("File a Dispute")

    if "form_dispute_type" not in st.session_state:
        st.session_state.form_dispute_type = "no_show_charge"
        _apply_defaults()

    dispute_types = load_dispute_types()
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox(
            "Dispute Type",
            options=[d["value"] for d in dispute_types],
            format_func=lambda v: next(d["label"] for d in dispute_types if d["value"] == v),
            key="form_dispute_type",
            on_change=_apply_defaults,
        )
        st.text_input("Trip ID", key="form_trip_id")
    with col2:
        st.radio("Filed By", options=["rider", "driver"], horizontal=True, key="form_filed_by")
        st.text_input("Dispute ID", key="form_dispute_id")

    st.text_area("Description", height=100, key="form_description")

    if st.button("Submit Dispute", type="primary", disabled=st.session_state.get("resolving", False)):
        missing = [
            label
            for label, key in (
                ("Trip ID", "form_trip_id"),
                ("Dispute ID", "form_dispute_id"),
                ("Description", "form_description"),
            )
            if not st.session_state[key].strip()
        ]
        if missing:
            st.error(f"Please fill in: {', '.join(missing)}")
            return None
        return {
            "dispute_ticket": {
                "dispute_id": st.session_state.form_dispute_id.strip(),
                "trip_id": st.session_state.form_trip_id.strip(),
                "filed_by": st.session_state.form_filed_by,
                "dispute_type": st.session_state.form_dispute_type,
                "description": st.session_state.form_description.strip(),
            }
        }
    return None
