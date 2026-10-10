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
    DEFAULT_DEMO_MODE = bool(st.secrets.get("demo_mode", True))
except Exception:
    BACKEND_URL = "http://localhost:8000"
    DEFAULT_DEMO_MODE = True


def load_mock_ruling() -> dict[str, Any]:
    with open(MOCK_DIR / "mock_ruling.json") as f:
        return json.load(f)


def load_mock_agent_log() -> list[dict[str, Any]]:
    with open(MOCK_DIR / "mock_agent_log.json") as f:
        return json.load(f)


def load_mock_evidence() -> list[dict[str, Any]]:
    with open(MOCK_DIR / "mock_evidence.json") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_dispute_types() -> list[dict[str, Any]]:
    """Return selectable dispute types for the filing form."""
    return [
        {"value": "no_show_charge", "label": "No-Show Charge"},
        {"value": "route_deviation", "label": "Route Deviation"},
    ]


class BackendError(Exception):
    """Raised when the backend is unreachable or returns an invalid response."""


def _mock_stream():
    import random
    import time

    for msg in load_mock_agent_log():
        time.sleep(random.uniform(0.6, 1.2))
        yield msg


def stream_agent_log(dispute_payload: dict[str, Any], demo_mode: bool = True):
    """Yield agent log messages.

    In demo mode, replays the mock log with simulated delays. Otherwise streams
    NDJSON from the backend and raises BackendError on any failure, so the UI
    never passes off mock data as a real ruling.
    """
    if demo_mode:
        yield from _mock_stream()
        return

    timeout = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream(
                "POST",
                f"{BACKEND_URL}/api/disputes/resolve",
                json=dispute_payload,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line:
                        yield json.loads(line)
    except httpx.HTTPStatusError as e:
        raise BackendError(f"Backend returned HTTP {e.response.status_code}.") from e
    except httpx.HTTPError as e:
        raise BackendError(f"Could not reach the backend at {BACKEND_URL}.") from e
    except json.JSONDecodeError as e:
        raise BackendError("Backend sent a malformed message.") from e
