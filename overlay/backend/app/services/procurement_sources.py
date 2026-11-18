"""Read-only evidence store and question answering over the case snapshot."""

from __future__ import annotations

import re
from datetime import date, timedelta, timezone
from functools import lru_cache

from app.config.settings import BACKEND_DIR
from app.models.procurement import Evidence, ProcurementCase, PublicAnswer

BEIJING = timezone(timedelta(hours=8))
DATA_DIR = BACKEND_DIR / "data" / "procurement"
_DEADLINE = re.compile(
    r"截标|(?:投标|交标|递交|提交)[^，。？,?\n]{0,15}截止"
    r"|截止(?:时间|日期|递交|提交|到?几点|到?哪天)"
    r"|(?:什么时候|何时)截止|递交到什么时候|什么时候(?:递交|提交|交标)"
)
_STAGE = re.compile(r"阶段|进度|状态|走到|进行到|公示|进展")
_INTERNAL = re.compile(r"内部审批|内部进度|内部流程|审批节点|审批流转")
_STAGES = {"tender": "已发布招标公告", "candidate": "已发布中标候选人公示"}


@lru_cache(maxsize=1)
def load_case() -> ProcurementCase:
    return ProcurementCase.model_validate_json(
        (DATA_DIR / "csg_case.json").read_text(encoding="utf-8")
    )


def get_evidence(evidence_id: str) -> Evidence | None:
    return next((row for row in load_case().sources if row.evidence_id == evidence_id), None)


def visible_on(evidence: Evidence, as_of: date) -> bool:
    return evidence.published_at.astimezone(BEIJING).date() <= as_of


def answer_public(question: str, project_id: str, as_of: date) -> PublicAnswer:
    """Query by explicit project identifier and the end of the Beijing calendar day."""
    visible = [
        row for row in load_case().sources
        if row.project_id == project_id.strip().upper() and visible_on(row, as_of)
    ]
    if not visible:
        return PublicAnswer(status="insufficient_evidence")
    if _INTERNAL.search(question):
        return PublicAnswer(status="unsupported_question")

    if _DEADLINE.search(question):
        tender = next((row for row in visible if row.kind == "tender"), None)
        if tender is None or tender.tender_deadline is None:
            return PublicAnswer(status="insufficient_evidence")
        return PublicAnswer(
            status="answered",
            value=tender.tender_deadline.astimezone(BEIJING).isoformat(),
            evidence_ids=[tender.evidence_id],
        )
    if _STAGE.search(question):
        latest = max(visible, key=lambda row: row.published_at)
        return PublicAnswer(
            status="answered", value=_STAGES[latest.kind], evidence_ids=[latest.evidence_id]
        )
    return PublicAnswer(status="unsupported_question")
