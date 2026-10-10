"""Advocate agents (Rider Advocate and Driver Advocate).

Both sides use the same system-prompt template with only the side name
filled in.  Each advocate receives the same user message (case summary +
evidence + clause texts) and must reply with JSON matching the
``AdvocateBrief`` schema.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from agents.llm import LLMError, chat, parse_model_reply
from agents.context import case_summary
from schemas import AdvocateBrief, DisputeCase, EvidenceOutput

_AGENT_NAME = "{side}_advocate"

_SYSTEM_PROMPT = """\
You are the {side} advocate in a Ryde ride-hailing dispute resolution system.

You argue for the {side}, honestly. Use only the evidence given; never \
invent facts.

Every argument must cite at least one evidence ref in the form \
<tool>.<fact_key> (e.g. no_show_check.total_wait_min) and at least one \
clause ID from the policy given.

At most 5 arguments, each under 400 characters; position under 200 \
characters.

List the weaknesses in your side's case in weaknesses_acknowledged.

Ratings and history may not override trip evidence (E-1.4).

Reply with only JSON matching the AdvocateBrief schema:

{schema}
"""


def _build_user_message(
    case: DisputeCase,
    evidence: list[EvidenceOutput],
    clauses: dict[str, str],
) -> str:
    """Build the identical user message for both advocates."""
    summary = case_summary(case)
    evidence_data = [e.model_dump(mode="json") for e in evidence]
    payload: dict[str, Any] = {
        "case_summary": summary,
        "evidence": evidence_data,
        "relevant_clauses": clauses,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _validate_brief(
    brief: AdvocateBrief,
    evidence: list[EvidenceOutput],
    clauses: dict[str, str],
) -> None:
    """Validate evidence_refs and clause IDs in *brief*.

    Raises ``LLMError`` with a message explaining the first violation.
    """
    # Build a set of valid tool.fact_key prefixes (top-level keys only).
    valid_refs: set[str] = set()
    for ev in evidence:
        for key in ev.facts:
            valid_refs.add(f"{ev.tool}.{key}")

    for arg in brief.arguments:
        for ref in arg.evidence_refs:
            # For nested keys like history_lookup.rider.x, check the
            # top-level key (tool.first_key).
            parts = ref.split(".")
            if len(parts) < 2:
                raise LLMError(
                    f"Invalid evidence ref '{ref}': must be in the form "
                    f"<tool>.<fact_key>."
                )
            top_key = f"{parts[0]}.{parts[1]}"
            if top_key not in valid_refs:
                raise LLMError(
                    f"Invalid evidence ref '{ref}': '{top_key}' does not "
                    f"match any tool.fact_key in the evidence."
                )

        for clause_id in arg.clauses:
            if clause_id not in clauses:
                raise LLMError(
                    f"Invalid clause ID '{clause_id}': not found in the "
                    f"policy clauses provided."
                )


async def run_advocate(
    side: Literal["rider", "driver"],
    case: DisputeCase,
    evidence: list[EvidenceOutput],
    clauses: dict[str, str],
) -> AdvocateBrief:
    """Run one advocate agent and return its brief.

    *side* is "rider" or "driver".  The advocate calls the LLM, parses
    the reply into an ``AdvocateBrief``, validates evidence refs and
    clause IDs, and retries once on failure before raising ``LLMError``.
    """
    agent = _AGENT_NAME.format(side=side)
    system_prompt = _SYSTEM_PROMPT.format(
        side=side,
        schema=json.dumps(
            AdvocateBrief.model_json_schema(), ensure_ascii=False, indent=2
        ),
    )
    user_message = _build_user_message(case, evidence, clauses)

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

        result = await chat(agent, system_prompt, msg)
        try:
            brief = parse_model_reply(result.text, AdvocateBrief)
            # Override side to ensure consistency.
            brief = brief.model_copy(update={"side": side})
            _validate_brief(brief, evidence, clauses)
            return brief
        except LLMError as exc:
            last_error = str(exc)
            if attempt == 1:
                raise

    # Unreachable — the loop either returns or raises.
    raise LLMError(f"Advocate {side} failed after retry.")
