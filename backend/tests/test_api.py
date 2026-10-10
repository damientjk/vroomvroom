"""Tests for the stub stream of POST /api/disputes/resolve (USE_STUB_AGENTS=true).

The real agent stream is tested in test_api_agents.py.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _use_stub_agents(monkeypatch):
    monkeypatch.setenv("USE_STUB_AGENTS", "true")


def _stream_lines(resp) -> list[dict]:
    """Parse each ND-JSON line from the streaming response body."""
    lines = []
    for raw in resp.iter_lines():
        if raw:
            lines.append(json.loads(raw))
    return lines


# Patch asyncio.sleep at the module level so the stream runs instantly.
_sleep_patcher = patch("app.main.asyncio.sleep", new=AsyncMock(return_value=None))


def setUp():
    _sleep_patcher.start()


def tearDown():
    _sleep_patcher.stop()


def test_disp002_charge_upheld():
    """DISP-002: last line is ruling_data with outcome=charge_upheld, amount=5.0."""
    with patch("app.main.asyncio.sleep", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/disputes/resolve",
            json={"dispute_ticket": {"dispute_id": "DISP-002"}},
        )
    assert resp.status_code == 200
    lines = _stream_lines(resp)
    assert len(lines) > 0
    last = lines[-1]
    assert last["type"] == "ruling_data"
    assert last["data"]["outcome"] == "charge_upheld"
    assert last["data"]["amount_sgd"] == 5.0


def test_tc05_refund():
    """TC-05: ruling outcome=refund, amount=1.07."""
    with patch("app.main.asyncio.sleep", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/disputes/resolve",
            json={"dispute_ticket": {"dispute_id": "TC-05"}},
        )
    assert resp.status_code == 200
    lines = _stream_lines(resp)
    last = lines[-1]
    assert last["type"] == "ruling_data"
    assert last["data"]["outcome"] == "refund"
    assert last["data"]["amount_sgd"] == 1.07


def test_disp002_t9_escalate():
    """DISP-002-T9 (TC-09): ruling outcome=escalate, amount=0.0."""
    with patch("app.main.asyncio.sleep", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/disputes/resolve",
            json={"dispute_ticket": {"dispute_id": "DISP-002-T9"}},
        )
    assert resp.status_code == 200
    lines = _stream_lines(resp)
    last = lines[-1]
    assert last["type"] == "ruling_data"
    assert last["data"]["outcome"] == "escalate"
    assert last["data"]["amount_sgd"] == 0.0
    assert last["data"]["escalated"] is True
    assert last["data"]["escalation_reason"] is not None


def test_unknown_id_returns_404():
    """Unknown dispute_id → 404 before streaming starts."""
    resp = client.post(
        "/api/disputes/resolve",
        json={"dispute_ticket": {"dispute_id": "DOES-NOT-EXIST"}},
    )
    assert resp.status_code == 404


def test_every_line_parses_as_json():
    """Every line in the DISP-002 stream is valid JSON."""
    with patch("app.main.asyncio.sleep", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/disputes/resolve",
            json={"dispute_ticket": {"dispute_id": "DISP-002"}},
        )
    assert resp.status_code == 200
    lines = _stream_lines(resp)
    assert len(lines) > 0
    for line in lines:
        assert isinstance(line, dict)


def test_stream_contains_evidence_and_brief_data():
    """The stream includes evidence_data and brief_data lines."""
    with patch("app.main.asyncio.sleep", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/disputes/resolve",
            json={"dispute_ticket": {"dispute_id": "DISP-002"}},
        )
    assert resp.status_code == 200
    lines = _stream_lines(resp)
    types = [l.get("type") for l in lines]
    assert "evidence_data" in types
    assert "brief_data" in types


def test_health():
    """Health endpoint still works."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
