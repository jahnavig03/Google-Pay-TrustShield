import { useMutation } from "@tanstack/react-query";
import { useCallback, useLayoutEffect, useRef, useState, type FormEvent } from "react";

import demo1 from "../../../shared/contracts/fixtures/demo1_payment_85k.json";
import { describeError, type PaymentRiskRequest, type PaymentRiskResponse } from "../api/client";
import { DECISION_TONE, ErrorNotice, Icon, Spinner, formatRupees } from "../components/ui";
import { QrScanner, type QrSample } from "../qr/QrScanner";
import { hostOf, parseQr, type ParsedQr } from "../qr/upi";
import { usePageRole, useRole } from "../role";

type FormState = Omit<
  PaymentRiskRequest,
  "transaction_id" | "currency" | "attachment_uri" | "qr"
>;
type UpiQr = Extract<ParsedQr, { kind: "upi" }>;
type OtherQr = Extract<ParsedQr, { kind: "not_upi" }>;

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
    label: "Demo 1 · ₹85k scam",
    hint: "₹85,000 'account blocked' scam: scam SMS, new payee, new device",
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
    label: "Rent ₹25k",
    hint: "₹25,000 rent to a long-standing landlord: large but genuine",
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
    label: "Everyday ₹40",
    hint: "₹40 at a tea stall: a normal payment",
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

