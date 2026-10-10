"""Safety evidence tool.

Surfaces candidate safety incidents (S-1.1) from chat logs, the dispute
description and GPS speed.  Spec: docs/policy_implementation_handoff.md
``check_safety``.  A safety incident always escalates to human review
(S-1.2), overriding whatever the dispute-type formula would decide —
see ``safety_override`` below.
"""

from __future__ import annotations

import re

from app.policy_constants import SAFETY_KEYWORDS, SPEEDING_THRESHOLD_KMH
from schemas import DisputeCase, EvidenceOutput

# Keywords match at the start of a word, so stems like "discriminat" and
# "threat" still catch "discrimination" / "threatened", but "hit" no longer
# matches "white" (in nearly every case's "White Toyota Prius" message).
_KEYWORD_RES = {
    kw: re.compile(r"\b" + re.escape(kw), re.IGNORECASE) for kw in SAFETY_KEYWORDS
}


def _keyword_hits(text: str) -> list[str]:
    return [kw for kw, pattern in _KEYWORD_RES.items() if pattern.search(text)]


def safety_check(case: DisputeCase) -> EvidenceOutput:
    """Return safety evidence facts for *case*.

    Computes:
      - keyword_hits: safety keywords found anywhere (S-1.1)
      - flagged_messages: the chat messages / description that matched
      - max_speed_kmh, speeding (S-1.1 dangerous driving)
      - safety_incident, categories
    """
    flagged_messages: list[dict[str, str]] = []
    hits: list[str] = []

    for c in case.chat_logs:
        found = _keyword_hits(c.content)
        if found:
            flagged_messages.append({"sender": c.sender, "content": c.content})
            hits.extend(found)

    description = case.dispute_ticket.description
    found = _keyword_hits(description)
    if found:
        flagged_messages.append({"sender": "dispute_description", "content": description})
        hits.extend(found)

    keyword_hits = sorted(set(hits))

    speeds = [p.speed_kmh for p in case.gps_telemetry if p.speed_kmh is not None]
    max_speed_kmh = max(speeds) if speeds else None
    # Strictly greater than the threshold (handoff boundary test B15).
    speeding = max_speed_kmh is not None and max_speed_kmh > SPEEDING_THRESHOLD_KMH

    categories: list[str] = []
    if keyword_hits:
        categories.append("keyword: " + ", ".join(keyword_hits))
    if speeding:
        categories.append(f"speeding: {max_speed_kmh} km/h")

    facts: dict[str, object] = {
        "safety_incident": bool(categories),
        "categories": categories,
        "keyword_hits": keyword_hits,
        "flagged_messages": flagged_messages,
        "max_speed_kmh": max_speed_kmh,
        "speeding": speeding,
        "speeding_threshold_kmh": SPEEDING_THRESHOLD_KMH,
    }

    flags = ["S-1.1_SAFETY_INCIDENT"] if categories else []

    return EvidenceOutput(
        dispute_id=case.dispute_ticket.dispute_id,
        tool="safety_check",
        facts=facts,
        flags=flags,
    )


def safety_override(
    facts: dict[str, object],
) -> tuple[str, float, list[str], bool] | None:
    """Return the escalation outcome if *facts* show a safety incident.

    Same 4-tuple shape as the dispute-type outcome formulas, or ``None``
    when there is no incident.  S-1.1 / S-1.2: never auto-resolve, no
    financial action until a human reviews.
    """
    if facts["safety_incident"]:
        return ("escalate", 0.00, ["S-1.1", "S-1.2"], False)
    return None
