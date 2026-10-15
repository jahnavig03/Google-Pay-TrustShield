import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import {
  ApiError,
  describeError,
  type AnalystAction,
  type Case,
  type CaseAnswer,
  type CaseSummary,
} from "../api/client";
import {
  Badge,
  DECISION_TONE,
  ErrorNotice,
  Icon,
  Spinner,
  formatDateTime,
  formatRupees,
  humanize,
  timeAgo,
} from "../components/ui";
import { RISK_BANDS } from "../config";
import { usePageRole, useRole } from "../role";
import { useSession } from "../session";

const NOT_COVERED = "not covered by policy";
const LIST_REFRESH_MS = 10_000;

type Filter = "all" | "review" | "escalated" | "resolved";
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "review", label: "Needs review" },
  { id: "escalated", label: "Escalated" },
  { id: "resolved", label: "Resolved" },
];

function bucket(status: string): Exclude<Filter, "all"> {
  if (status === "escalated") return "escalated";
  if (status === "closed" || status === "customer_outreach") return "resolved";
  return "review";
}

const ACTIONS: { action: AnalystAction; label: string; icon: string; tone: string }[] = [
  { action: "approve_escalation", label: "Approve escalation", icon: "gavel", tone: "danger" },
  { action: "customer_outreach", label: "Customer outreach", icon: "call", tone: "secondary" },
  { action: "close", label: "Close case", icon: "task_alt", tone: "secondary" },
];

