"""UI state helpers for loading mock data and calling the backend API."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st
import httpx

MOCK_DIR = Path(__file__).resolve().parent

try:
    BACKEND_URL = st.secrets.get("backend_url", "http://localhost:8000")
except Exception:
    BACKEND_URL = "http://localhost:8000"


def load_mock_ruling() -> dict[str, Any]:
    with open(MOCK_DIR / "mock_ruling.json") as f:
        return json.load(f)


def load_mock_agent_log() -> list[dict[str, Any]]:
    with open(MOCK_DIR / "mock_agent_log.json") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_dispute_types() -> list[dict[str, Any]]:
    """Return selectable dispute types for the filing form."""
    return [
        {"value": "no_show_charge", "label": "No-Show Charge"},
        {"value": "route_deviation", "label": "Route Deviation"},
    ]


def stream_agent_log(dispute_payload: dict[str, Any]):
    """Yield agent log messages from the backend streaming endpoint.

    Falls back to mock data with simulated delays when the backend is not
    reachable, so frontend development is never blocked.
    """
    try:
        with httpx.Client(timeout=60.0) as client:
            with client.stream(
                "POST",
                f"{BACKEND_URL}/api/disputes/resolve",
                json=dispute_payload,
            ) as resp:
                for line in resp.iter_lines():
                    if line:
                        yield json.loads(line)
    except Exception:
        # Mock fallback — Person A's API not ready yet
        import time

        for msg in load_mock_agent_log():
            time.sleep(0.8)
            yield msg
