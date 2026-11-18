"""Render an acceptance report directly from the recorded inputs and results."""

import re

from app.models.procurement import ProcurementSession, PublicAnswer
from app.services.procurement_sources import load_case

_OUTCOMES = {"passed": "通过", "failed": "失败", "error": "执行异常"}
_ATTEMPTS = {"returned": "已返回", "timeout": "超时", "error": "异常"}


def _inline(value: str) -> str:
    return re.sub(r"([\\\x60*_\[\]<>|])", r"\\\1", " ".join(value.splitlines()))


def _answer(answer: PublicAnswer | None) -> str:
    if answer is None:
        return "未返回"
    if answer.value:
        return answer.value.replace("T", " ").replace("+08:00", "（北京时间）")
    return {
        "answered": "未提供事实值",
        "insufficient_evidence": "资料不足",
        "unsupported_question": "超出公告问答范围",
    }[answer.status]


def render_procurement_report(session: ProcurementSession) -> str:
    case = load_case()
    sources = {row.evidence_id: row for row in case.sources}
    plan = session.plan
    if plan is None:
        raise ValueError("验收方案尚未生成")
    scope = "公开进度及内部审批" if session.scope == "public_and_internal" else "仅公开进度"
    passed = sum(item.outcome == "passed" for item in session.results)
    lines = [
        "# 企业采购 AI 售前 Copilot｜PoC 验收报告", "",
        f"{case.buyer} · {case.title}", "",
        f"- 采购编号 **{case.project_id}**",
        f"- 会话 **{session.session_id}**",
        f"- 公告快照 **{session.snapshot_version}**",
        f"- 确认范围 **{scope}**",
        f"- 公开用例 **通过 {passed} / 已执行 {len(session.results)}**",
        "", "## 模拟需求与范围确认", "",
        f"> {_inline(session.user_input)}", "",
    ]
    for turn in session.clarifications:
        lines.extend([f"- **追问** {_inline(turn.text)}", f"- **模拟答复** {_inline(turn.answer)}"])
    lines += ["", "## 方案与需求", "", _inline(plan.summary), ""]
    for item in plan.requirements:
        status = "待联调／未执行" if item.scope_status == "pending_integration" else "PoC 范围内"
        origin = "模拟客户答复" if item.origin == "customer_reply" else "公开公告与模拟场景"
        lines.append(f"- **{item.requirement_id} · {status}** {item.description}（{origin}）")

    lines += [
        "", "## 实测验收表", "",
        "| 用例 · 需求 | 采购编号 / 截至日期（北京时间） | 实际值 | 预期值 | 实际引用 | 结果 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in session.results:
        test = item.case
        refs = []
        for evidence_id in item.actual.evidence_ids if item.actual else []:
            source = sources.get(evidence_id)
            refs.append(f"[{source.title}]({source.url})" if source else _inline(evidence_id))
        lines.append(
            f"| {test.case_id} · {test.requirement_id} {test.title} | {test.project_id} / {test.as_of} | "
            f"{_inline(_answer(item.actual))} | {_inline(_answer(test.expected))} | "
            f"{'、'.join(refs) or '—'} | {_OUTCOMES[item.outcome]} |"
        )

    lines += ["", "### 工具输入、尝试与复核", ""]
    for item in session.results:
        lines.append(f"- **{item.case.case_id}** {_inline(item.case.question)}")
        for attempt in item.attempts:
            detail = f" · {_inline(attempt.detail)}" if attempt.detail else ""
            lines.append(f"  - {_ATTEMPTS[attempt.status]} · {attempt.elapsed_ms:.2f} ms{detail}")
        for issue in item.issues:
            lines.append(f"  - {_inline(issue)}")
        for source in item.reviewed:
            lines.append(f"  - 复核 [{source.title}]({source.url}) · {_inline(source.locator)}")

    if plan.integration_checks:
        lines += ["", "## 内部审批联调清单", "", "R03 当前状态为 **待联调／未执行**。", ""]
        for check in plan.integration_checks:
            lines += [
                f"- **{check.dependency}** · {check.needed}",
                f"  - 用例 · {check.scenario}",
                f"  - 预期 · {check.expected}",
            ]

    lines += ["", "## 工作流轨迹", ""]
    for event in session.trace:
        lines.append(f"- {event.ts.isoformat(timespec='seconds')} · {_inline(event.note)}")

    lines += ["", "## 公告出处", ""]
    for row in sources.values():
        lines.append(f"- [{row.title}]({row.url}) · {row.published_at.date()} · {row.locator}")
    return "\n".join(lines) + "\n"
