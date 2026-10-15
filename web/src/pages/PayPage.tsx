import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import demo1 from "../../../shared/contracts/fixtures/demo1_payment_85k.json";
import { describeError, type PaymentRiskRequest, type PaymentRiskResponse } from "../api/client";
import { DECISION_TONE, ErrorNotice, Icon, Spinner } from "../components/ui";
import { usePageRole, useRole } from "../role";

type FormState = Omit<PaymentRiskRequest, "transaction_id" | "currency" | "attachment_uri">;

const EMPTY: FormState = {
  amount: 0,
  payer_id: "payer_demo_001",
  payee_vpa: "",
  beneficiary_age_minutes: 0,
  device_changed: false,
  location_changed: false,
  message_context: "",
};

const MINUTES_PER_YEAR = 60 * 24 * 365;

/** Demo presets. All synthetic; payer ids and VPAs exist in the mock feature store. */
const PRESETS: { id: string; label: string; hint: string; form: FormState }[] = [
  {
    id: "demo1",
    label: "Demo 1: ₹85,000 'account blocked'",
    hint: "Scam SMS, new payee, new device",
    form: {
      ...EMPTY,
      amount: demo1.request.amount,
      payer_id: demo1.request.payer_id,
      payee_vpa: demo1.request.payee_vpa,
      beneficiary_age_minutes: demo1.request.beneficiary_age_minutes,
      device_changed: demo1.request.device_changed,
      location_changed: demo1.request.location_changed,
      message_context: demo1.request.message_context,
    },
  },
  {
    id: "rent",
    label: "Rent ₹25,000 to landlord",
    hint: "Large but genuine",
    form: {
      ...EMPTY,
      amount: 25000,
      payer_id: "payer_demo_002",
      payee_vpa: "landlord.sharma@synthbank",
      beneficiary_age_minutes: 400 * 24 * 60,
      message_context: "Reminder: rent of Rs 25,000 is due today. Thanks!",
    },
  },
  {
    id: "chai",
    label: "Everyday ₹40 at a tea stall",
    hint: "Normal payment",
    form: {
      ...EMPTY,
      amount: 40,
      payer_id: "payer_demo_003",
      payee_vpa: "chai.ramesh@synthbank",
      beneficiary_age_minutes: 2 * MINUTES_PER_YEAR,
    },
  },
];

const DECISION_ICON: Record<string, string> = {
  ALLOW: "check_circle",
  WARN: "info",
  STEP_UP_VERIFICATION: "warning",
  HOLD_AND_ESCALATE: "pan_tool",
};

const HEADLINE: Record<string, string> = {
  ALLOW: "This payment looks fine",
  WARN: "Take a moment before you pay",
  STEP_UP_VERIFICATION: "Please confirm a few details first",
  HOLD_AND_ESCALATE: "We've paused this payment for your safety",
};

function newTransactionId(): string {
  return `TXN-${Date.now()}`;
}

