import { type FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { Card, StatusBadge } from '../components/ui'
import type { ProcurementCase, ProcurementResult, ProcurementSession, PublicAnswer } from '../types'

const PUBLIC_REPLY = '一期只查公开进度'
const INTERNAL_REPLY = '公开进度要查，也要查内部审批'
const PRIMARY = 'rounded-md bg-blue-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-50'
const SECONDARY = 'rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:border-blue-500 hover:text-blue-700 disabled:opacity-50'
const FIELD = 'w-full rounded-md border border-slate-300 bg-white p-3 text-sm leading-6 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-100'

const OUTCOME = {
  passed: { label: '通过', style: 'bg-emerald-50 text-emerald-800' },
  failed: { label: '失败', style: 'bg-red-50 text-red-800' },
  error: { label: '执行异常', style: 'bg-amber-50 text-amber-900' },
}
const ATTEMPT = { returned: '已返回', timeout: '超时', error: '异常' }

function showAnswer(answer: PublicAnswer | null) {
  if (!answer) return '未返回'
  if (answer.value) return answer.value.replace('T', ' ').replace('+08:00', '（北京时间）')
  if (answer.status === 'insufficient_evidence') return '资料不足'
  if (answer.status === 'unsupported_question') return '超出公告问答范围'
  return '未提供事实值'
}

function AcceptanceRow({ result, sources }: { result: ProcurementResult; sources: ProcurementCase['sources'] }) {
  const test = result.case
  const outcome = OUTCOME[result.outcome]
  return (
    <li className="border-t border-slate-200 px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div>
          <p className="text-xs font-medium text-slate-500">{test.case_id} · {test.requirement_id}</p>
          <h3 className="mt-1 text-sm font-semibold text-slate-900">{test.title}</h3>
        </div>
        <span className={`rounded px-2 py-1 text-xs font-medium ${outcome.style}`}>{outcome.label}</span>
      </div>
      <p className="mt-2 break-words text-sm leading-6 text-slate-800">
        <span className="mr-2 text-slate-500">实际</span>{showAnswer(result.actual)}
      </p>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
        {result.actual?.evidence_ids.map((id) => {
          const source = sources.find((row) => row.evidence_id === id)
          return source ? (
            <a key={id} href={source.url} target="_blank" rel="noreferrer" className="text-xs text-blue-700 hover:underline">
              {source.title} ↗
            </a>
          ) : <span key={id} className="break-all text-xs text-red-700">{id}</span>
        })}
        <details className="basis-full text-xs text-slate-600">
          <summary className="cursor-pointer text-slate-600 hover:text-blue-700">查看输入与核对记录</summary>
          <div className="mt-2 space-y-1 break-words rounded-md bg-slate-50 px-3 py-2.5 leading-5">
            <p>{test.question}</p>
            <p>{test.project_id} · 截至 {test.as_of}（北京时间）</p>
            <p>预期 · {showAnswer(test.expected)}</p>
            {result.attempts.map((attempt, index) => (
              <p key={index}>尝试 {index + 1} · {ATTEMPT[attempt.status]} · {attempt.elapsed_ms.toFixed(2)} ms {attempt.detail}</p>
            ))}
            {result.issues.map((issue, index) => <p key={index} className="text-red-700">{issue}</p>)}
            {result.reviewed.map((source) => (
              <p key={source.evidence_id}>
                复核 · <a href={source.url} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">{source.title}</a>
                <span className="ml-1">{source.locator}</span>
              </p>
            ))}
          </div>
        </details>
      </div>
    </li>
  )
}

function CaseSidebar({ caseInfo, session }: { caseInfo: ProcurementCase; session: ProcurementSession | null }) {
  return (
    <aside className="min-w-0 space-y-4" aria-label="项目证据与执行轨迹">
      <Card title="官方公告依据">
        <ul className="divide-y divide-slate-100">
          {caseInfo.sources.map((source) => (
            <li key={source.evidence_id} className="space-y-2 py-3 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <a href={source.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-blue-700 hover:underline">
                  {source.title} ↗
                </a>
                <time dateTime={source.published_at} className="text-xs tabular-nums text-slate-500">
                  {source.published_at.slice(0, 10)}
                </time>
              </div>
              <details className="text-xs leading-5 text-slate-600">
                <summary className="cursor-pointer hover:text-blue-700">查看原文定位</summary>
                <p className="mt-1 font-medium">{source.locator}</p>
                <p className="mt-1">{source.excerpt}</p>
              </details>
            </li>
          ))}
        </ul>
        <p className="mt-4 border-t border-slate-100 pt-3 text-xs leading-5 text-slate-500">
          本地快照 {session?.snapshot_version ?? caseInfo.snapshot_version} · 北京时间
        </p>
      </Card>

      <Card title="智能体工作流">
        <ol className="space-y-3 text-sm text-slate-700">
          {([
            ['discovery', '需求澄清'],
            ['solution', '方案设计'],
            ['verification', 'PoC 验证'],
          ] as const).map(([step, label]) => {
            const waiting = step === 'discovery' && session?.status === 'need_clarification'
            const ran = session?.trace.some((event) => event.step === step)
            return (
              <li key={step} className="flex justify-between gap-2">
                <span>{label}</span>
                <span className={waiting ? 'text-xs text-amber-700' : 'text-xs text-slate-500'}>
                  {waiting ? '等待答复' : ran ? '已执行' : '待执行'}
                </span>
              </li>
            )
          })}
        </ol>
        {!!session?.trace.length && (
          <details className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-600">
            <summary className="cursor-pointer hover:text-blue-700">查看执行轨迹</summary>
            <ol className="mt-3 space-y-3 leading-5">
              {session.trace.map((event, index) => (
                <li key={index}>
                  <time dateTime={event.ts} className="font-mono text-slate-500">{event.ts.slice(11, 19)}</time>
                  <p>{event.case_id ? `${event.case_id} · ` : ''}{event.note}</p>
                </li>
              ))}
            </ol>
          </details>
        )}
      </Card>
    </aside>
  )
}

export default function Procurement() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const [caseInfo, setCaseInfo] = useState<ProcurementCase | null>(null)
  const [loadedSession, setSession] = useState<ProcurementSession | null>(null)
  const [input, setInput] = useState('')
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [caseError, setCaseError] = useState('')
  const session = loadedSession?.session_id === sessionId ? loadedSession : null

  useEffect(() => {
    let active = true
    api.procurementCase().then((value) => {
      if (!active) return
      setCaseInfo(value)
      setInput(value.sample_input)
    }).catch((err) => { if (active) setCaseError(String(err)) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    setError('')
    setAnswer('')
    if (!sessionId) return
    let active = true
    api.procurementSession(sessionId).then((value) => {
      if (active) setSession(value)
    }).catch((err) => { if (active) setError(String(err)) })
    return () => { active = false }
  }, [sessionId])

  async function start(event: FormEvent) {
    event.preventDefault()
    if (!caseInfo || !input.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      const value = await api.startProcurement(caseInfo.case_id, input.trim())
      setSession(value)
      navigate(`/procurement/${value.session_id}`)
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  async function reply(value: string) {
    const pending = session?.pending_question
    if (!session || !pending || !value.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      setSession(await api.resumeProcurement(session.session_id, pending.question_id, value.trim()))
      setAnswer('')
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  const passed = session?.results.filter((result) => result.outcome === 'passed').length ?? 0

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-5 sm:px-7 sm:py-7">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">企业采购 AI 售前 Copilot</h1>
        {session && !busy && (
          <Link to="/procurement" onClick={() => setInput(session.user_input)} className={SECONDARY}>用同一需求再演示</Link>
        )}
      </header>

      {(caseError || error) && (
        <p role="alert" className="break-words rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {caseError || error}
        </p>
      )}
      {!caseInfo && !caseError && <p role="status" className="text-sm text-slate-500">正在加载公开案例…</p>}

      {caseInfo && (
        <>
          <section aria-label="招标案例" className="flex flex-wrap items-start justify-between gap-4 rounded-xl bg-slate-900 px-5 py-5 text-white sm:px-7">
            <div>
              <p className="text-xs font-medium text-slate-300">{caseInfo.buyer}</p>
              <h2 className="mt-2 text-xl font-semibold">{caseInfo.title}</h2>
              <p className="mt-2 text-xs text-slate-300">采购编号 <span className="ml-1 font-mono">{caseInfo.project_id}</span></p>
            </div>
            {session && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-slate-300">{session.mode === 'rules' ? '规则演示' : '模型辅助'}</span>
                <StatusBadge status={session.status} />
              </div>
            )}
          </section>

          <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="min-w-0 space-y-4">
              {!sessionId && (
                <Card>
                  <form onSubmit={start} className="space-y-3">
                    <label htmlFor="procurement-input" className="block font-semibold text-slate-900">模拟客户需求</label>
                    <textarea id="procurement-input" className={FIELD} rows={3} maxLength={4000}
                      value={input} onChange={(event) => setInput(event.target.value)} disabled={busy} />
                    <button type="submit" disabled={busy || !input.trim()} className={PRIMARY}>
                      {busy ? '分析需求中…' : '开始澄清'}
                    </button>
                  </form>
                </Card>
              )}
              {sessionId && !session && !error && <p role="status" className="text-sm text-slate-500">正在读取会话…</p>}
              {session && (
                <>
                  <Card>
                    <h2 className="font-semibold text-slate-900">模拟客户需求</h2>
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{session.user_input}</p>
                    {session.clarifications.map((turn) => (
                      <div key={turn.question_id} className="mt-4 space-y-1 border-l-2 border-blue-200 pl-3 text-sm leading-6">
                        <p className="break-words text-slate-700">{turn.text}</p>
                        <p className="break-words text-slate-600"><span className="font-medium">模拟答复</span> · {turn.answer}</p>
                      </div>
                    ))}

                    {session.pending_question && (
                      <form className="mt-5 space-y-3 border-t border-slate-200 pt-4"
                        onSubmit={(event) => { event.preventDefault(); void reply(answer) }}>
                        <label htmlFor="procurement-answer" className="block text-sm font-semibold leading-6 text-slate-900">
                          {session.pending_question.text}
                        </label>
                        <div className="flex flex-wrap gap-2">
                          <button type="button" disabled={busy} onClick={() => void reply(PUBLIC_REPLY)} className={SECONDARY}>
                            只查公开进度
                          </button>
                          <button type="button" disabled={busy} onClick={() => void reply(INTERNAL_REPLY)} className={SECONDARY}>
                            公开进度＋内部审批
                          </button>
                        </div>
                        <textarea id="procurement-answer" rows={2} placeholder="输入模拟客户答复"
                          maxLength={2000} value={answer} onChange={(event) => setAnswer(event.target.value)} className={FIELD} disabled={busy} />
                        <button type="submit" disabled={busy || !answer.trim()} className={PRIMARY}>
                          {busy ? '正在处理答复…' : '提交澄清答复'}
                        </button>
                        {busy && <p role="status" className="text-xs text-slate-500">正在判断范围并执行适用的用例。</p>}
                      </form>
                    )}
                    {session.status === 'running' && <p role="status" className="mt-3 text-sm text-slate-500">会话正在执行，刷新可读取最新状态。</p>}
                  </Card>

                  {session.plan && (
                    <Card>
                      <h2 className="font-semibold text-slate-900">
                        {session.scope === 'public_and_internal' ? '公开进度与内部审批' : '仅公开进度'}
                      </h2>
                      <p className="mt-2 break-words text-sm leading-6 text-slate-600">{session.plan.summary}</p>
                      <ul className="mt-3 space-y-2 text-sm text-slate-700">
                        {session.plan.requirements.map((item) => (
                          <li key={item.requirement_id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                            <span className="font-mono text-xs text-slate-500">{item.requirement_id}</span>
                            <span>{item.description}</span>
                            {item.scope_status === 'pending_integration' && (
                              <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">待联调／未执行</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </Card>
                  )}

                  {session.status === 'completed' && (
                    <section aria-labelledby="procurement-results" className="rounded-lg border border-slate-200 bg-white">
                      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                        <div>
                          <h2 id="procurement-results" className="font-semibold text-slate-900">公开用例验收</h2>
                          <p className="mt-1 text-sm text-slate-600">通过 {passed} / 已执行 {session.results.length}</p>
                        </div>
                        <a className={SECONDARY} href={api.procurementReport(session.session_id)}>下载验收报告</a>
                      </div>
                      <ul>
                        {session.results.map((result) => (
                          <AcceptanceRow key={result.case.case_id} result={result} sources={caseInfo.sources} />
                        ))}
                      </ul>
                    </section>
                  )}

                  {!!session.plan?.integration_checks.length && (
                    <Card>
                      <h2 className="font-semibold text-slate-900">内部审批联调清单</h2>
                      <ul className="mt-3 divide-y divide-slate-100">
                        {session.plan.integration_checks.map((check) => (
                          <li key={check.dependency} className="space-y-1 py-3 text-sm leading-6 text-slate-700 first:pt-0 last:pb-0">
                            <h3 className="font-semibold text-slate-900">{check.dependency}</h3>
                            <p>{check.needed}</p>
                            <p><span className="text-slate-500">联调用例 · </span>{check.scenario}</p>
                            <p><span className="text-slate-500">预期 · </span>{check.expected}</p>
                          </li>
                        ))}
                      </ul>
                    </Card>
                  )}
                </>
              )}
            </div>
            <CaseSidebar caseInfo={caseInfo} session={session} />
          </div>
        </>
      )}
    </div>
  )
}