export function AnalystPage() {
  usePageRole("analyst");
  const { caseId } = useParams();
  const { api, role } = useRole();
  const cases = useQuery({
    queryKey: ["cases", role],
    queryFn: () => api.listCases(),
    refetchInterval: LIST_REFRESH_MS,
    // Only the analyst role may read cases; the page sets it on open.
    enabled: role === "analyst",
  });
  const list = cases.data?.cases ?? [];

  return (
    <section className="page">
      <header className="page-header console-header">
        <div>
          <h1>Case queue</h1>
          <p className="muted">
            Cases open when a payment scores R ≥ {RISK_BANDS.stepUp.toFixed(2)}. Nothing is
            escalated without your approval.
          </p>
        </div>
        {cases.dataUpdatedAt > 0 && (
          <span className="muted small refresh-note">
            <Icon name="sync" /> Updated {new Date(cases.dataUpdatedAt).toLocaleTimeString("en-IN")}
          </span>
        )}
      </header>

      <Kpis cases={list} />

      <div className="analyst-layout">
        <CaseQueue
          cases={list}
          selectedId={caseId}
          loading={cases.isLoading}
          error={cases.isError ? cases.error : null}
        />
        {caseId ? (
          <CaseDetail key={caseId} caseId={caseId} />
        ) : (
          <div className="card empty">
            <Icon name="manage_search" className="empty-icon" />
            <p className="muted">Select a case to review its evidence and decide.</p>
          </div>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ KPIs */

function Kpis({ cases }: { cases: CaseSummary[] }) {
  const review = cases.filter((c) => bucket(c.status) === "review").length;
  const escalated = cases.filter((c) => bucket(c.status) === "escalated").length;
  const resolved = cases.filter((c) => bucket(c.status) === "resolved").length;
  const top = cases.reduce<CaseSummary | null>(
    (best, c) => (!best || c.risk_score > best.risk_score ? c : best),
    null,
  );
  return (
    <div className="kpis" role="list" aria-label="Queue summary">
      <Kpi icon="pending_actions" tone="warning" label="Needs review" value={review} />
      <Kpi icon="gavel" tone="danger" label="Escalated" value={escalated} />
      <Kpi icon="task_alt" tone="ok" label="Resolved" value={resolved} />
      <Kpi
        icon="speed"
        tone="neutral"
        label="Highest risk"
        value={top ? top.risk_score.toFixed(3) : "—"}
        hint={top ? formatRupees(top.amount) : undefined}
      />
    </div>
  );
}

function Kpi(props: { icon: string; tone: string; label: string; value: ReactNode; hint?: string }) {
  return (
    <div className={`kpi tone-${props.tone}`} role="listitem">
      <Icon name={props.icon} className="kpi-icon" />
      <div>
        <div className="kpi-value">{props.value}</div>
        <div className="kpi-label">
          {props.label}
          {props.hint && <span className="muted"> · {props.hint}</span>}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ queue */

function CaseQueue(props: {
  cases: CaseSummary[];
  selectedId?: string;
  loading: boolean;
  error: unknown;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return props.cases.filter(
      (c) =>
        (filter === "all" || bucket(c.status) === filter) &&
        (!q || c.case_id.toLowerCase().includes(q) || c.payee_vpa.toLowerCase().includes(q)),
    );
  }, [props.cases, filter, query]);

  return (
    <aside className="card case-list" aria-label="Cases">
      <div className="chips" role="group" aria-label="Filter cases">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={filter === f.id ? "chip selected" : "chip"}
            aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}
          >
            {filter === f.id && <Icon name="check" />}
            {f.label}
          </button>
        ))}
      </div>
      <label className="search">
        <Icon name="search" />
        <input
          aria-label="Search cases"
          placeholder="Search case or UPI ID"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>

      {props.loading && <Spinner label="Loading cases…" />}
      {props.error != null && <ErrorNotice>{describeError(props.error)}</ErrorNotice>}
      {!props.loading && props.cases.length === 0 && !props.error && (
        <p className="muted small">No cases yet. A payment scoring high opens one automatically.</p>
      )}
      {props.cases.length > 0 && shown.length === 0 && (
        <p className="muted small">No cases match this filter.</p>
      )}

      <ul>
        {shown.map((c) => (
          <li key={c.case_id}>
            <Link
              to={`/analyst/${encodeURIComponent(c.case_id)}`}
              className={c.case_id === props.selectedId ? "case-row selected" : "case-row"}
              aria-current={c.case_id === props.selectedId ? "page" : undefined}
            >
              <span className="case-row-top">
                <strong>{formatRupees(c.amount)}</strong>
                <Badge tone={DECISION_TONE[c.decision] ?? "neutral"}>{humanize(c.decision)}</Badge>
              </span>
              <span className="muted small ellipsis">{c.payee_vpa}</span>
              <span className="mini-meter" aria-hidden="true">
                <span style={{ width: `${Math.round(c.risk_score * 100)}%` }} />
              </span>
              <span className="muted small case-row-meta">
                <span>R {c.risk_score.toFixed(3)}</span>
                <span>{humanize(c.status)}</span>
                <span>{timeAgo(c.created_at)}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}

/* ------------------------------------------------------------------ detail */

type Tab = "overview" | "timeline" | "accounts" | "evidence" | "decision";
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "insights" },
  { id: "timeline", label: "Timeline", icon: "timeline" },
  { id: "accounts", label: "Accounts", icon: "hub" },
  { id: "evidence", label: "Evidence & Q&A", icon: "menu_book" },
  { id: "decision", label: "Decision", icon: "gavel" },
];

function CaseDetail({ caseId }: { caseId: string }) {
  const { api, role } = useRole();
  const [tab, setTab] = useState<Tab>("overview");
  const baseId = useId();
  const detail = useQuery({
    queryKey: ["case", caseId, role],
    queryFn: () => api.getCase(caseId),
    enabled: role === "analyst",
  });

  if (role !== "analyst") return null;
  if (detail.isPending) return <Spinner label="Loading case…" />;
  if (detail.isError) return <ErrorNotice>{describeError(detail.error)}</ErrorNotice>;
  const c = detail.data;

  return (
    <article className="case-detail" aria-label={`Case ${c.case_id}`}>
      <div className="card case-hero">
        <div className="case-title">
          <h2>{c.case_id}</h2>
          <Badge tone={DECISION_TONE[c.decision] ?? "neutral"}>{humanize(c.decision)}</Badge>
          <Badge tone="neutral">{humanize(c.status)}</Badge>
        </div>
        <RiskMeter score={c.risk_score} />
        <dl className="facts">
          <div>
            <dt>Risk type</dt>
            <dd>{humanize(c.risk_type)}</dd>
          </div>
          <div>
            <dt>Opened</dt>
            <dd>{formatDateTime(c.created_at)}</dd>
          </div>
          <div>
            <dt>Transaction</dt>
            <dd>{c.transaction_id}</dd>
          </div>
        </dl>
        {c.recommended_action && !c.analyst_decision && (
          <p className="notice notice-info recommend">
            <Icon name="lightbulb" /> Recommended: <strong>{humanize(c.recommended_action)}</strong>
          </p>
        )}
      </div>

      <div className="card tabs-card">
        <div className="tabs" role="tablist" aria-label="Case sections">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`${baseId}-${t.id}-tab`}
              aria-controls={`${baseId}-${t.id}-panel`}
              aria-selected={tab === t.id}
              className={tab === t.id ? "tab active" : "tab"}
              onClick={() => setTab(t.id)}
            >
              <Icon name={t.icon} />
              {t.label}
            </button>
          ))}
        </div>
        <div
          role="tabpanel"
          id={`${baseId}-${tab}-panel`}
          aria-labelledby={`${baseId}-${tab}-tab`}
          className="tab-panel"
        >
          {tab === "overview" && <Overview c={c} />}
          {tab === "timeline" && <Timeline c={c} />}
          {tab === "accounts" && <Accounts c={c} />}
          {tab === "evidence" && <Evidence c={c} />}
          {tab === "decision" && <DecisionPanel current={c} />}
        </div>
      </div>
    </article>
  );
}