export function PayPage() {
  usePageRole("customer");
  const { api } = useRole();
  const [form, setForm] = useState<FormState>(PRESETS[0].form);
  const [chosenAction, setChosenAction] = useState<string | null>(null);

  const evaluate = useMutation({
    mutationFn: (body: PaymentRiskRequest) => api.evaluatePayment(body),
    onMutate: () => setChosenAction(null),
  });

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    evaluate.mutate({
      ...form,
      transaction_id: newTransactionId(),
      currency: "INR",
      message_context: form.message_context?.trim() ? form.message_context : null,
    });
  }

  return (
    <section className="page">
      <header className="page-header">
        <h1>Payment simulator</h1>
        <p className="muted">
          Try a UPI payment. TrustShield checks it before it goes through and explains why.
        </p>
      </header>

      <div className="two-col">
        <form className="card form" onSubmit={submit} aria-label="Payment details">
          <fieldset className="presets">
            <legend>Start from an example</legend>
            {PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                className="preset"
                onClick={() => {
                  setForm(preset.form);
                  evaluate.reset();
                }}
              >
                <strong>{preset.label}</strong>
                <span>{preset.hint}</span>
              </button>
            ))}
          </fieldset>

          <label>
            Amount (₹)
            <input
              type="number"
              min={1}
              step="any"
              required
              value={form.amount || ""}
              onChange={(e) => update("amount", Number(e.target.value))}
            />
          </label>
          <label>
            Pay to (UPI ID)
            <input
              required
              value={form.payee_vpa}
              placeholder="name@synthbank"
              onChange={(e) => update("payee_vpa", e.target.value.trim())}
            />
          </label>
          <label>
            Payer (demo account)
            <input
              required
              value={form.payer_id}
              onChange={(e) => update("payer_id", e.target.value.trim())}
            />
          </label>
          <label>
            Recipient added (minutes ago)
            <input
              type="number"
              min={0}
              required
              value={form.beneficiary_age_minutes}
              onChange={(e) => update("beneficiary_age_minutes", Number(e.target.value))}
            />
          </label>
          <div className="checks">
            <label className="check">
              <input
                type="checkbox"
                checked={form.device_changed ?? false}
                onChange={(e) => update("device_changed", e.target.checked)}
              />
              Paying from a new device
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={form.location_changed ?? false}
                onChange={(e) => update("location_changed", e.target.checked)}
              />
              Paying from a new location
            </label>
          </div>
          <label>
            Message that asked you to pay (optional)
            <textarea
              rows={4}
              value={form.message_context ?? ""}
              placeholder="Paste the SMS, chat or call notes here"
              onChange={(e) => update("message_context", e.target.value)}
            />
          </label>
          <button type="submit" className="primary" disabled={evaluate.isPending}>
            {evaluate.isPending ? "Checking…" : "Pay"}
          </button>
        </form>

        <div aria-live="polite">
          {evaluate.isPending && <Spinner label="Checking this payment…" />}
          {evaluate.isError && (
            <ErrorNotice>{describeError(evaluate.error, "customer")}</ErrorNotice>
          )}
          {evaluate.data && (
            <ResultSheet
              result={evaluate.data}
              chosenAction={chosenAction}
              onAction={setChosenAction}
            />
          )}
          {evaluate.isIdle && (
            <div className="card empty">
              <p className="muted">Pick an example or fill in the form, then press Pay.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function ResultSheet({
  result,
  chosenAction,
  onAction,
}: {
  result: PaymentRiskResponse;
  chosenAction: string | null;
  onAction: (label: string) => void;
}) {
  const allowed = result.decision === "ALLOW";
  return (
    <article
      className={`card sheet tone-${DECISION_TONE[result.decision] ?? "neutral"}`}
      aria-label="Payment check result"
    >
      <div className="result-head">
        <Icon name={DECISION_ICON[result.decision] ?? "info"} className="result-icon" />
        <h2>{HEADLINE[result.decision] ?? result.decision}</h2>
      </div>
      <p className="sheet-message">{result.customer_message}</p>

      {!allowed && (result.top_signals?.length ?? 0) > 0 && (
        <>
          <h3>Why we're checking</h3>
          <ul className="signals">
            {result.top_signals?.map((signal) => (
              <li key={signal.code}>
                <strong>{signal.label}</strong>
                <span>{signal.plain_explanation}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {(result.safe_actions?.length ?? 0) > 0 && (
        <div className="actions">
          {result.safe_actions?.map((action, i) => (
            <button
              key={action.code}
              type="button"
              className={i === 0 ? "primary" : "secondary"}
              onClick={() => onAction(action.label)}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
      {chosenAction && (
        <p className="notice notice-info" role="status">
          Simulated: “{chosenAction}”. No real payment was made.
        </p>
      )}

      {result.case_id && (
        <p className="muted small">
          A safety specialist will review this payment. Case reference {result.case_id}.
        </p>
      )}
      {result.audit_id && <p className="muted small">Check reference {result.audit_id}</p>}
    </article>
  );
}
