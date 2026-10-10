"""Shared context-building utilities for the LLM agents.

Provides:
- ``load_policy_clauses()`` — parse the policy doc into {clause_id: text}.
- ``relevant_clauses(dispute_type)`` — return clauses relevant to a dispute.
- ``case_summary(case)`` — whitelist safe fields from a DisputeCase.
- ``gather_evidence(case)`` — run the real evidence tools.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from schemas import DisputeCase, EvidenceOutput
from tools.history_lookup import history_lookup
from tools.no_show_check import no_show_check
from tools.route_deviation import route_deviation

_POLICY_DOC_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "ryde_dispute_policy.md"
)

# Heading regex: ### <ID> — <title>  or  ### <ID> - <title>
_HEADING_RE = re.compile(r"^###\s+([A-Z]+-\d+\.\d+)\s*[—–-]\s*(.+)$")

# Whitelisted dispute_ticket fields for case_summary.
_TICKET_WHITELIST = ("dispute_id", "dispute_type", "filed_by", "description")


# ---------- Policy clause parsing ----------

_POLICY_CLAUSES: dict[str, str] | None = None


def load_policy_clauses() -> dict[str, str]:
    """Parse the policy doc once into ``{clause_id: section_text}``.

    Each ``### <ID> — <title>`` heading starts a section.  The section
    text runs from the line after the heading up to (but not including)
    the next heading of the same or higher level (``##`` or ``###``).
    """
    global _POLICY_CLAUSES
    if _POLICY_CLAUSES is not None:
        return _POLICY_CLAUSES

    text = _POLICY_DOC_PATH.read_text()
    lines = text.splitlines()

    clauses: dict[str, str] = {}
    current_id: str | None = None
    current_lines: list[str] = []

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            # Flush the previous section.
            if current_id is not None:
                clauses[current_id] = "\n".join(current_lines).strip()
            current_id = m.group(1)
            current_lines = [line]
        elif current_id is not None:
            # Stop at a ## heading (new top-level section).
            if line.startswith("## "):
                clauses[current_id] = "\n".join(current_lines).strip()
                current_id = None
                current_lines = []
            else:
                current_lines.append(line)

    # Flush the last section.
    if current_id is not None:
        clauses[current_id] = "\n".join(current_lines).strip()

    _POLICY_CLAUSES = clauses
    return _POLICY_CLAUSES


def relevant_clauses(dispute_type: str) -> dict[str, str]:
    """Return clauses relevant to *dispute_type*.

    For ``no_show_charge``: all ``NS-*`` clauses.
    For ``route_deviation``: all ``RD-*`` clauses.
    Always includes all ``E-*`` and ``S-*`` clauses.
    """
    all_clauses = load_policy_clauses()
    prefix = "NS-" if dispute_type == "no_show_charge" else "RD-"
    return {
        cid: text
        for cid, text in all_clauses.items()
        if cid.startswith(prefix) or cid.startswith("E-") or cid.startswith("S-")
    }


# ---------- Case summary (safe whitelist) ----------


def case_summary(case: DisputeCase) -> dict[str, Any]:
    """Return a safe subset of *case* for the LLM prompt.

    Only includes: dispute_ticket (id, type, filed_by, description),
    trip_data, chat_logs, app_events.  Never includes test_case_id,
    test_case_description, data_label, gps_telemetry, or anything else.
    """
    ticket = {
        k: case.dispute_ticket.model_dump().get(k)
        for k in _TICKET_WHITELIST
    }

    return {
        "dispute_ticket": ticket,
        "trip_data": case.trip_data.model_dump(mode="json"),
        "chat_logs": [c.model_dump(mode="json") for c in case.chat_logs],
        "app_events": [e.model_dump(mode="json") for e in case.app_events],
    }


# ---------- Evidence gathering ----------


def gather_evidence(case: DisputeCase) -> list[EvidenceOutput]:
    """Run all relevant evidence tools for *case*.

    Always runs ``history_lookup``.  Then runs ``no_show_check`` or
    ``route_deviation`` depending on the dispute type.
    """
    evidence: list[EvidenceOutput] = [history_lookup(case)]

    dt = case.dispute_ticket.dispute_type
    if dt == "no_show_charge":
        evidence.append(no_show_check(case))
    elif dt == "route_deviation":
        evidence.append(route_deviation(case))

    return evidence
