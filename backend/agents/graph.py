"""LangGraph orchestration: evidence -> advocates (parallel) -> Judge -> route.

    START -> gather_evidence -+-> rider_advocate --+-> judge -+-> issue_ruling -> END
                              +-> driver_advocate -+          +-> human_review -> END

The Judge's ruling is routed to the human review queue when it is escalated
(safety incident, missing evidence or low confidence; S-1.2, E-1.6),
otherwise it is issued to both parties.  ``build_graph().astream(...,
stream_mode="updates")`` yields one update per node as it finishes, which
the API streams to the UI.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.advocates import run_advocate
from agents.context import gather_evidence, relevant_clauses
from agents.judge import run_judge
from schemas import AdvocateBrief, DisputeCase, EvidenceOutput, Ruling


class DisputeState(TypedDict, total=False):
    case: DisputeCase
    driver_first: bool  # Judge reads the driver's brief first (fairness test)
    clauses: dict[str, str]
    evidence: list[EvidenceOutput]
    rider_brief: AdvocateBrief
    driver_brief: AdvocateBrief
    ruling: Ruling
    routed_to: Literal["issue_ruling", "human_review"]


async def _gather_evidence(state: DisputeState) -> DisputeState:
    case = state["case"]
    return {
        "clauses": relevant_clauses(case.dispute_ticket.dispute_type),
        "evidence": gather_evidence(case),
    }


async def _rider_advocate(state: DisputeState) -> DisputeState:
    brief = await run_advocate(
        "rider", state["case"], state["evidence"], state["clauses"],
    )
    return {"rider_brief": brief}


async def _driver_advocate(state: DisputeState) -> DisputeState:
    brief = await run_advocate(
        "driver", state["case"], state["evidence"], state["clauses"],
    )
    return {"driver_brief": brief}


async def _judge(state: DisputeState) -> DisputeState:
    ruling = await run_judge(
        state["case"],
        state["evidence"],
        state["clauses"],
        state["rider_brief"],
        state["driver_brief"],
        driver_first=state.get("driver_first", False),
    )
    return {"ruling": ruling}


def _route_ruling(state: DisputeState) -> Literal["issue_ruling", "human_review"]:
    return "human_review" if state["ruling"].escalated else "issue_ruling"


async def _issue_ruling(state: DisputeState) -> DisputeState:
    return {"routed_to": "issue_ruling"}


async def _human_review(state: DisputeState) -> DisputeState:
    # The review queue itself (list, approve/override) comes on Mon 12 Oct.
    return {"routed_to": "human_review"}


def build_graph():
    graph = StateGraph(DisputeState)
    graph.add_node("gather_evidence", _gather_evidence)
    graph.add_node("rider_advocate", _rider_advocate)
    graph.add_node("driver_advocate", _driver_advocate)
    graph.add_node("judge", _judge)
    graph.add_node("issue_ruling", _issue_ruling)
    graph.add_node("human_review", _human_review)

    graph.add_edge(START, "gather_evidence")
    # Both advocates run in parallel on the same inputs (E-1.2).
    graph.add_edge("gather_evidence", "rider_advocate")
    graph.add_edge("gather_evidence", "driver_advocate")
    graph.add_edge(["rider_advocate", "driver_advocate"], "judge")
    graph.add_conditional_edges(
        "judge", _route_ruling, ["issue_ruling", "human_review"],
    )
    graph.add_edge("issue_ruling", END)
    graph.add_edge("human_review", END)
    return graph.compile()


dispute_graph = build_graph()
