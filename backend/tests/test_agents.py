"""Tests for the three LLM agents (no real network calls).

Patches ``agents.llm.chat`` to return canned JSON for the advocate and
judge agents.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agents.advocates import run_advocate, _build_user_message
from agents.context import case_summary, gather_evidence, relevant_clauses
from agents.judge import run_judge, JudgeDecision
from agents.llm import LLMError, LLMResult
from agents.pipeline import resolve_case
from app.main import _CASE_INDEX
from schemas import DisputeCase

# ---------- Helpers ----------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TC_DIR = _REPO_ROOT / "data" / "test_cases"


def _load_tc(tc_id: str) -> DisputeCase:
    """Load a test case by TC prefix."""
    case = _CASE_INDEX.get(tc_id)
    assert case is not None, f"Unknown TC: {tc_id}"
    return case


def _llm_result(text: str) -> LLMResult:
    """Create a canned LLMResult."""
    return LLMResult(
        text=text,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        cached=False,
    )


def _make_advocate_json(
    side: str, dispute_id: str, evidence_refs: list[str], clauses: list[str],
    bad_clause: str | None = None,
) -> str:
    """Build a canned AdvocateBrief JSON reply."""
    if bad_clause:
        clauses = [bad_clause] + clauses
    return json.dumps({
        "dispute_id": dispute_id,
        "side": side,
        "position": f"The {side} has a valid position based on evidence.",
        "arguments": [
            {
                "point": f"Evidence shows the {side}'s case is strong.",
                "evidence_refs": evidence_refs,
                "clauses": clauses,
            },
        ],
        "weaknesses_acknowledged": ["Some weakness in the case."],
    })


def _make_judge_json(
    rider_requested_detour: bool | None,
    traffic_justified: bool | None,
    confidence: float,
    clauses: list[str],
) -> str:
    """Build a canned JudgeDecision JSON reply."""
    return json.dumps({
        "rider_requested_detour": rider_requested_detour,
        "traffic_justified": traffic_justified,
        "confidence": confidence,
        "clauses_cited": clauses,
        "explanation_rider": "Explanation for the rider.",
        "explanation_driver": "Explanation for the driver.",
    })


# ---------- 1. case_summary whitelist ----------


def test_case_summary_excludes_test_fields():
    """case_summary of a TC file contains no test_case_description,
    test_case_id, gps_telemetry, or data_label."""
    case = _load_tc("TC-05")
    summary = case_summary(case)

    assert "test_case_description" not in summary
    assert "test_case_id" not in summary
    assert "data_label" not in summary
    assert "gps_telemetry" not in summary
    assert "rider_profile" not in summary
    assert "driver_profile" not in summary
    assert "cancellation_policy" not in summary

    # Whitelisted fields are present.
    assert "dispute_ticket" in summary
    assert "trip_data" in summary
    assert "chat_logs" in summary
    assert "app_events" in summary

    # dispute_ticket has only the whitelisted fields.
    ticket = summary["dispute_ticket"]
    assert set(ticket.keys()) == {
        "dispute_id", "dispute_type", "filed_by", "description"
    }
    assert ticket["dispute_id"] == "DISP-001-T5"


# ---------- 2. Both advocates receive identical user messages ----------


@pytest.mark.asyncio
async def test_both_advocates_receive_identical_user_messages():
    """Both advocates receive exactly the same user message."""
    case = _load_tc("TC-05")
    evidence = gather_evidence(case)
    clauses = relevant_clauses(case.dispute_ticket.dispute_type)

    captured_messages: list[str] = []

    async def _mock_chat(agent, system_prompt, user_message, **kwargs):
        captured_messages.append(user_message)
        side = "rider" if "rider" in agent else "driver"
        return _llm_result(_make_advocate_json(
            side=side,
            dispute_id=case.dispute_ticket.dispute_id,
            evidence_refs=["route_deviation.deviation_pct"],
            clauses=["RD-2.6"],
        ))

    with patch("agents.advocates.chat", side_effect=_mock_chat):
        await run_advocate("rider", case, evidence, clauses)
        await run_advocate("driver", case, evidence, clauses)

    assert len(captured_messages) == 2
    assert captured_messages[0] == captured_messages[1]


# ---------- 3. Unknown clause triggers one retry, then succeeds ----------


@pytest.mark.asyncio
async def test_advocate_retry_on_unknown_clause():
    """An advocate reply citing an unknown clause triggers one retry,
    then succeeds."""
    case = _load_tc("TC-05")
    evidence = gather_evidence(case)
    clauses = relevant_clauses(case.dispute_ticket.dispute_type)

    call_count = 0

    async def _mock_chat(agent, system_prompt, user_message, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: cite an unknown clause.
            return _llm_result(_make_advocate_json(
                side="rider",
                dispute_id=case.dispute_ticket.dispute_id,
                evidence_refs=["route_deviation.deviation_pct"],
                clauses=["RD-2.6"],
                bad_clause="FAKE-9.9",
            ))
        # Second call: valid.
        return _llm_result(_make_advocate_json(
            side="rider",
            dispute_id=case.dispute_ticket.dispute_id,
            evidence_refs=["route_deviation.deviation_pct"],
            clauses=["RD-2.6"],
        ))

    with patch("agents.advocates.chat", side_effect=_mock_chat):
        brief = await run_advocate("rider", case, evidence, clauses)

    assert call_count == 2
    assert brief.side == "rider"
    assert brief.arguments[0].clauses == ["RD-2.6"]


# ---------- 4a. TC-06: rider_requested_detour=True → no_action / RD-2.3 ----------


@pytest.mark.asyncio
async def test_judge_tc06_rider_detour_no_action():
    """Judge findings rider_requested_detour=True on TC-06 give no_action /
    RD-2.3."""
    case = _load_tc("TC-06")
    evidence = gather_evidence(case)
    clauses = relevant_clauses(case.dispute_ticket.dispute_type)

    # Build canned briefs.
    from schemas import AdvocateBrief, Argument
    rider_brief = AdvocateBrief(
        dispute_id=case.dispute_ticket.dispute_id,
        side="rider",
        position="Rider position.",
        arguments=[Argument(
            point="The driver deviated.",
            evidence_refs=["route_deviation.deviation_pct"],
            clauses=["RD-2.3"],
        )],
    )
    driver_brief = AdvocateBrief(
        dispute_id=case.dispute_ticket.dispute_id,
        side="driver",
        position="Driver position.",
        arguments=[Argument(
            point="Rider requested the route.",
            evidence_refs=["route_deviation.rider_requested_detour"],
            clauses=["RD-2.3"],
        )],
    )

    async def _mock_chat(agent, system_prompt, user_message, **kwargs):
        return _llm_result(_make_judge_json(
            rider_requested_detour=True,
            traffic_justified=False,
            confidence=0.9,
            clauses=["RD-2.3"],
        ))

    with patch("agents.judge.chat", side_effect=_mock_chat):
        ruling = await run_judge(case, evidence, clauses, rider_brief, driver_brief)

    assert ruling.outcome == "no_action"
    assert ruling.amount_sgd == 0.0
    assert "RD-2.3" in ruling.clauses_cited
    assert not ruling.escalated


# ---------- 4b. TC-05: rider_requested_detour=False, traffic_justified=False → refund / 1.07 ----------


@pytest.mark.asyncio
async def test_judge_tc05_refund():
    """Judge findings rider_requested_detour=False with
    traffic_justified=False on TC-05 gives refund / 1.07."""
    case = _load_tc("TC-05")
    evidence = gather_evidence(case)
    clauses = relevant_clauses(case.dispute_ticket.dispute_type)

    from schemas import AdvocateBrief, Argument
    rider_brief = AdvocateBrief(
        dispute_id=case.dispute_ticket.dispute_id,
        side="rider",
        position="Rider was overcharged.",
        arguments=[Argument(
            point="The route deviated by over 40%.",
            evidence_refs=["route_deviation.deviation_pct"],
            clauses=["RD-2.6"],
        )],
    )
    driver_brief = AdvocateBrief(
        dispute_id=case.dispute_ticket.dispute_id,
        side="driver",
        position="Driver took a reasonable route.",
        arguments=[Argument(
            point="The route was necessary.",
            evidence_refs=["route_deviation.actual_distance_km"],
            clauses=["RD-2.4"],
        )],
    )

    async def _mock_chat(agent, system_prompt, user_message, **kwargs):
        return _llm_result(_make_judge_json(
            rider_requested_detour=False,
            traffic_justified=False,
            confidence=0.9,
            clauses=["RD-2.6"],
        ))

    with patch("agents.judge.chat", side_effect=_mock_chat):
        ruling = await run_judge(case, evidence, clauses, rider_brief, driver_brief)

    assert ruling.outcome == "refund"
    assert ruling.amount_sgd == pytest.approx(1.07, abs=0.01)
    assert "RD-2.6" in ruling.clauses_cited
    assert not ruling.escalated


# ---------- 5. Confidence 0.5 forces escalate ----------


@pytest.mark.asyncio
async def test_low_confidence_forces_escalate():
    """Confidence 0.5 forces escalate."""
    case = _load_tc("TC-05")
    evidence = gather_evidence(case)
    clauses = relevant_clauses(case.dispute_ticket.dispute_type)

    from schemas import AdvocateBrief, Argument
    rider_brief = AdvocateBrief(
        dispute_id=case.dispute_ticket.dispute_id,
        side="rider",
        position="Rider position.",
        arguments=[Argument(
            point="The driver deviated.",
            evidence_refs=["route_deviation.deviation_pct"],
            clauses=["RD-2.6"],
        )],
    )
    driver_brief = AdvocateBrief(
        dispute_id=case.dispute_ticket.dispute_id,
        side="driver",
        position="Driver position.",
        arguments=[Argument(
            point="No deviation.",
            evidence_refs=["route_deviation.actual_distance_km"],
            clauses=["RD-2.4"],
        )],
    )

    async def _mock_chat(agent, system_prompt, user_message, **kwargs):
        return _llm_result(_make_judge_json(
            rider_requested_detour=False,
            traffic_justified=False,
            confidence=0.5,
            clauses=["RD-2.6"],
        ))

    with patch("agents.judge.chat", side_effect=_mock_chat):
        ruling = await run_judge(case, evidence, clauses, rider_brief, driver_brief)

    assert ruling.outcome == "escalate"
    assert ruling.amount_sgd == 0.0
    assert ruling.escalated is True
    assert "Low confidence" in (ruling.escalation_reason or "")


# ---------- 6. TC-11 gives escalate with RD-2.7 ----------


@pytest.mark.asyncio
async def test_tc11_missing_gps_escalate():
    """TC-11 gives escalate with RD-2.7 (missing GPS evidence)."""
    case = _load_tc("TC-11")
    evidence = gather_evidence(case)
    clauses = relevant_clauses(case.dispute_ticket.dispute_type)

    from schemas import AdvocateBrief, Argument
    rider_brief = AdvocateBrief(
        dispute_id=case.dispute_ticket.dispute_id,
        side="rider",
        position="Rider position.",
        arguments=[Argument(
            point="The route was longer than expected.",
            evidence_refs=["route_deviation.baseline_distance_km"],
            clauses=["RD-2.7"],
        )],
    )
    driver_brief = AdvocateBrief(
        dispute_id=case.dispute_ticket.dispute_id,
        side="driver",
        position="Driver position.",
        arguments=[Argument(
            point="GPS data was incomplete.",
            evidence_refs=["route_deviation.missing_evidence"],
            clauses=["E-1.5"],
        )],
    )

    async def _mock_chat(agent, system_prompt, user_message, **kwargs):
        return _llm_result(_make_judge_json(
            rider_requested_detour=False,
            traffic_justified=False,
            confidence=0.9,
            clauses=["RD-2.7", "E-1.5"],
        ))

    with patch("agents.judge.chat", side_effect=_mock_chat):
        ruling = await run_judge(case, evidence, clauses, rider_brief, driver_brief)

    assert ruling.outcome == "escalate"
    assert ruling.amount_sgd == 0.0
    assert ruling.escalated is True
    assert "RD-2.7" in ruling.clauses_cited
    assert "E-1.5" in ruling.clauses_cited
    assert "Missing evidence" in (ruling.escalation_reason or "")
