"""Tests for the real agent stream of POST /api/disputes/resolve (LangGraph).

LLM calls are replaced with canned replies, so no ADP credits are used.
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agents.llm import LLMError, LLMResult
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _use_real_agents(monkeypatch):
    monkeypatch.delenv("USE_STUB_AGENTS", raising=False)


def _result(payload: dict) -> LLMResult:
    return LLMResult(
        text=json.dumps(payload), input_tokens=None, output_tokens=None,
        total_tokens=1, cached=False,
    )


def _fake_chat(evidence_ref: str, clause: str, judge_findings: dict | None = None,
               seen: list | None = None):
    async def chat(agent, system_prompt, user_message, **kwargs):
        if seen is not None:
            seen.append((agent, user_message))
        if agent == "judge":
            return _result({
                "rider_requested_detour": None,
                "traffic_justified": None,
                **(judge_findings or {}),
                "confidence": 0.95,
                "clauses_cited": [clause],
                "explanation_rider": "For the rider.",
                "explanation_driver": "For the driver.",
            })
        side = agent.removesuffix("_advocate")
        return _result({
            "dispute_id": "ignored",
            "side": side,
            "position": f"{side} position",
            "arguments": [{
                "point": f"{side} point",
                "evidence_refs": [evidence_ref],
                "clauses": [clause],
            }],
            "weaknesses_acknowledged": [],
        })
    return chat


def _post(dispute_id: str, chat, **body) -> list[dict]:
    with patch("agents.advocates.chat", side_effect=chat), \
         patch("agents.judge.chat", side_effect=chat):
        resp = client.post(
            "/api/disputes/resolve",
            json={"dispute_ticket": {"dispute_id": dispute_id}, **body},
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(raw) for raw in resp.iter_lines() if raw]


def test_disp002_real_flow_stream():
    lines = _post("DISP-002", _fake_chat("no_show_check.total_wait_min", "NS-1.4"))
    types = [line["type"] for line in lines]

    evidence = [l["data"]["tool"] for l in lines if l["type"] == "evidence_data"]
    assert evidence == ["history_lookup", "safety_check", "no_show_check"]
    assert sorted(l["data"]["side"] for l in lines if l["type"] == "brief_data") == ["driver", "rider"]
    assert {l["agent"] for l in lines if l["type"] == "argument"} == {"rider_advocate", "driver_advocate"}

    assert types[-1] == "ruling_data"
    ruling = lines[-1]["data"]
    assert ruling["outcome"] == "charge_upheld"
    assert ruling["amount_sgd"] == 5.0
    assert ruling["dispute_id"] == "DISP-002"

    seqs = [l["seq"] for l in lines if "seq" in l]
    assert seqs == list(range(1, len(seqs) + 1))


def test_tc08_safety_routed_to_human_review():
    lines = _post("TC-08", _fake_chat("safety_check.keyword_hits", "S-1.1"))
    ruling = next(l["data"] for l in lines if l["type"] == "ruling_data")
    assert ruling["outcome"] == "escalate"
    assert ruling["escalated"] is True
    assert lines[-1]["content"] == "Routed to the human review queue."


def test_tc05_judge_findings_decide_refund():
    chat = _fake_chat(
        "route_deviation.deviation_pct", "RD-2.6",
        judge_findings={"rider_requested_detour": False, "traffic_justified": False},
    )
    ruling = _post("TC-05", chat)[-1]["data"]
    assert (ruling["outcome"], ruling["amount_sgd"]) == ("refund", 1.07)


def test_driver_first_reaches_the_judge():
    seen: list = []
    _post("DISP-002", _fake_chat("no_show_check.total_wait_min", "NS-1.4", seen=seen),
          driver_first=True)
    judge_msg = json.loads(next(msg for agent, msg in seen if agent == "judge"))
    keys = list(judge_msg)
    assert keys.index("driver_brief") < keys.index("rider_brief")


def test_llm_failure_streams_error_line():
    async def failing_chat(agent, system_prompt, user_message, **kwargs):
        raise LLMError("App key invalid")

    lines = _post("DISP-002", failing_chat)
    assert lines[-1] == {"type": "error", "content": "App key invalid"}
    assert not any(l["type"] == "ruling_data" for l in lines)
