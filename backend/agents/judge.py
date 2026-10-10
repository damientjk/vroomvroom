"""Judge agent.

The Judge LLM never decides the outcome or amount. For route_deviation
it decides only two findings (rider_requested_detour, traffic_justified).
For no_show_charge it decides nothing — the precomputed outcome is given.

The Ruling is built in code from the formula output + the Judge's
confidence, clauses, and explanations.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.context import case_summary
from agents.llm import LLMError, chat, parse_model_reply
from app.policy_constants import SPOT_CHECK_THRESHOLD
from schemas import AdvocateBrief, DisputeCase, EvidenceOutput, Ruling
from tools.no_show_check import compute_no_show_outcome
from tools.route_deviation import compute_route_deviation_outcome


class JudgeDecision(BaseModel):
    """Strict Pydantic model for the Judge LLM's reply."""

    model_config = ConfigDict(extra="forbid")

    rider_requested_detour: bool | None = None
    traffic_justified: bool | None = None
    confidence: float = Field(ge=0, le=1)
    clauses_cited: list[str] = Field(min_length=1)
    explanation_rider: str
    explanation_driver: str


_SYSTEM_PROMPT = """\
You are the Judge in a Ryde ride-hailing dispute resolution system.

You must cite at least one clause ID from the policy in \
`clauses_cited`.

You must not let rider/driver ratings, dispute history, or fraud flags \
override the trip evidence in determining the outcome.

The outcome and amount are provided to you by the code. You do not \
compute them. You explain them.

If a safety incident is flagged, you must set `escalated: true` and \
`outcome: escalate`. (This is handled by code; you only provide \
explanations.)

Produce two explanations: `explanation_rider` and `explanation_driver`, \
each in plain language suitable for the respective party.

Weigh both advocates' briefs equally, regardless of order or length \
(E-1.2).

Base your confidence on how complete and clear the evidence is.

The explanations must match the outcome that your findings produce in \
the outcome table provided.

Reply with only JSON matching this schema:

{schema}
"""


def _build_outcome_table(facts: dict[str, Any]) -> str:
    """For route_deviation: compute all 4 combinations of the two booleans.

    Returns a text table showing the outcome for each combination.
    """
    results: list[str] = []
    for rrd in (True, False):
        for tj in (True, False):
            f = dict(facts)
            f["rider_requested_detour"] = rrd
            f["traffic_justified"] = tj
            outcome, amount, clauses, conduct = compute_route_deviation_outcome(f)
            results.append(
                f"  rider_requested_detour={rrd}, traffic_justified={tj} "
                f"-> outcome={outcome}, amount_sgd={amount:.2f}, "
                f"clauses={clauses}, conduct_flag={conduct}"
            )
    return "\n".join(results)


