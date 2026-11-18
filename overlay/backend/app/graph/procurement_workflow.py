"""LangGraph workstream for discovery, solution planning and PoC verification."""

from datetime import datetime
from operator import add
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.procurement_agents import FOLLOW_UP, QUESTION, design_plan, discover_scope
from app.agents.procurement_verifier import run_acceptance_case
from app.models.procurement import Scope, TraceEntry
from app.services.procurement_sources import BEIJING


class ProcurementState(TypedDict, total=False):
    session_id: str
    user_input: str
    case_id: str
    snapshot_version: str
    mode: Literal["rules", "deepseek"]
    scope: Scope
    question: str | None
    clarifications: list[dict]
    plan: dict
    results: list[dict]
    trace: Annotated[list[dict], add]


def _entry(step, note: str, case_id: str | None = None) -> dict:
    return TraceEntry(
        step=step, ts=datetime.now(BEIJING), note=note, case_id=case_id,
    ).model_dump(mode="json")


def discover(state: ProcurementState) -> dict:
    replies = state.get("clarifications", [])
    reply = replies[-1]["answer"] if replies else None
    scope, note = discover_scope(state["user_input"], reply, state["mode"] == "deepseek")
    if scope == "unknown":
        question = FOLLOW_UP if replies else QUESTION
        note += "，等待确认公开进度与内部审批的范围"
    else:
        question = None
        note += "，已确认范围"
    return {"scope": scope, "question": question, "trace": [_entry("discovery", note)]}


def collect_reply(state: ProcurementState) -> dict:
    question = state["question"]
    reply = interrupt({"text": question})
    turn = {"question_id": reply["question_id"], "text": question, "answer": reply["answer"]}
    return {
        "clarifications": [*state.get("clarifications", []), turn],
        "trace": [_entry("clarification", "收到模拟客户答复")],
    }


def plan_solution(state: ProcurementState) -> dict:
    plan, note = design_plan(state["scope"], state["mode"] == "deepseek")
    if plan.integration_checks:
        note += "，已登记内部审批的联调依赖"
    return {"plan": plan.model_dump(mode="json"), "trace": [_entry("solution", note)]}


def verify_plan(state: ProcurementState) -> dict:
    results = [run_acceptance_case(case_id) for case_id in state["plan"]["case_ids"]]
    outcomes = {"passed": "通过", "failed": "失败", "error": "执行异常"}
    trace = [
        _entry(
            "verification",
            f"调用公告问答并核对 {result.case.title}，结果为{outcomes[result.outcome]}",
            result.case.case_id,
        )
        for result in results
    ]
    return {"results": [row.model_dump(mode="json") for row in results], "trace": trace}


def _next_step(state: ProcurementState) -> Literal["clarify", "plan"]:
    return "clarify" if state["scope"] == "unknown" else "plan"


def build_procurement_graph(checkpointer: SqliteSaver):
    graph = StateGraph(ProcurementState)
    graph.add_node("discover", discover)
    graph.add_node("clarify", collect_reply)
    graph.add_node("plan", plan_solution)
    graph.add_node("verify", verify_plan)
    graph.add_edge(START, "discover")
    graph.add_conditional_edges("discover", _next_step)
    graph.add_edge("clarify", "discover")
    graph.add_edge("plan", "verify")
    graph.add_edge("verify", END)
    return graph.compile(checkpointer=checkpointer)
