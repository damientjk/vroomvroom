"""Ruling card and evidence card components."""
from __future__ import annotations

from typing import Any

import streamlit as st

OUTCOME_LABELS = {
    "refund": "Refund",
    "compensation": "Compensation",
    "no_action": "No Action",
    "charge_upheld": "Charge Upheld",
    "charge_reversed": "Charge Reversed",
    "escalate": "Escalated to Human",
}

OUTCOME_COLORS = {
    "refund": "#1a73e8",
    "compensation": "#1a73e8",
    "no_action": "#5f6368",
    "charge_upheld": "#e8451a",
    "charge_reversed": "#1a73e8",
    "escalate": "#d93025",
}

TOOL_LABELS = {
    "no_show_check": "No-Show Check",
    "route_deviation": "Route Deviation",
    "fare_validate": "Fare Validation",
    "history_lookup": "History Lookup",
}

TOOL_ICONS = {
    "no_show_check": "📍",
    "route_deviation": "🗺️",
    "fare_validate": "💳",
    "history_lookup": "📋",
}


def render_ruling_card(ruling: dict[str, Any], audience: str) -> None:
    """Render a ruling card for either the rider or driver perspective."""
    outcome = ruling.get("outcome", "no_action")
    label = OUTCOME_LABELS.get(outcome, outcome)
    color = OUTCOME_COLORS.get(outcome, "#5f6368")
    confidence = ruling.get("confidence", 0)
    amount = ruling.get("amount_sgd", 0)
    clauses = ruling.get("clauses_cited", [])
    escalated = ruling.get("escalated", False)

    explanation = (
        ruling.get("explanation_rider", "")
        if audience == "rider"
        else ruling.get("explanation_driver", "")
    )

    title = "Rider View" if audience == "rider" else "Driver View"

    with st.container(border=True):
        st.markdown(f"#### {title}")
        st.markdown(
            f"<span style='color:{color};font-weight:700;font-size:1.2em;'>{label}</span>",
            unsafe_allow_html=True,
        )

        if amount > 0:
            st.metric("Amount (SGD)", f"${amount:.2f}")

        col1, col2 = st.columns(2)
        col1.metric("Confidence", f"{confidence:.0%}")
        col2.metric("Clauses Cited", ", ".join(clauses) or "—")

        st.markdown("**Explanation**")
        st.info(explanation)

        if escalated:
            st.warning(
                f"⚠️ Escalated to human review: {ruling.get('escalation_reason', 'low confidence')}"
            )


def render_evidence_card(evidence: dict[str, Any]) -> None:
    """Render an evidence tool output card.

    Expected schema (see schemas.md §2 Evidence output):
        dispute_id, tool, facts (dict), flags (list[str])
    """
    tool = evidence.get("tool", "unknown")
    facts = evidence.get("facts", {})
    flags = evidence.get("flags", [])
    label = TOOL_LABELS.get(tool, tool)
    icon = TOOL_ICONS.get(tool, "🔧")

    with st.container(border=True):
        st.markdown(f"#### {icon} {label}")
        st.caption(f"Dispute {evidence.get('dispute_id', '—')}")

        if facts:
            for key, value in facts.items():
                display_key = key.replace("_", " ").title()
                if isinstance(value, bool):
                    val_str = "✅ Yes" if value else "❌ No"
                elif isinstance(value, list) and not value:
                    val_str = "—"
                elif isinstance(value, list):
                    val_str = ", ".join(str(v) for v in value)
                else:
                    val_str = str(value)
                st.markdown(f"**{display_key}**: {val_str}")

        if flags:
            for flag in flags:
                st.warning(f"⚠️ {flag}")
