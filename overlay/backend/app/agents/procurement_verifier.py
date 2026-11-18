"""Run the registered acceptance checks and recheck sources after a discrepancy."""

from time import perf_counter

from app.agents.procurement_agents import acceptance_cases
from app.models.procurement import AcceptanceCase, PublicAnswer, ToolAttempt, VerificationResult
from app.services.procurement_sources import answer_public, get_evidence, visible_on


def _compare(case: AcceptanceCase, actual: PublicAnswer) -> list[str]:
    issues = []
    if actual.status != case.expected.status:
        issues.append("应答状态与预期不符")
    if actual.value != case.expected.value:
        issues.append("事实值与预期不符")
    if sorted(actual.evidence_ids) != sorted(case.expected.evidence_ids):
        issues.append("引用缺失或与预期原文不符")
    for evidence_id in actual.evidence_ids:
        evidence = get_evidence(evidence_id)
        if evidence is None or evidence.project_id != case.project_id or not visible_on(evidence, case.as_of):
            issues.append(f"证据 {evidence_id} 无法支持此采购编号或日期")
    return issues


def run_acceptance_case(case_id: str) -> VerificationResult:
    case = acceptance_cases()[case_id]
    attempts = []
    actual = None
    for _ in range(2):
        started = perf_counter()
        try:
            actual = answer_public(case.question, case.project_id, case.as_of)
        except TimeoutError:
            attempts.append(ToolAttempt(
                status="timeout", elapsed_ms=round((perf_counter() - started) * 1000, 2),
                detail="公告问答工具超时",
            ))
            continue
        except Exception as exc:
            attempts.append(ToolAttempt(
                status="error", elapsed_ms=round((perf_counter() - started) * 1000, 2),
                detail=f"公告问答工具异常（{type(exc).__name__}）",
            ))
            break
        attempts.append(ToolAttempt(
            status="returned", elapsed_ms=round((perf_counter() - started) * 1000, 2)
        ))
        break

    if actual is None:
        return VerificationResult(
            case=case, outcome="error", attempts=attempts,
            issues=[attempts[-1].detail or "工具未返回结果"],
        )

    issues = _compare(case, actual)
    reviewed = []
    if issues:
        ids = dict.fromkeys([*actual.evidence_ids, *case.expected.evidence_ids])
        reviewed = [row for evidence_id in ids if (row := get_evidence(evidence_id)) is not None]
    return VerificationResult(
        case=case, outcome="failed" if issues else "passed", actual=actual,
        attempts=attempts, issues=issues, reviewed=reviewed,
    )
