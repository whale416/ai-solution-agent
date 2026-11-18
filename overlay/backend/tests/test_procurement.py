"""Exercise both procurement PoC branches through the mounted FastAPI routes."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agents.procurement_agents import PlanDraft, ScopeDecision
from app.agents.procurement_verifier import run_acceptance_case
from app.config.settings import BACKEND_DIR, settings
from app.main import app
from app.models.procurement import PublicAnswer
from app.routes.procurement import session_store
from app.services.llm_provider import get_llm, invoke_structured
from app.services.procurement_sessions import ProcurementSessions
from app.services.procurement_sources import load_case

API = "/api/procurement"
PUBLIC = "一期只查公开进度"
BOTH = "公开进度要查，也要查内部审批"


class ProcurementTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=BACKEND_DIR / "data")
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "test.sqlite"
        self.store = ProcurementSessions(self.database)
        app.dependency_overrides[session_store] = lambda: self.store
        self.addCleanup(app.dependency_overrides.pop, session_store)
        self.enterContext(patch.object(settings, "deepseek_api_key", ""))
        self.client = self.enterContext(TestClient(app))
        self.case = load_case()

    def _start(self):
        res = self.client.post(f"{API}/sessions", json={
            "case_id": self.case.case_id, "user_input": self.case.sample_input,
        })
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def _resume(self, session, reply):
        res = self.client.post(f"{API}/sessions/{session['session_id']}/resume", json={
            "question_id": session["pending_question"]["question_id"], "answer": reply,
        })
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def _query(self, question, as_of, project_id=None):
        res = self.client.post(f"{API}/query", json={
            "question": question, "project_id": project_id or self.case.project_id, "as_of": as_of,
        })
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def _download(self, session):
        res = self.client.get(f"{API}/sessions/{session['session_id']}/report")
        self.assertEqual(res.status_code, 200)
        self.assertIn("attachment", res.headers["content-disposition"])
        return res.text

    def test_t01_wait_for_scope_before_tools(self):
        with patch("app.graph.procurement_workflow.run_acceptance_case") as run:
            session = self._start()
        self.assertEqual(session["status"], "need_clarification")
        self.assertIn("内部审批", session["pending_question"]["text"])
        self.assertEqual(session["results"], [])
        run.assert_not_called()
        res = self.client.get(f"{API}/sessions/{session['session_id']}/report")
        self.assertEqual(res.status_code, 409)

    def test_t02_ambiguous_reply_reprompts(self):
        first = self._start()
        follow_up = self._resume(first, "先做个能看的版本")
        self.assertEqual(follow_up["status"], "need_clarification")
        self.assertNotEqual(follow_up["pending_question"]["question_id"], first["pending_question"]["question_id"])
        self.assertEqual(follow_up["results"], [])
        self.assertEqual(len(follow_up["clarifications"]), 1)
        self.assertEqual(self._resume(follow_up, PUBLIC)["scope"], "public_only")

    def test_t03_public_only_checks_live_sandbox(self):
        session = self._resume(self._start(), "首期先查对外公告，暂不接审批系统")
        self.assertEqual(session["status"], "completed")
        self.assertEqual(session["scope"], "public_only")
        self.assertEqual(session["plan"]["integration_checks"], [])
        self.assertEqual([result["case"]["case_id"] for result in session["results"]], ["T05", "T06", "T07", "T08"])
        self.assertTrue(all(result["outcome"] == "passed" for result in session["results"]))
        self.assertEqual(session["results"][0]["actual"]["evidence_ids"], ["csg-tender"])

    def test_t04_internal_approval_waits_for_integration(self):
        session = self._resume(self._start(), BOTH)
        self.assertEqual(session["scope"], "public_and_internal")
        self.assertEqual(session["plan"]["requirements"][-1]["scope_status"], "pending_integration")
        self.assertEqual(len(session["plan"]["integration_checks"]), 4)
        self.assertTrue(all(result["outcome"] == "passed" for result in session["results"]))
        self.assertIn("待联调／未执行", self._download(session))

    def test_t05_tender_cutoff_with_evidence(self):
        result = self._query("按原招标公告，投标文件什么时候截止递交？", "2026-10-22")
        self.assertEqual(result["value"], "2026-10-13T09:00:00+08:00")
        self.assertEqual(result["evidence_ids"], ["csg-tender"])
        case = self.client.get(f"{API}/case").json()
        self.assertEqual(case["sources"][0]["url"], "https://www.bidding.csg.cn/zbgg/1200442355.jhtml")

    def test_t06_candidate_notice_by_beijing_day(self):
        for cutoff in ("2026-10-21", "2026-10-22"):
            with self.subTest(cutoff=cutoff):
                result = self._query("项目走到哪个公开阶段了？", cutoff)
                self.assertEqual(result["value"], "已发布中标候选人公示")
                self.assertEqual(result["evidence_ids"], ["csg-candidates"])

    def test_t07_future_notice_is_excluded(self):
        for question in ("项目走到哪个公开阶段了？", "截止到指定日期，项目公开进度如何？"):
            with self.subTest(question=question):
                result = self._query(question, "2026-10-20")
                self.assertEqual(result["value"], "已发布招标公告")
                self.assertEqual(result["evidence_ids"], ["csg-tender"])
        self.assertEqual(self._query("公开进度？", "2026-09-10")["status"], "insufficient_evidence")

    def test_t08_unknown_project_never_falls_back(self):
        result = self._query("公开进度？", "2026-10-22", "CG0000000000000000")
        self.assertEqual(result, {"status": "insufficient_evidence", "value": None, "evidence_ids": []})

    def test_t09_reference_error_triggers_review(self):
        for evidence in ([], ["csg-candidates"]):
            with self.subTest(evidence=evidence):
                actual = PublicAnswer(status="answered", value="2026-10-13T09:00:00+08:00", evidence_ids=evidence)
                with patch("app.agents.procurement_verifier.answer_public", return_value=actual):
                    result = run_acceptance_case("T05")
                self.assertEqual(result.outcome, "failed")
                self.assertEqual(result.actual, actual)
                self.assertEqual(result.reviewed[-1].evidence_id, "csg-tender")
                self.assertTrue(result.issues)

    def test_t10_timeouts_retried_once(self):
        with patch("app.agents.procurement_verifier.answer_public", side_effect=TimeoutError) as answer:
            result = run_acceptance_case("T05")
        self.assertEqual(answer.call_count, 2)
        self.assertEqual(result.outcome, "error")
        self.assertEqual([attempt.status for attempt in result.attempts], ["timeout", "timeout"])

    def test_t11_restart_reads_checkpoint_and_resumes(self):
        first = self._start()
        self.store = ProcurementSessions(self.database)
        restored = self.client.get(f"{API}/sessions/{first['session_id']}").json()
        self.assertEqual(restored["pending_question"], first["pending_question"])
        result = self._resume(restored, PUBLIC)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["clarifications"]), 1)

    def test_t12_sessions_export_independent_reports(self):
        public = self._resume(self._start(), PUBLIC)
        internal = self._resume(self._start(), BOTH)
        self.assertNotEqual(public["session_id"], internal["session_id"])
        public_md, internal_md = self._download(public), self._download(internal)
        self.assertIn(PUBLIC, public_md)
        self.assertIn(BOTH, internal_md)
        self.assertIn("通过 4 / 已执行 4", public_md)
        self.assertIn("通过 4 / 已执行 4", internal_md)
        self.assertNotIn("内部审批联调清单", public_md)
        self.assertIn("内部审批联调清单", internal_md)

    def test_repeat_submission_does_not_add_a_second_turn(self):
        first = self._start()
        completed = self._resume(first, PUBLIC)
        self.assertEqual(self._resume(first, PUBLIC), completed)
        res = self.client.post(f"{API}/sessions/{first['session_id']}/resume", json={
            "question_id": first["pending_question"]["question_id"], "answer": BOTH,
        })
        self.assertEqual(res.status_code, 409)

    def test_deepseek_structured_output_disables_thinking(self):
        expected = ScopeDecision(scope="public_only")
        with (
            patch.object(settings, "deepseek_base_url", "https://api.deepseek.com"),
            patch("app.services.llm_provider.ChatOpenAI") as chat_model,
        ):
            chat_model.return_value.with_structured_output.return_value.invoke.return_value = expected
            result = invoke_structured(ScopeDecision, [("human", PUBLIC)], retries=1, timeout=12)
            self.assertEqual(result, expected)
            self.assertEqual(chat_model.call_args.kwargs["extra_body"], {"thinking": {"type": "disabled"}})
            get_llm()
            self.assertNotIn("extra_body", chat_model.call_args.kwargs)

        with (
            patch.object(settings, "deepseek_base_url", "https://compat.example.test/v1"),
            patch("app.services.llm_provider.ChatOpenAI") as chat_model,
        ):
            get_llm(structured_output=True)
            self.assertNotIn("extra_body", chat_model.call_args.kwargs)

    def test_model_suggestions_still_execute_real_checks(self):
        with (
            patch.object(settings, "deepseek_api_key", "test-key"),
            patch("app.agents.procurement_agents.invoke_structured", side_effect=[
                ScopeDecision(scope="unknown"),
                ScopeDecision(scope="public_only"),
                PlanDraft(priority=["T06", "T05", "T07", "T08"], summary="先核对历史阶段，再核对截标时间。"),
            ]) as model,
        ):
            session = self._resume(self._start(), PUBLIC)
        self.assertEqual(model.call_count, 3)
        self.assertEqual(session["mode"], "deepseek")
        self.assertEqual(session["results"][0]["case"]["case_id"], "T06")
        self.assertTrue(all(result["outcome"] == "passed" for result in session["results"]))


if __name__ == "__main__":
    unittest.main()
