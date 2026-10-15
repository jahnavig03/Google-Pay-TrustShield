import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import {
  ApiError,
  describeError,
  type AnalystAction,
  type Case,
  type CaseAnswer,
} from "../api/client";
import {
  Badge,
  DECISION_TONE,
  ErrorNotice,
  RoleNotice,
  Spinner,
  formatDateTime,
  formatRupees,
  humanize,
} from "../components/ui";
import { usePageRole, useRole } from "../role";

const NOT_COVERED = "not covered by policy";
const LIST_REFRESH_MS = 10_000;

const ACTIONS: { action: AnalystAction; label: string; tone: string }[] = [
  { action: "approve_escalation", label: "Approve escalation", tone: "danger" },
  { action: "customer_outreach", label: "Customer outreach", tone: "secondary" },
  { action: "close", label: "Close case", tone: "secondary" },
];

export function AnalystPage() {
  const { caseId } = useParams();
  usePageRole("analyst");
  return (
    <section className="page">
      <header className="page-header">
        <h1>Analyst console</h1>
        <p className="muted">
          Cases open automatically when a payment scores R ≥ 0.70. Nothing is escalated without
          your approval.
        </p>
      </header>
      <RoleNotice needs="analyst" />
      <div className="analyst-layout">
        <CaseList selectedId={caseId} />
        {caseId ? (
          <CaseDetail caseId={caseId} />
        ) : (
          <div className="card empty">
            <p className="muted">Select a case to see its timeline, evidence and actions.</p>
          </div>
        )}
      </div>
    </section>
  );
}

