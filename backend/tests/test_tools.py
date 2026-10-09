"""Tests for no_show_check() and history_lookup() against DISP-002."""

import copy
from pathlib import Path

from schemas import DisputeCase, EvidenceOutput
from tools.history_lookup import history_lookup
from tools.no_show_check import no_show_check

DATA = Path(__file__).resolve().parents[2] / "data"


def _load_disp_002() -> DisputeCase:
    return DisputeCase.model_validate_json((DATA / "DISP-002.json").read_text())


# ---------- no_show_check: DISP-002 happy path ----------


def test_no_show_check_returns_evidence_output():
    result = no_show_check(_load_disp_002())
    assert isinstance(result, EvidenceOutput)
    assert result.tool == "no_show_check"
    assert result.dispute_id == "DISP-002"


def test_no_show_check_driver_distance():
    facts = no_show_check(_load_disp_002()).facts
    assert facts["driver_distance_from_pickup_m"] == 0.0
    assert facts["driver_within_arrival_radius"] is True


def test_no_show_check_arrival_vs_scheduled():
    facts = no_show_check(_load_disp_002()).facts
    assert facts["arrived_minutes_vs_scheduled"] == -2.0


def test_no_show_check_total_wait():
    facts = no_show_check(_load_disp_002()).facts
    assert facts["total_wait_min"] == 8.0


def test_no_show_check_gates_passed():
    facts = no_show_check(_load_disp_002()).facts
    assert facts["free_wait_expired"] is True
    assert facts["no_show_threshold_reached"] is True


def test_no_show_check_contact():
    facts = no_show_check(_load_disp_002()).facts
    assert facts["contact_attempts"] == 5
    assert facts["rider_replies"] == 0


def test_no_show_check_no_missing_evidence():
    facts = no_show_check(_load_disp_002()).facts
    assert facts["missing_evidence"] == []


def test_no_show_check_no_flags():
    result = no_show_check(_load_disp_002())
    assert result.flags == []


# ---------- no_show_check: failure paths ----------


def _clone_case() -> DisputeCase:
    """Return a mutable deep copy of DISP-002 as a dict."""
    raw = DisputeCase.model_validate_json((DATA / "DISP-002.json").read_text())
    return raw.model_dump()


def _run_on_clone(mutator) -> EvidenceOutput:
    case_dict = _clone_case()
    mutator(case_dict)
    return no_show_check(DisputeCase.model_validate(case_dict))


def test_driver_cancelled_during_free_wait():
    # Wait only 3 minutes, which is below the 5-minute free wait threshold.
    def mutate(d):
        d["trip_data"]["cancellation_time"] = "2026-09-13T08:46:00+08:00"
        d["trip_data"]["cancellation_reason"] = "rider_no_show"

    result = _run_on_clone(mutate)
    assert result.facts["total_wait_min"] == 3.0
    assert result.facts["free_wait_expired"] is False
    assert result.facts["no_show_threshold_reached"] is False


def test_driver_400m_away_from_pickup():
    def mutate(d):
        # Move the arrived/waiting GPS points far away.
        for p in d["gps_telemetry"]:
            if p["status"] in ("arrived", "waiting"):
                p["lat"] = 1.2880
                p["lng"] = 103.8420

    result = _run_on_clone(mutate)
    assert result.facts["driver_distance_from_pickup_m"] > 10
    assert result.facts["driver_within_arrival_radius"] is False
    assert "NS-1.1" not in result.flags  # not a flag, surfaced as a fact


def test_no_contact_attempts():
    def mutate(d):
        # Remove all driver messages/calls from the waiting period.
        d["chat_logs"] = [
            c for c in d["chat_logs"]
            if not (c["sender"] == "driver" and c["type"] in ("message", "call"))
        ]
        d["app_events"] = [
            e for e in d["app_events"] if e["event_type"] != "driver_called_rider"
        ]

    result = _run_on_clone(mutate)
    assert result.facts["contact_attempts"] == 0
    assert result.facts["rider_replies"] == 0


def test_rider_reply_during_wait_counts():
    def mutate(d):
        d["chat_logs"].insert(
            -1,
            {
                "timestamp": "2026-09-13T08:47:00+08:00",
                "sender": "rider",
                "type": "message",
                "content": "Coming down now",
            },
        )

    result = _run_on_clone(mutate)
    assert result.facts["rider_replies"] == 1
    assert result.facts["contact_attempts"] == 5  # driver attempts unchanged


def test_messages_outside_wait_period_ignored():
    def mutate(d):
        # Add a driver message after cancellation — should not count.
        d["chat_logs"].insert(
            -1,
            {
                "timestamp": "2026-09-13T08:52:00+08:00",
                "sender": "driver",
                "type": "message",
                "content": "Sorry I missed you",
            },
        )

    result = _run_on_clone(mutate)
    assert result.facts["contact_attempts"] == 5


# ---------- history_lookup ----------


def test_history_lookup_returns_evidence_output():
    result = history_lookup(_load_disp_002())
    assert isinstance(result, EvidenceOutput)
    assert result.tool == "history_lookup"
    assert result.dispute_id == "DISP-002"


def test_history_lookup_rider_summary():
    rider = history_lookup(_load_disp_002()).facts["rider"]
    assert rider["avg_rating"] == 3.9
    assert rider["total_trips"] == 34
    assert rider["account_age_days"] == 210
    assert rider["dispute_history"] == {
        "total_disputes": 4,
        "upheld": 1,
        "rejected": 3,
    }
    assert rider["fraud_flags"] == 1
    assert rider["fraud_flag_details"] == "flagged_for_frequent_late_cancellations"


def test_history_lookup_driver_summary():
    driver = history_lookup(_load_disp_002()).facts["driver"]
    assert driver["avg_rating"] == 4.9
    assert driver["total_trips"] == 3201
    assert driver["account_age_days"] == 900
    assert driver["dispute_history"] == {
        "total_disputes": 1,
        "upheld_against": 0,
        "rejected": 1,
    }
    assert driver["fraud_flags"] == 0
    assert driver["fraud_flag_details"] is None


def test_history_lookup_rider_fraud_flag():
    result = history_lookup(_load_disp_002())
    assert "RIDER_FRAUD_FLAG" in result.flags
    assert "DRIVER_FRAUD_FLAG" not in result.flags
