"""Persist and resume procurement sessions using the LangGraph checkpointer."""

from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, StateSnapshot

from app.agents.procurement_agents import model_available
from app.graph.procurement_workflow import build_procurement_graph
from app.models.procurement import ProcurementSession
from app.services.procurement_sources import load_case


class StaleClarification(ValueError):
    """The submitted answer does not belong to the current question."""


def _view(snapshot: StateSnapshot) -> ProcurementSession:
    values = snapshot.values
    if not values:
        raise KeyError("会话不存在")
    waiting = next(iter(snapshot.interrupts), None)
    pending = {"question_id": waiting.id, "text": waiting.value["text"]} if waiting else None
    if pending:
        status = "need_clarification"
    elif snapshot.next:
        status = "running"
    else:
        status = "completed"
    return ProcurementSession.model_validate({
        **values, "status": status, "pending_question": pending, "scope": values.get("scope", "unknown"),
    })


class ProcurementSessions:
    def __init__(self, database: Path):
        self.database = database
        self._resume_lock = Lock()

    @contextmanager
    def _open_graph(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(str(self.database)) as saver:
            yield build_procurement_graph(saver)

    def start(self, case_id: str, user_input: str) -> ProcurementSession:
        case = load_case()
        if case_id != case.case_id:
            raise KeyError("案例不存在")
        session_id = str(uuid4())
        config = {"configurable": {"thread_id": session_id}}
        with self._open_graph() as graph:
            graph.invoke({
                "session_id": session_id,
                "case_id": case_id,
                "user_input": user_input,
                "snapshot_version": case.snapshot_version,
                "mode": "deepseek" if model_available() else "rules",
            }, config)
            return _view(graph.get_state(config))

    def get(self, session_id: str) -> ProcurementSession:
        config = {"configurable": {"thread_id": session_id}}
        with self._open_graph() as graph:
            return _view(graph.get_state(config))

    def resume(self, session_id: str, question_id: str, answer: str) -> ProcurementSession:
        config = {"configurable": {"thread_id": session_id}}
        # Serialize submissions in this local server so a double click cannot replay a turn.
        with self._resume_lock, self._open_graph() as graph:
            snapshot = graph.get_state(config)
            session = _view(snapshot)
            previous = next(
                (turn for turn in session.clarifications if turn.question_id == question_id), None
            )
            if previous:
                if previous.answer != answer:
                    raise StaleClarification("该问题已收到答复，请刷新会话")
                if session.status == "running":
                    graph.invoke(None, config)
                    return _view(graph.get_state(config))
                return session
            if not session.pending_question or session.pending_question.question_id != question_id:
                raise StaleClarification("该澄清问题已失效，请刷新会话")
            graph.invoke(Command(resume={question_id: {
                "question_id": question_id, "answer": answer,
            }}), config)
            return _view(graph.get_state(config))
