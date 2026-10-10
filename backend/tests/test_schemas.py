import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import AdvocateBrief, DisputeCase, EvidenceOutput, Ruling

DATA = Path(__file__).resolve().parents[2] / "data"


def test_disp_002_parses():
    case = DisputeCase.model_validate_json((DATA / "DISP-002.json").read_text())
    assert case.dispute_ticket.dispute_type == "no_show_charge"
    assert case.cancellation_policy.no_show_threshold_min == 8
    assert len(case.chat_logs) == 6


def test_schemas_md_examples_validate():
    EvidenceOutput.model_validate(
        {
            "dispute_id": "DISP-002",
            "tool": "no_show_check",
            "facts": {
                "driver_distance_from_pickup_m": 0,
                "arrived": True,
                "arrived_minutes_vs_scheduled": -2,
                "total_wait_min": 8,
                "free_wait_expired": True,
                "no_show_threshold_reached": True,
                "contact_attempts": 5,
                "rider_replies": 0,
                "missing_evidence": [],
            },
            "flags": [],
        }
    )
    AdvocateBrief.model_validate(
        {
            "dispute_id": "DISP-002",
            "side": "driver",
            "position": "Uphold the fee.",
            "arguments": [
                {"point": "Waited 8 min.", "evidence_refs": ["no_show_check.total_wait_min"], "clauses": ["NS-1.6"]}
            ],
        }
    )
    Ruling.model_validate(
        {
            "dispute_id": "DISP-002",
            "outcome": "charge_upheld",
            "amount_sgd": 0.0,
            "confidence": 0.92,
            "clauses_cited": ["NS-1.6"],
            "explanation_rider": "...",
            "explanation_driver": "...",
            "conduct_flag": False,
        }
    )


def test_ruling_rejects_bad_confidence_and_unexplained_escalation():
    base = {
        "dispute_id": "X",
        "outcome": "escalate",
        "amount_sgd": 0,
        "confidence": 0.4,
        "clauses_cited": [],
        "explanation_rider": "",
        "explanation_driver": "",
        "conduct_flag": False,
        "escalated": True,
    }
    with pytest.raises(ValidationError):
        Ruling.model_validate(base)  # missing escalation_reason
    with pytest.raises(ValidationError):
        Ruling.model_validate({**base, "escalation_reason": "low confidence", "confidence": 1.5})


def test_brief_rejects_uncited_argument():
    with pytest.raises(ValidationError):
        AdvocateBrief.model_validate(
            {
                "dispute_id": "X",
                "side": "rider",
                "position": "Refund me.",
                "arguments": [{"point": "Unfair.", "evidence_refs": [], "clauses": []}],
            }
        )