def _build_user_message(
    case: DisputeCase,
    evidence: list[EvidenceOutput],
    clauses: dict[str, str],
    rider_brief: AdvocateBrief,
    driver_brief: AdvocateBrief,
    outcome_table_or_precomputed: str,
) -> str:
    """Build the user message for the Judge."""
    summary = case_summary(case)
    evidence_data = [e.model_dump(mode="json") for e in evidence]
    payload: dict[str, Any] = {
        "case_summary": summary,
        "evidence": evidence_data,
        "relevant_clauses": clauses,
        "rider_brief": rider_brief.model_dump(mode="json"),
        "driver_brief": driver_brief.model_dump(mode="json"),
        "outcome_table": outcome_table_or_precomputed,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_decision(
    decision: JudgeDecision,
    clauses: dict[str, str],
    dispute_type: str,
) -> None:
    """Validate the Judge's clause IDs and findings."""
    for cid in decision.clauses_cited:
        if cid not in clauses:
            raise LLMError(
                f"Invalid clause ID '{cid}': not found in the policy "
                f"clauses provided."
            )

    if dispute_type == "route_deviation":
        if decision.rider_requested_detour is None:
            raise LLMError(
                "rider_requested_detour must be true or false for "
                "route_deviation disputes."
            )
        if decision.traffic_justified is None:
            raise LLMError(
                "traffic_justified must be true or false for "
                "route_deviation disputes."
            )


async def run_judge(
    case: DisputeCase,
    evidence: list[EvidenceOutput],
    clauses: dict[str, str],
    rider_brief: AdvocateBrief,
    driver_brief: AdvocateBrief,
) -> Ruling:
    """Run the Judge agent and return a ``Ruling``.

    The Judge LLM provides confidence, clauses, and explanations.  The
    outcome and amount are computed in code from the formula.
    """
    dispute_id = case.dispute_ticket.dispute_id
    dispute_type = case.dispute_ticket.dispute_type

    # Find the type-specific evidence.
    type_evidence = next(
        (e for e in evidence if e.tool in ("no_show_check", "route_deviation")),
        None,
    )
    if type_evidence is None:
        raise LLMError(
            f"No type-specific evidence found for {dispute_type}."
        )
    facts = type_evidence.facts

    # Build the outcome info for the prompt.
    if dispute_type == "route_deviation":
        outcome_info = (
            "Outcome table (computed by code for each combination of "
            "your two findings):\n"
            + _build_outcome_table(facts)
        )
    else:
        outcome, amount, clause_list, conduct = compute_no_show_outcome(facts)
        outcome_info = (
            f"Precomputed outcome (by code):\n"
            f"  outcome={outcome}, amount_sgd={amount:.2f}, "
            f"clauses={clause_list}, conduct_flag={conduct}"
        )

    system_prompt = _SYSTEM_PROMPT.format(
        schema=json.dumps(
            JudgeDecision.model_json_schema(), ensure_ascii=False, indent=2
        ),
    )
    user_message = _build_user_message(
        case, evidence, clauses, rider_brief, driver_brief, outcome_info,
    )

    last_error: str | None = None
    for attempt in range(2):
        msg = user_message
        if last_error is not None:
            msg = (
                user_message
                + "\n\nYour previous reply had an error:\n"
                + last_error
                + "\nPlease fix the error and reply again with valid JSON."
            )

        result = await chat("judge", system_prompt, msg)
        try:
            decision = parse_model_reply(result.text, JudgeDecision)
            _validate_decision(decision, clauses, dispute_type)
            break
        except LLMError as exc:
            last_error = str(exc)
            if attempt == 1:
                raise
    else:
        raise LLMError("Judge failed after retry.")

    # ---- Build the Ruling in code ----

    if dispute_type == "route_deviation":
        # Recompute outcome from the Judge's findings.
        f = dict(facts)
        f["rider_requested_detour"] = decision.rider_requested_detour
        f["traffic_justified"] = decision.traffic_justified
        outcome, amount, formula_clauses, conduct = (
            compute_route_deviation_outcome(f)
        )
    else:
        outcome, amount, formula_clauses, conduct = compute_no_show_outcome(facts)

    # Merge clauses: formula's clauses first, then extra valid ones from
    # the Judge, with duplicates removed.
    merged_clauses: list[str] = list(formula_clauses)
    for cid in decision.clauses_cited:
        if cid not in merged_clauses:
            merged_clauses.append(cid)

    # Check for missing evidence escalation.
    missing = facts.get("missing_evidence", [])
    escalated = outcome == "escalate"
    escalation_reason: str | None = None

    if escalated:
        if missing:
            escalation_reason = "Missing evidence: " + ", ".join(missing)
        else:
            escalation_reason = "[Judge] Escalation required"

    # Low confidence forces escalation (E-1.6).
    if decision.confidence < SPOT_CHECK_THRESHOLD:
        outcome = "escalate"
        amount = 0.0
        escalated = True
        if escalation_reason is None:
            escalation_reason = "Low confidence"
        else:
            escalation_reason = "Low confidence; " + escalation_reason

    ruling = Ruling(
        dispute_id=dispute_id,
        outcome=outcome,
        amount_sgd=amount,
        confidence=decision.confidence,
        clauses_cited=merged_clauses,
        explanation_rider=decision.explanation_rider,
        explanation_driver=decision.explanation_driver,
        conduct_flag=conduct,
        escalated=escalated,
        escalation_reason=escalation_reason,
    )
    return ruling
