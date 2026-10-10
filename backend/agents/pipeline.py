"""End-to-end pipeline: evidence -> advocates (parallel) -> judge -> ruling.

Runs the LangGraph in ``agents/graph.py`` to completion; the API streams
the same graph node by node instead.
"""

from __future__ import annotations

from typing import Any

from agents.graph import dispute_graph
from schemas import DisputeCase


async def resolve_case(
    case: DisputeCase, *, driver_first: bool = False,
) -> dict[str, Any]:
    """Resolve a dispute end-to-end.

    Returns ``{"evidence": [...], "rider_brief": ..., "driver_brief": ...,
    "ruling": ..., "routed_to": "issue_ruling" | "human_review"}``.
    """
    state = await dispute_graph.ainvoke({"case": case, "driver_first": driver_first})
    return {
        "evidence": state["evidence"],
        "rider_brief": state["rider_brief"],
        "driver_brief": state["driver_brief"],
        "ruling": state["ruling"],
        "routed_to": state["routed_to"],
    }
