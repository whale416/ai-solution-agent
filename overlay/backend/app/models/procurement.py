"""Contracts for the public procurement PoC."""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Scope = Literal["public_only", "public_and_internal", "unknown"]


class Evidence(BaseModel):
    evidence_id: str
    project_id: str
    kind: Literal["tender", "candidate"]
    title: str
    url: str
    published_at: AwareDatetime
    locator: str
    excerpt: str
    tender_deadline: AwareDatetime | None = None


class ProcurementCase(BaseModel):
    case_id: str
    title: str
    buyer: str
    project_id: str
    snapshot_version: str
    sample_as_of: date
    sample_input: str
    sources: list[Evidence]


class PublicQuery(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=500)
    project_id: str = Field(min_length=1, max_length=80)
    as_of: date


class PublicAnswer(BaseModel):
    status: Literal["answered", "insufficient_evidence", "unsupported_question"]
    value: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class AcceptanceCase(PublicQuery):
    case_id: str
    requirement_id: str
    title: str
    expected: PublicAnswer


class Requirement(BaseModel):
    requirement_id: str
    description: str
    evidence_ids: list[str]
    origin: Literal["case_scope", "customer_reply"]
    scope_status: Literal["in_scope", "pending_integration"]


class IntegrationCheck(BaseModel):
    dependency: str
    needed: str
    scenario: str
    expected: str


class VerificationPlan(BaseModel):
    summary: str
    requirements: list[Requirement]
    case_ids: list[str]
    integration_checks: list[IntegrationCheck]


class ToolAttempt(BaseModel):
    status: Literal["returned", "timeout", "error"]
    elapsed_ms: float
    detail: str | None = None


class VerificationResult(BaseModel):
    case: AcceptanceCase
    outcome: Literal["passed", "failed", "error"]
    actual: PublicAnswer | None = None
    attempts: list[ToolAttempt]
    issues: list[str] = Field(default_factory=list)
    reviewed: list[Evidence] = Field(default_factory=list)


class PendingQuestion(BaseModel):
    question_id: str
    text: str


class Clarification(PendingQuestion):
    answer: str


class TraceEntry(BaseModel):
    step: Literal["discovery", "clarification", "solution", "verification"]
    ts: AwareDatetime
    note: str
    case_id: str | None = None


class ProcurementSession(BaseModel):
    session_id: str
    case_id: str
    snapshot_version: str
    user_input: str
    mode: Literal["rules", "deepseek"]
    status: Literal["need_clarification", "running", "completed"]
    scope: Scope
    pending_question: PendingQuestion | None
    clarifications: list[Clarification] = Field(default_factory=list)
    plan: VerificationPlan | None = None
    results: list[VerificationResult] = Field(default_factory=list)
    trace: list[TraceEntry] = Field(default_factory=list)