/** Grow a textarea to fit its text (no inner scrollbar); CSS lets it also fill spare height. */
function useAutoHeight(value: string) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight + 2}px`; // + borders
  }, [value]);
  return ref;
}

export function PayPage() {
  usePageRole("customer");
  const { api } = useRole();
  const [form, setForm] = useState<FormState>(PRESETS[0].form);
  const [chosenAction, setChosenAction] = useState<string | null>(null);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [qr, setQr] = useState<UpiQr | null>(null);
  const [otherQr, setOtherQr] = useState<OtherQr | null>(null);
  const messageRef = useAutoHeight(form.message_context ?? "");

  const evaluate = useMutation({
    mutationFn: (body: PaymentRiskRequest) => api.evaluatePayment(body),
    onMutate: () => setChosenAction(null),
  });

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  const onQr = useCallback(
    (text: string, sample?: QrSample) => {
      setScannerOpen(false);
      evaluate.reset();
      const parsed = parseQr(text);
      if (parsed.kind === "not_upi") {
        setQr(null);
        setOtherQr(parsed);
        return;
      }
      setOtherQr(null);
      setQr(parsed);
      setForm((prev) => ({
        ...prev,
        payee_vpa: parsed.payeeVpa,
        // QR amount if fixed; else the sample's, else blank so the user types it.
        amount: parsed.amount ?? sample?.scenario?.amount ?? 0,
        // A real scan is usually a first payment to this UPI ID; samples carry their story.
        beneficiary_age_minutes: sample?.scenario?.beneficiary_age_minutes ?? 0,
        payer_id: sample?.scenario?.payer_id ?? prev.payer_id,
        device_changed: sample ? false : prev.device_changed,
        location_changed: sample ? false : prev.location_changed,
        message_context: sample ? "" : prev.message_context,
      }));
    },
    [evaluate],
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    evaluate.mutate({
      ...form,
      transaction_id: newTransactionId(),
      currency: "INR",
      message_context: form.message_context?.trim() ? form.message_context : null,
      qr: qr
        ? {
            raw: qr.raw,
            payee_name: qr.payeeName ?? null,
            amount: qr.amount ?? null,
            merchant_code: qr.merchantCode ?? null,
          }
        : null,
    });
  }

  return (
    <section className="page">
      <header className="page-header compact">
        <h1>Payment simulator</h1>
        <p className="muted">
          Try a UPI payment or scan a QR. TrustShield checks it before it goes through.
        </p>
      </header>

      <div className="two-col">
        <form className="card form dense fill-screen" onSubmit={submit} aria-label="Payment details">
          <fieldset className="preset-row">
            <legend>Try an example</legend>
            {PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                className="chip"
                title={preset.hint}
                onClick={() => {
                  setForm(preset.form);
                  setQr(null);
                  setOtherQr(null);
                  evaluate.reset();
                }}
              >
                {preset.label}
              </button>
            ))}
          </fieldset>

          {qr && (
            <div className="qr-card" role="status" aria-label="From QR code">
              <Icon name="qr_code_2" className="qr-card-icon" />
              <div className="qr-card-body">
                <strong>{qr.payeeName ?? "No name in QR"}</strong>
                <span className="muted small">
                  {qr.payeeVpa}
                  {qr.amount ? ` · ${formatRupees(qr.amount)}` : ""}
                  {qr.merchantCode ? " · shop QR" : ""}
                </span>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Remove QR"
                onClick={() => setQr(null)}
              >
                <Icon name="close" />
              </button>
            </div>
          )}

          <div className="field-grid">
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
              Recipient added (min ago)
              <input
                type="number"
                min={0}
                required
                value={form.beneficiary_age_minutes}
                onChange={(e) => update("beneficiary_age_minutes", Number(e.target.value))}
              />
            </label>
            <div className="field">
              <div className="field-label-row">
                <label htmlFor="payee-vpa">Pay to (UPI ID)</label>
                <button
                  type="button"
                  className="scan-chip"
                  onClick={() => setScannerOpen(true)}
                  aria-label="Scan QR"
                  title="Scan or upload a QR code"
                >
                  <Icon name="qr_code_scanner" />
                  Scan QR
                </button>
              </div>
              <input
                id="payee-vpa"
                required
                value={form.payee_vpa}
                placeholder="name@synthbank"
                onChange={(e) => {
                  update("payee_vpa", e.target.value.trim());
                  setQr(null); // typed by hand: no longer from the QR
                }}
              />
            </div>
            <label>
              Payer (demo account)
              <input
                required
                value={form.payer_id}
                onChange={(e) => update("payer_id", e.target.value.trim())}
              />
            </label>
          </div>
          <div className="checks inline">
            <label className="check">
              <input
                type="checkbox"
                checked={form.device_changed ?? false}
                onChange={(e) => update("device_changed", e.target.checked)}
              />
              New device
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={form.location_changed ?? false}
                onChange={(e) => update("location_changed", e.target.checked)}
              />
              New location
            </label>
          </div>
          <label className="grow">
            Message that asked you to pay (optional)
            <textarea
              ref={messageRef}
              className="message-box"
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
          {otherQr && <NotAPaymentQr qr={otherQr} onDismiss={() => setOtherQr(null)} />}
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
          {evaluate.isIdle && !otherQr && (
            <div className="card empty">
              <p className="muted">Pick an example, scan a QR, or fill in the form, then press Pay.</p>
            </div>
          )}
        </div>
      </div>

      {scannerOpen && <QrScanner onResult={onQr} onClose={() => setScannerOpen(false)} />}
    </section>
  );
}

/** Checked on the device: a QR that isn't a UPI payment is never something to pay from. */
function NotAPaymentQr({ qr, onDismiss }: { qr: OtherQr; onDismiss: () => void }) {
  const what =
    qr.reason === "link"
      ? `It opens a website (${hostOf(qr.raw)}), not a payment.`
      : qr.reason === "upi_other"
        ? "It's a UPI request that isn't a normal payment to a shop or person."
        : qr.reason === "no_payee"
          ? "It doesn't contain a valid UPI ID to pay."
          : "It contains plain text, not a payment.";
  return (
    <article className="card sheet tone-danger" aria-label="QR check result">
      <div className="result-head">
        <Icon name="gpp_bad" className="result-icon" />
        <h2>This QR code isn't a payment</h2>
      </div>
      <p className="sheet-message">
        {what} Don't pay, sign in, or share any details from it. If someone sent it to you, check
        with them through a contact you already trust.
      </p>
      <div className="actions">
        <button type="button" className="secondary" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    </article>
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

      {(result.top_signals?.length ?? 0) > 0 && (
        <>
          <h3>{allowed ? "What we checked" : "Why we're checking"}</h3>
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
