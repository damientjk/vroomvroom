"""End-to-end pipeline: evidence -> advocates (parallel) -> judge -> ruling.

Plain asyncio; LangGraph integration is a future step.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agents.advocates import run_advocate
from agents.context import gather_evidence, relevant_clauses
from agents.judge import run_judge
from schemas import DisputeCase


async def resolve_case(case: DisputeCase) -> dict[str, Any]:
    """Resolve a dispute end-to-end.

    1. Gather evidence (real tools).
    2. Run both advocates in parallel (asyncio.gather).
    3. Run the Judge.
    4. Return ``{"evidence": [...], "rider_brief": ..., "driver_brief": ..., "ruling": ...}``.
    """
    dispute_type = case.dispute_ticket.dispute_type
    clauses = relevant_clauses(dispute_type)
    evidence = gather_evidence(case)

    rider_brief, driver_brief = await asyncio.gather(
        run_advocate("rider", case, evidence, clauses),
        run_advocate("driver", case, evidence, clauses),
    )

    ruling = await run_judge(case, evidence, clauses, rider_brief, driver_brief)

    return {
        "evidence": evidence,
        "rider_brief": rider_brief,
        "driver_brief": driver_brief,
        "ruling": ruling,
    }
