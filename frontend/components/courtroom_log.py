"""Courtroom log component — displays agent messages as they arrive."""
from __future__ import annotations

from typing import Any

import streamlit as st

AGENT_STYLES = {
    "rider_advocate": {"icon": "R", "color": "#1a73e8", "label": "Rider Advocate"},
    "driver_advocate": {"icon": "D", "color": "#e8451a", "label": "Driver Advocate"},
    "judge": {"icon": "J", "color": "#6b21a8", "label": "Judge"},
    "system": {"icon": "S", "color": "#5f6368", "label": "System"},
}

TYPE_ICONS = {
    "evidence": "🔍",
    "argument": "📋",
    "rebuttal": "⚡",
    "ruling": "⚖️",
}


def render_courtroom_log(messages: list[dict[str, Any]]) -> None:
    """Render the live courtroom log from a list of agent messages."""
    st.subheader("Courtroom")
    st.caption("Agents build their cases in real time")

    log_container = st.container()
    with log_container:
        for msg in messages:
            agent = msg.get("agent", "system")
            msg_type = msg.get("type", "evidence")
            content = msg.get("content", "")
            style = AGENT_STYLES.get(agent, AGENT_STYLES["system"])
            type_icon = TYPE_ICONS.get(msg_type, "•")

            st.markdown(
                f"""
                <div style="
                    border-left: 3px solid {style['color']};
                    padding: 8px 12px;
                    margin: 6px 0;
                    background: #f8f9fa;
                    border-radius: 0 4px 4px 0;
                ">
                    <span style="color:{style['color']};font-weight:600;">
                        {type_icon} {style['label']}
                    </span>
                    <span style="color:#80868b;font-size:0.8em;margin-left:8px;">
                        {msg_type}
                    </span>
                    <div style="margin-top:4px;color:#202124;">{content}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