function CaseList({ selectedId }: { selectedId?: string }) {
  const { api, role } = useRole();
  const cases = useQuery({
    queryKey: ["cases", role],
    queryFn: () => api.listCases(),
    refetchInterval: LIST_REFRESH_MS,
    // Only the analyst role may read cases. Without this guard, a nav click (which switches
    // the role before the route transition commits) briefly re-fetches with the wrong role.
    enabled: role === "analyst",
  });

  return (
    <aside className="card case-list" aria-label="Cases">
      <h2>Cases</h2>
      {cases.isLoading && <Spinner label="Loading cases…" />}
      {cases.isError && <ErrorNotice>{describeError(cases.error)}</ErrorNotice>}
      {cases.data && cases.data.cases.length === 0 && (
        <p className="muted">
          No cases yet. Run demo 1 in the <Link to="/pay">payment simulator</Link>.
        </p>
      )}
      <ul>
        {cases.data?.cases.map((c) => (
          <li key={c.case_id}>
            <Link
              to={`/analyst/${encodeURIComponent(c.case_id)}`}
              className={c.case_id === selectedId ? "case-row selected" : "case-row"}
              aria-current={c.case_id === selectedId ? "page" : undefined}
            >
              <span className="case-row-top">
                <strong>{formatRupees(c.amount)}</strong>
                <Badge tone={DECISION_TONE[c.decision] ?? "neutral"}>{humanize(c.decision)}</Badge>
              </span>
              <span className="muted small">
                {c.payee_vpa} · R {c.risk_score.toFixed(3)}
              </span>
              <span className="muted small">
                {humanize(c.status)} · {formatDateTime(c.created_at)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function CaseDetail({ caseId }: { caseId: string }) {
  const { api, role } = useRole();
  const detail = useQuery({
    queryKey: ["case", caseId, role],
    queryFn: () => api.getCase(caseId),
    enabled: role === "analyst",
  });

  if (role !== "analyst") return null; // RoleNotice above explains why
  if (detail.isPending) return <Spinner label="Loading case…" />;
  if (detail.isError) return <ErrorNotice>{describeError(detail.error)}</ErrorNotice>;
  const c = detail.data;

  return (
    <article className="case-detail" aria-label={`Case ${c.case_id}`}>
      <div className="card">
        <div className="case-title">
          <h2>{c.case_id}</h2>
          <Badge tone={DECISION_TONE[c.decision] ?? "neutral"}>{humanize(c.decision)}</Badge>
          <Badge tone="neutral">{humanize(c.status)}</Badge>
        </div>
        <p>{c.summary}</p>
        <dl className="facts">
          <div>
            <dt>Risk score</dt>
            <dd>{c.risk_score.toFixed(4)}</dd>
          </div>
          <div>
            <dt>Risk type</dt>
            <dd>{humanize(c.risk_type)}</dd>
          </div>
          <div>
            <dt>Recommended</dt>
            <dd>{c.recommended_action ? humanize(c.recommended_action) : "—"}</dd>
          </div>
          <div>
            <dt>Opened</dt>
            <dd>{formatDateTime(c.created_at)}</dd>
          </div>
        </dl>
      </div>

      <div className="detail-grid">
        <section className="card" aria-label="Top signals">
          <h3>Top signals</h3>
          <SignalBars signals={c.top_signals ?? []} />
        </section>
        <section className="card" aria-label="Timeline">
          <h3>Timeline</h3>
          <ol className="timeline">
            {(c.timeline ?? []).map((event, i) => (
              <li key={`${event.timestamp}-${i}`}>
                <span className="muted small">{formatDateTime(event.timestamp)}</span>
                <strong>{humanize(event.event_type)}</strong>
                <span>{event.description}</span>
              </li>
            ))}
          </ol>
        </section>
        <section className="card" aria-label="Linked entities">
          <h3>Linked accounts and devices</h3>
          <ul className="entities">
            {(c.linked_entities ?? []).map((e) => (
              <li key={`${e.entity_type}-${e.entity_id}`}>
                <Badge tone="neutral">{e.entity_type}</Badge> <code>{e.entity_id}</code>{" "}
                <span className="muted">({humanize(e.relation)})</span>
                {e.risk_note && <div className="small">{e.risk_note}</div>}
              </li>
            ))}
          </ul>
        </section>
        <section className="card" aria-label="Policy evidence">
          <h3>Policy evidence</h3>
          {(c.citations ?? []).length === 0 ? (
            <p className="muted small">
              No policy passages attached yet. Evidence IDs: {(c.evidence_ids ?? []).join(", ")}
            </p>
          ) : (
            <Citations citations={c.citations ?? []} />
          )}
          {(c.missing_evidence ?? []).length > 0 && (
            <>
              <h4>Missing evidence</h4>
              <ul className="small">
                {c.missing_evidence?.map((m) => <li key={m}>{m}</li>)}
              </ul>
            </>
          )}
        </section>
      </div>

      <AskBox caseId={c.case_id} />
      <DecisionPanel current={c} />
    </article>
  );
}

function SignalBars({ signals }: { signals: NonNullable<Case["top_signals"]> }) {
  const max = Math.max(...signals.map((s) => Math.abs(s.contribution)), 1);
  return (
    <ul className="signal-bars">
      {signals.map((s) => (
        <li key={s.code}>
          <div className="signal-bar-head">
            <strong>{s.label}</strong>
            <span className="muted small">w·x {s.contribution.toFixed(2)}</span>
          </div>
          <div className="bar" aria-hidden="true">
            <span style={{ width: `${(Math.abs(s.contribution) / max) * 100}%` }} />
          </div>
          <span className="small">{s.plain_explanation}</span>
        </li>
      ))}
    </ul>
  );
}

function Citations({ citations }: { citations: NonNullable<CaseAnswer["citations"]> }) {
  return (
    <ul className="citations">
      {citations.map((cite) => (
        <li key={cite.evidence_id}>
          <Badge tone="neutral">{cite.evidence_id}</Badge> <strong>{cite.title}</strong>
          <blockquote>{cite.snippet}</blockquote>
          {cite.uri && <span className="muted small">{cite.uri}</span>}
        </li>
      ))}
    </ul>
  );
}

function AskBox({ caseId }: { caseId: string }) {
  const { api } = useRole();
  const [question, setQuestion] = useState("Why was this payment flagged?");
  const [history, setHistory] = useState<{ question: string; answer: CaseAnswer }[]>([]);
  const ask = useMutation({
    mutationFn: (q: string) => api.askCase(caseId, q),
    onSuccess: (answer, q) => setHistory((prev) => [{ question: q, answer }, ...prev]),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (question.trim()) ask.mutate(question.trim());
  }

  return (
    <section className="card" aria-label="Ask about this case">
      <h3>Ask why</h3>
      <form className="inline-form" onSubmit={submit}>
        <input
          aria-label="Question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button type="submit" className="secondary" disabled={ask.isPending}>
          {ask.isPending ? "Asking…" : "Ask"}
        </button>
      </form>
      {ask.isError && <ErrorNotice>{describeError(ask.error)}</ErrorNotice>}
      {history.map((item, i) => (
        <div key={i} className="qa">
          <p className="muted small">Q: {item.question}</p>
          {item.answer.answer.trim().toLowerCase() === NOT_COVERED ? (
            <p className="answer-not-covered">
              Not covered by policy: no retrieved policy passage answers this question.
            </p>
          ) : (
            <p>{item.answer.answer}</p>
          )}
          {(item.answer.citations ?? []).length > 0 && (
            <Citations citations={item.answer.citations ?? []} />
          )}
        </div>
      ))}
    </section>
  );
}

function DecisionPanel({ current }: { current: Case }) {
  const { api } = useRole();
  const queryClient = useQueryClient();
  const [analystId, setAnalystId] = useState("analyst_demo_01");
  const [reason, setReason] = useState("");
  const decide = useMutation({
    mutationFn: (action: AnalystAction) =>
      api.decideCase(current.case_id, action, analystId, reason.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case", current.case_id] });
      queryClient.invalidateQueries({ queryKey: ["cases"] });
      setReason("");
    },
  });
  const decided = current.analyst_decision;
  const conflict = decide.error instanceof ApiError && decide.error.status === 409;

  return (
    <section className="card" aria-label="Analyst decision">
      <h3>Decision</h3>
      {decided && (
        <p className="notice notice-info">
          {humanize(decided.action)} by {decided.analyst_id} on{" "}
          {formatDateTime(decided.decided_at)}. Audit {decided.audit_id ?? "—"}.
        </p>
      )}
      <div className="decision-form">
        <label>
          Analyst ID
          <input value={analystId} onChange={(e) => setAnalystId(e.target.value)} />
        </label>
        <label>
          Reason (required, goes into the audit log)
          <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <div className="actions">
          {ACTIONS.map((a) => (
            <button
              key={a.action}
              type="button"
              className={a.tone === "danger" ? "danger" : "secondary"}
              disabled={decide.isPending || !reason.trim() || !analystId.trim()}
              onClick={() => decide.mutate(a.action)}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>
      {decide.isError && (
        <ErrorNotice>
          {conflict
            ? "Governance: this action needs a recorded analyst approval before it can run."
            : describeError(decide.error)}
        </ErrorNotice>
      )}
      {decide.data && (
        <p className="notice notice-ok" role="status">
          Recorded: case is now {humanize(decide.data.status)}. Audit{" "}
          {decide.data.decision.audit_id ?? "—"}.
        </p>
      )}
    </section>
  );
}
