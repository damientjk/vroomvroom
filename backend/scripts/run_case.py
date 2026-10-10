"""Run one dispute end-to-end through the agent pipeline.

Usage (from backend/):
    python3 scripts/run_case.py DISP-002
    python3 scripts/run_case.py TC-05

Loads the case the same way app/main.py's case index does (reuses
``_CASE_INDEX`` from ``app.main`` without changing the endpoint's
behaviour), runs ``resolve_case``, and pretty-prints the briefs and
ruling.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure backend/ is on sys.path when run as a script.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from agents.pipeline import resolve_case
from app.main import _CASE_INDEX
from schemas import DisputeCase


def load_case(dispute_id: str) -> DisputeCase:
    """Look up a case by dispute ID or TC prefix."""
    case = _CASE_INDEX.get(dispute_id)
    if case is None:
        print(f"Unknown dispute ID or TC prefix: {dispute_id}", file=sys.stderr)
        print(
            f"Available: {', '.join(sorted(_CASE_INDEX.keys()))}",
            file=sys.stderr,
        )
        sys.exit(1)
    return case


def _print_brief(brief, label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label} Advocate Brief")
    print(f"{'=' * 60}")
    print(f"  Side:      {brief.side}")
    print(f"  Position:  {brief.position}")
    print(f"  Arguments ({len(brief.arguments)}):")
    for i, arg in enumerate(brief.arguments, 1):
        print(f"    {i}. {arg.point}")
        print(f"       Evidence: {', '.join(arg.evidence_refs)}")
        print(f"       Clauses:  {', '.join(arg.clauses)}")
    if brief.weaknesses_acknowledged:
        print(f"  Weaknesses acknowledged:")
        for w in brief.weaknesses_acknowledged:
            print(f"    - {w}")


def _print_ruling(ruling) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Judge's Ruling")
    print(f"{'=' * 60}")
    print(f"  Dispute ID:        {ruling.dispute_id}")
    print(f"  Outcome:           {ruling.outcome}")
    print(f"  Amount (SGD):      ${ruling.amount_sgd:.2f}")
    print(f"  Confidence:        {ruling.confidence:.2f}")
    print(f"  Clauses cited:     {', '.join(ruling.clauses_cited)}")
    print(f"  Conduct flag:      {ruling.conduct_flag}")
    print(f"  Escalated:         {ruling.escalated}")
    if ruling.escalation_reason:
        print(f"  Escalation reason: {ruling.escalation_reason}")
    print(f"  Explanation (rider):")
    print(f"    {ruling.explanation_rider}")
    print(f"  Explanation (driver):")
    print(f"    {ruling.explanation_driver}")


def _print_evidence(evidence_list) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Evidence")
    print(f"{'=' * 60}")
    for ev in evidence_list:
        print(f"\n  Tool: {ev.tool}")
        if ev.flags:
            print(f"  Flags: {', '.join(ev.flags)}")
        print(f"  Facts:")
        for key in sorted(ev.facts):
            val = ev.facts[key]
            if isinstance(val, (list, dict)):
                val_str = json.dumps(val, ensure_ascii=False)
                if len(val_str) > 100:
                    val_str = val_str[:100] + "..."
            else:
                val_str = str(val)
            print(f"    {key}: {val_str}")


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/run_case.py <dispute_id_or_tc_prefix>")
        sys.exit(1)

    dispute_id = sys.argv[1]
    case = load_case(dispute_id)

    print(f"Resolving dispute: {case.dispute_ticket.dispute_id}")
    print(f"  Type:   {case.dispute_ticket.dispute_type}")
    print(f"  Filed by: {case.dispute_ticket.filed_by}")
    print(f"  Description: {case.dispute_ticket.description[:120]}")

    result = await resolve_case(case)

    _print_evidence(result["evidence"])
    _print_brief(result["rider_brief"], "Rider")
    _print_brief(result["driver_brief"], "Driver")
    _print_ruling(result["ruling"])
    print()


if __name__ == "__main__":
    asyncio.run(main())