function RiskMeter({ score }: { score: number }) {
  const { warn, stepUp, hold } = RISK_BANDS;
  const pct = (x: number) => `${Math.min(100, Math.max(0, x * 100))}%`;
  return (
    <div className="risk-meter" role="img" aria-label={`Risk score ${score.toFixed(3)} out of 1`}>
      <div className="risk-meter-head">
        <span className="risk-score">{score.toFixed(3)}</span>
        <span className="muted small">risk score R</span>
      </div>
      <div className="risk-track">
        <span className="band band-allow" style={{ width: pct(warn) }} />
        <span className="band band-warn" style={{ width: pct(stepUp - warn) }} />
        <span className="band band-stepup" style={{ width: pct(hold - stepUp) }} />
        <span className="band band-hold" style={{ width: pct(1 - hold) }} />
        <span className="risk-marker" style={{ left: pct(score) }} />
      </div>
      <div className="risk-legend small muted">
        <span>Allow</span>
        <span>Warn ≥ {warn.toFixed(2)}</span>
        <span>Step-up ≥ {stepUp.toFixed(2)}</span>
        <span>Hold ≥ {hold.toFixed(2)}</span>
      </div>
    </div>
  );
}

function Overview({ c }: { c: Case }) {
  const signals = c.top_signals ?? [];
  const max = Math.max(...signals.map((s) => Math.abs(s.contribution)), 1);
  return (
    <div className="overview">
      <p>{c.summary}</p>
      <h3>Why it was flagged</h3>
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
    </div>
  );
}

function Timeline({ c }: { c: Case }) {
  return (
    <ol className="timeline">
      {(c.timeline ?? []).map((event, i) => (
        <li key={`${event.timestamp}-${i}`}>
          <span className="muted small">{formatDateTime(event.timestamp)}</span>
          <strong>{humanize(event.event_type)}</strong>
          <span>{event.description}</span>
        </li>
      ))}
    </ol>
  );
}

const ENTITY_ICON: Record<string, string> = {
  account: "account_circle",
  vpa: "alternate_email",
  device: "smartphone",
  phone: "call",
  merchant: "storefront",
};

function Accounts({ c }: { c: Case }) {
  const entities = c.linked_entities ?? [];
  if (entities.length === 0) return <p className="muted">No linked accounts recorded.</p>;
  return (
    <ul className="entities">
      {entities.map((e) => (
        <li key={`${e.entity_type}-${e.entity_id}`} className="entity">
          <Icon name={ENTITY_ICON[e.entity_type] ?? "link"} className="entity-icon" />
          <div>
            <code>{e.entity_id}</code>
            <div className="muted small">
              {humanize(e.entity_type)} · {humanize(e.relation)}
            </div>
            {e.risk_note && <div className="small entity-note">{e.risk_note}</div>}
          </div>
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

function Evidence({ c }: { c: Case }) {
  return (
    <div>
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
      <AskBox caseId={c.case_id} />
    </div>
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
    <section className="ask" aria-label="Ask about this case">
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
  const { analystId } = useSession();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const decide = useMutation({
    mutationFn: (action: AnalystAction) =>
      api.decideCase(current.case_id, action, analystId ?? "", reason.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case", current.case_id] });
      queryClient.invalidateQueries({ queryKey: ["cases"] });
      setReason("");
    },
  });
  const decided = current.analyst_decision;
  const conflict = decide.error instanceof ApiError && decide.error.status === 409;

  return (
    <div className="decision-form">
      {decided && (
        <p className="notice notice-info">
          {humanize(decided.action)} by {decided.analyst_id} on {formatDateTime(decided.decided_at)}
          . Audit {decided.audit_id ?? "—"}.
        </p>
      )}
      <p className="muted small">
        Deciding as <strong>{analystId}</strong>. Your reason is written to the audit log.
      </p>
      <label>
        Reason (required)
        <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="actions">
        {ACTIONS.map((a) => (
          <button
            key={a.action}
            type="button"
            className={a.tone === "danger" ? "danger" : "secondary"}
            disabled={decide.isPending || !reason.trim() || !analystId}
            onClick={() => decide.mutate(a.action)}
          >
            <Icon name={a.icon} />
            {a.label}
          </button>
        ))}
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
    </div>
  );
}
