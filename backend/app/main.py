"""FastAPI app for the Ryde Dispute Resolution system.

This module exposes a stub streaming endpoint (POST /api/disputes/resolve)
so the frontend can integrate before the real LangGraph agents exist. The
mocked agent messages will be replaced by the real agent flow later.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from schemas import AdvocateBrief, AgentLogMessage, Argument, DisputeCase, EvidenceOutput, Ruling
from tools.history_lookup import history_lookup
from tools.no_show_check import compute_no_show_outcome, no_show_check
from tools.route_deviation import compute_route_deviation_outcome, route_deviation

app = FastAPI(title="Ryde Dispute Resolution")

# CORS: allow all origins for local dev only.
# TODO: tighten to the frontend origin before production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data directory -- same resolution as backend/tests/test_tools.py
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_TC_DIR = _DATA_DIR / "test_cases"
_MOCK_AGENT_LOG_PATH = Path(__file__).resolve().parents[2] / "frontend" / "mock_agent_log.json"

_TC_PREFIX_RE = re.compile(r"^(TC-\d+)")


# ---------- Request model ----------


class DisputeTicketRequest(BaseModel):
    """Lightweight dispute-ticket model: only dispute_id is required.

    Other fields are accepted but ignored. We deliberately do NOT validate
    against schemas.DisputeTicket because it requires filed_at and status
    which the frontend does not send.
    """

    dispute_id: str
    trip_id: str | None = None
    filed_by: str | None = None
    dispute_type: str | None = None
    description: str | None = None


class ResolveRequest(BaseModel):
    """Top-level request body: {"dispute_ticket": {"dispute_id": "..."}}."""

    dispute_ticket: DisputeTicketRequest


# ---------- Case lookup ----------


def _load_case_index() -> dict[str, DisputeCase]:
    """Build a lookup index at startup: dispute_id -> DisputeCase.

    Scans data/*.json (skipping *.expected.json) and
    data/test_cases/TC-*.json. Each case is keyed by its
    dispute_ticket.dispute_id; test cases are also keyed by their
    filename prefix (TC-01 ... TC-10).

    When a test case shares a dispute_id with a real data file
    (e.g. TC-01 has DISP-002), the real data file wins.
    """
    index: dict[str, DisputeCase] = {}

    # First: test cases (lower priority, loaded first so real data overrides)
    if _TC_DIR.is_dir():
        for path in sorted(_TC_DIR.glob("TC-*.json")):
            m = _TC_PREFIX_RE.match(path.name)
            if m is None:
                continue
            tc_key = m.group(1)  # e.g. "TC-01"
            case = DisputeCase.model_validate_json(path.read_text())
            index[tc_key] = case
            dispute_id = case.dispute_ticket.dispute_id
            if dispute_id not in index:
                index[dispute_id] = case

    # Then: real data files (higher priority -- overwrites TC duplicates)
    for path in sorted(_DATA_DIR.glob("*.json")):
        if path.name.endswith(".expected.json"):
            continue
        case = DisputeCase.model_validate_json(path.read_text())
        index[case.dispute_ticket.dispute_id] = case

    return index


_CASE_INDEX: dict[str, DisputeCase] = _load_case_index()


def _lookup_case(dispute_id: str) -> DisputeCase:
    """Return the DisputeCase for *dispute_id* or raise 404."""
    case = _CASE_INDEX.get(dispute_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Unknown dispute_id: {dispute_id}")
    return case


# ---------- Mock agent log ----------


def _load_mock_agent_log() -> list[dict[str, Any]]:
    if _MOCK_AGENT_LOG_PATH.is_file():
        return json.loads(_MOCK_AGENT_LOG_PATH.read_text())
    return []


_MOCK_AGENT_LOG: list[dict[str, Any]] = _load_mock_agent_log()


# ---------- Helpers ----------


def _now_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _evidence_summary(evidence: EvidenceOutput) -> str:
    """One-line summary of an EvidenceOutput for the agent log."""
    facts = evidence.facts
    parts: list[str] = []
    for key in sorted(facts):
        val = facts[key]
        if isinstance(val, (list, dict)):
            if isinstance(val, list):
                val_str = f"[{len(val)} items]"
            else:
                val_str = "{...}"
        else:
            val_str = str(val)
        parts.append(f"{key}={val_str}")
    return f"{evidence.tool}: " + ", ".join(parts)


def _build_advocate_brief(
    dispute_id: str,
    side: str,
    evidence: list[EvidenceOutput],
) -> AdvocateBrief:
    """Build a minimal valid AdvocateBrief with placeholder text."""
    tool_refs = [e.tool for e in evidence]
    brief = AdvocateBrief(
        dispute_id=dispute_id,
        side=side,
        position=f"[stub] {side.capitalize()} advocate position placeholder",
        arguments=[
            Argument(
                point=f"[stub] Placeholder argument for {side} advocate. "
                f"Evidence gathered: {', '.join(tool_refs)}.",
                evidence_refs=tool_refs if tool_refs else ["history_lookup"],
                clauses=["NS-1.6"] if side == "driver" else ["NS-1.7"],
            ),
        ],
        weaknesses_acknowledged=["[stub] Placeholder weakness"],
    )
    return brief


def _build_ruling(
    dispute_id: str,
    outcome: str,
    amount_sgd: float,
    clauses_cited: list[str],
    conduct_flag: bool,
    missing_evidence: list[str],
) -> Ruling:
    """Build a Ruling from the real outcome formula output."""
    escalated = outcome == "escalate"
    confidence = 0.5 if escalated else 0.9
    escalation_reason = None
    if escalated:
        if missing_evidence:
            escalation_reason = "Missing evidence: " + ", ".join(missing_evidence)
        else:
            escalation_reason = "[stub] Escalation required"
    ruling = Ruling(
        dispute_id=dispute_id,
        outcome=outcome,
        amount_sgd=amount_sgd,
        confidence=confidence,
        clauses_cited=clauses_cited,
        explanation_rider="[stub] Placeholder explanation for rider.",
        explanation_driver="[stub] Placeholder explanation for driver.",
        conduct_flag=conduct_flag,
        escalated=escalated,
        escalation_reason=escalation_reason,
    )
    return ruling


# ---------- Streaming endpoint ----------


@app.post("/api/disputes/resolve")
async def resolve_dispute(req: ResolveRequest):
    """Stream agent log messages and structured data as ND-JSON.

    STUB -- The mock agent messages and briefs will be replaced by the
    real LangGraph agent flow. The evidence tools and outcome formula are
    already real.
    """
    case = _lookup_case(req.dispute_ticket.dispute_id)

    async def stream():
        seq = 0
        try:
            # --- Step 1: Real evidence ---
            evidence_outputs: list[EvidenceOutput] = []

            history = history_lookup(case)
            evidence_outputs.append(history)
            seq += 1
            yield json.dumps(AgentLogMessage(
                seq=seq,
                agent="system",
                type="evidence",
                content=_evidence_summary(history),
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json")) + "\n"
            await asyncio.sleep(0.4)

            yield json.dumps({
                "type": "evidence_data",
                "data": history.model_dump(mode="json"),
            }) + "\n"
            await asyncio.sleep(0.4)

            dispute_type = case.dispute_ticket.dispute_type
            if dispute_type == "no_show_charge":
                tool_evidence = no_show_check(case)
            elif dispute_type == "route_deviation":
                tool_evidence = route_deviation(case)
            else:
                tool_evidence = None

            if tool_evidence is not None:
                evidence_outputs.append(tool_evidence)
                seq += 1
                yield json.dumps(AgentLogMessage(
                    seq=seq,
                    agent="system",
                    type="evidence",
                    content=_evidence_summary(tool_evidence),
                    timestamp=datetime.now(timezone.utc),
                ).model_dump(mode="json")) + "\n"
                await asyncio.sleep(0.4)

                yield json.dumps({
                    "type": "evidence_data",
                    "data": tool_evidence.model_dump(mode="json"),
                }) + "\n"
                await asyncio.sleep(0.4)

            # --- Step 2: Mock agent messages (skip system entries) ---
            for entry in _MOCK_AGENT_LOG:
                if entry.get("agent") == "system":
                    continue
                seq += 1
                entry_out = {
                    "seq": seq,
                    "agent": entry["agent"],
                    "type": entry["type"],
                    "content": entry["content"],
                    "timestamp": _now_iso(),
                }
                yield json.dumps(entry_out) + "\n"
                await asyncio.sleep(0.4)

            # --- Step 3: Mock briefs ---
            for side in ("rider", "driver"):
                brief = _build_advocate_brief(
                    dispute_id=case.dispute_ticket.dispute_id,
                    side=side,
                    evidence=evidence_outputs,
                )
                yield json.dumps({
                    "type": "brief_data",
                    "data": brief.model_dump(mode="json"),
                }) + "\n"
                await asyncio.sleep(0.4)

            # --- Step 4: Ruling from real outcome formula ---
            if dispute_type == "no_show_charge":
                facts = no_show_check(case).facts
                outcome, amount, clauses, conduct = compute_no_show_outcome(facts)
                missing = facts.get("missing_evidence", [])
            else:
                facts = route_deviation(case).facts
                outcome, amount, clauses, conduct = compute_route_deviation_outcome(facts)
                missing = facts.get("missing_evidence", [])

            ruling = _build_ruling(
                dispute_id=case.dispute_ticket.dispute_id,
                outcome=outcome,
                amount_sgd=amount,
                clauses_cited=clauses,
                conduct_flag=conduct,
                missing_evidence=missing,
            )
            yield json.dumps({
                "type": "ruling_data",
                "data": ruling.model_dump(mode="json"),
            }) + "\n"
            await asyncio.sleep(0.4)

        except Exception as e:
            yield json.dumps({"type": "error", "content": str(e)}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.get("/health")
def health():
    return {"status": "ok"}
