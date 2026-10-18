import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { describeError, type PaymentRiskRequest, type PaymentRiskResponse } from "../api/client";
import { ShieldMark } from "../components/Brand";
import { ErrorNotice, Icon, formatRupees } from "../components/ui";
import { QrScanner, type QrSample } from "../qr/QrScanner";
import { hostOf, parseQr, type ParsedQr } from "../qr/upi";
import { usePageRole, useRole } from "../role";
import {
  CONTACTS,
  GUIDE,
  MESSAGES,
  PERSONA,
  initials,
  type Payee,
  type PhoneMessage,
} from "./scenarios";

type UpiQr = Extract<ParsedQr, { kind: "upi" }>;
type OtherQr = Extract<ParsedQr, { kind: "not_upi" }>;

/** The payment being made: who, how much, and what led to it. */
export interface Draft {
  payee: Payee;
  amount: number;
  note: string;
  message?: PhoneMessage;
  qr?: UpiQr;
}

type Screen =
  | { name: "home" }
  | { name: "message"; message: PhoneMessage }
  | { name: "upi-id" }
  | { name: "not-payment"; qr: OtherQr }
  | { name: "amount"; draft: Draft }
  | { name: "checking"; draft: Draft }
  | { name: "verdict"; draft: Draft; result: PaymentRiskResponse }
  | { name: "pin"; draft: Draft; result: PaymentRiskResponse }
  | { name: "paid"; draft: Draft; result: PaymentRiskResponse; ref: string; at: Date }
  | { name: "cancelled"; draft: Draft; result: PaymentRiskResponse };

const CHECK_MIN_MS = 1200;
const VPA = /^[a-z0-9._-]{2,256}@[a-z0-9.-]{2,64}$/i;

function upiReference(): string {
  return String(Date.now()).slice(-12);
}

function wait(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function PhoneAppPage() {
  usePageRole("customer");
  return (
    <section className="phone-page">
      <header className="page-header compact">
        <h1>Phone payment app</h1>
        <p className="muted">
          A simulated UPI app with TrustShield built in. Pay the way you would on your phone.
        </p>
      </header>
      <div className="phone-layout">
        <div className="phone-frame" aria-label="Simulated phone">
          <span className="phone-notch" aria-hidden="true" />
          <PhoneApp />
        </div>
        <DemoGuide />
      </div>
    </section>
  );
}

function DemoGuide() {
  return (
    <aside className="card phone-guide" aria-labelledby="guide-title">
      <h2 id="guide-title">Try it like a real customer</h2>
      <ol className="guide-list">
        {GUIDE.map((step) => (
          <li key={step.title}>
            <div>
              <strong>{step.title}</strong>
              <span className="muted small">{step.how}</span>
            </div>
            <span className={`badge badge-${step.tone}`}>{step.expect}</span>
          </li>
        ))}
      </ol>
      <p className="muted small">
        When a payment is paused, a case opens for a fraud analyst.{" "}
        <Link to="/analyst/login">Open the analyst console</Link> to review it.
      </p>
      <p className="notice notice-info small">
        Simulated: synthetic accounts, no real money moves. Never enter your real UPI PIN on any
        website, including this one.
      </p>
    </aside>
  );
}

export function PhoneApp() {
  const { api } = useRole();
  const [screen, setScreen] = useState<Screen>({ name: "home" });
  const [scannerOpen, setScannerOpen] = useState(false);
  const [notification, setNotification] = useState<PhoneMessage | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // A scam SMS "arrives" a moment after the phone opens, like a real push notification.
  useEffect(() => {
    const show = window.setTimeout(() => setNotification(MESSAGES[0]), 1500);
    const hide = window.setTimeout(() => setNotification(null), 9500);
    return () => {
      window.clearTimeout(show);
      window.clearTimeout(hide);
    };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const check = useMutation({
    mutationFn: async (draft: Draft) => {
      const body: PaymentRiskRequest = {
        transaction_id: `TXN-${Date.now()}`,
        amount: draft.amount,
        currency: "INR",
        payer_id: PERSONA.payerId,
        payee_vpa: draft.payee.vpa,
        beneficiary_age_minutes: draft.payee.addedMinutesAgo,
        device_changed: false,
        location_changed: false,
        message_context: draft.message?.text ?? null,
        qr: draft.qr
          ? {
              raw: draft.qr.raw,
              payee_name: draft.qr.payeeName ?? null,
              amount: draft.qr.amount ?? null,
              merchant_code: draft.qr.merchantCode ?? null,
            }
          : null,
      };
      const [result] = await Promise.all([api.evaluatePayment(body), wait(CHECK_MIN_MS)]);
      return result;
    },
    onSuccess: (result, draft) =>
      setScreen(
        result.decision === "ALLOW"
          ? { name: "pin", draft, result }
          : { name: "verdict", draft, result },
      ),
    onError: (_err, draft) => setScreen({ name: "amount", draft }),
  });

  const pay = (draft: Draft) => {
    setScreen({ name: "checking", draft });
    check.mutate(draft);
  };

  const home = () => {
    check.reset();
    setScreen({ name: "home" });
  };

  const onQr = useCallback((text: string, sample?: QrSample) => {
    setScannerOpen(false);
    const parsed = parseQr(text);
    if (parsed.kind === "not_upi") {
      setScreen({ name: "not-payment", qr: parsed });
      return;
    }
    const saved = CONTACTS.find((c) => c.vpa === parsed.payeeVpa);
    setScreen({
      name: "amount",
      draft: {
        payee: {
          name: parsed.payeeName ?? parsed.payeeVpa,
          vpa: parsed.payeeVpa,
          addedMinutesAgo: saved?.addedMinutesAgo ?? sample?.scenario?.beneficiary_age_minutes ?? 0,
        },
        amount: parsed.amount ?? sample?.scenario?.amount ?? 0,
        note: parsed.note ?? "",
        qr: parsed,
      },
    });
  }, []);

  return (
    <div className="phone-app">
      <StatusBar />
      {notification && screen.name === "home" && (
        <button
          type="button"
          className="push"
          onClick={() => {
            setNotification(null);
            setScreen({ name: "message", message: notification });
          }}
        >
          <Icon name="sms" className="push-icon" />
          <span className="push-body">
            <strong>{notification.from}</strong>
            <span>{notification.text}</span>
          </span>
        </button>
      )}

      <div className="phone-screen">
        {screen.name === "home" && (
          <Home
            onScan={() => setScannerOpen(true)}
            onUpiId={() => setScreen({ name: "upi-id" })}
            onContact={(payee) => setScreen({ name: "amount", draft: { payee, amount: 0, note: "" } })}
            onMessage={(message) => setScreen({ name: "message", message })}
          />
        )}
        {screen.name === "message" && (
          <MessageView
            message={screen.message}
            onBack={home}
            onPay={() =>
              setScreen({
                name: "amount",
                draft: {
                  payee: screen.message.payee,
                  amount: screen.message.amount,
                  note: "",
                  message: screen.message,
                },
              })
            }
          />
        )}
        {screen.name === "upi-id" && (
          <UpiIdEntry
            onBack={home}
            onNext={(vpa) =>
              setScreen({
                name: "amount",
                draft: { payee: { name: vpa, vpa, addedMinutesAgo: 0 }, amount: 0, note: "" },
              })
            }
          />
        )}
        {screen.name === "not-payment" && <NotAPayment qr={screen.qr} onDone={home} />}
        {screen.name === "amount" && (
          <AmountEntry
            draft={screen.draft}
            error={check.isError ? describeError(check.error, "customer") : null}
            onBack={home}
            onPay={pay}
          />
        )}
        {screen.name === "checking" && <Checking draft={screen.draft} />}
        {screen.name === "verdict" && (
          <Verdict
            draft={screen.draft}
            result={screen.result}
            onCancel={() => setScreen({ ...screen, name: "cancelled" })}
            onContinue={() => setScreen({ ...screen, name: "pin" })}
            onSimulated={setToast}
          />
        )}
        {screen.name === "pin" && (
          <PinPad
            draft={screen.draft}
            result={screen.result}
            onBack={home}
            onDone={() =>
              setScreen({ ...screen, name: "paid", ref: upiReference(), at: new Date() })
            }
          />
        )}
        {screen.name === "paid" && (
          <Paid draft={screen.draft} result={screen.result} upiRef={screen.ref} at={screen.at} onDone={home} />
        )}
        {screen.name === "cancelled" && (
          <Cancelled draft={screen.draft} result={screen.result} onDone={home} />
        )}
      </div>

      {toast && (
        <p className="phone-toast" role="status">
          {toast}
        </p>
      )}
      {scannerOpen && <QrScanner onResult={onQr} onClose={() => setScannerOpen(false)} />}
    </div>
  );
}

function StatusBar() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="status-bar" aria-hidden="true">
      <span>{now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })}</span>
      <span className="status-icons">
        <span className="signal" />
        5G
        <span className="battery" />
      </span>
    </div>
  );
}

function AppBar({ title, onBack }: { title: string; onBack?: () => void }) {
  return (
    <div className="phone-bar">
      {onBack && (
        <button type="button" className="icon-button" aria-label="Back" onClick={onBack}>
          <Icon name="arrow_back" />
        </button>
      )}
      <h2>{title}</h2>
    </div>
  );
}

function Avatar({ name, small = false }: { name: string; small?: boolean }) {
  const hue = [...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  return (
    <span
      className={small ? "avatar avatar-sm" : "avatar"}
      style={{ background: `hsl(${hue} 55% 42%)` }}
      aria-hidden="true"
    >
      {initials(name) || "?"}
    </span>
  );
}

function Home({
  onScan,
  onUpiId,
  onContact,
  onMessage,
}: {
  onScan: () => void;
  onUpiId: () => void;
  onContact: (payee: Payee) => void;
  onMessage: (message: PhoneMessage) => void;
}) {
  return (
    <div className="phone-home">
      <div className="home-head">
        <div>
          <span className="app-name">SynthPay</span>
          <span className="protected">
            <ShieldMark size={14} />
            Protected by TrustShield
          </span>
        </div>
        <Avatar name={PERSONA.name} small />
      </div>
      <p className="greeting">Hi {PERSONA.name}</p>

      <div className="quick-actions">
        <button type="button" onClick={onScan}>
          <Icon name="qr_code_scanner" />
          Scan QR
        </button>
        <button type="button" onClick={onUpiId}>
          <Icon name="alternate_email" />
          Pay UPI ID
        </button>
        <button type="button" onClick={() => onContact(CONTACTS[0])}>
          <Icon name="contacts" />
          Pay contact
        </button>
      </div>

      <h3 className="phone-section">People</h3>
      <ul className="people">
        {CONTACTS.map((c) => (
          <li key={c.vpa}>
            <button type="button" onClick={() => onContact(c)} aria-label={`Pay ${c.name}`}>
              <Avatar name={c.name} />
              <span>{c.name.split(" ")[0]}</span>
            </button>
          </li>
        ))}
      </ul>

      <h3 className="phone-section">Messages</h3>
      <ul className="inbox">
        {MESSAGES.map((m) => (
          <li key={m.id}>
            <button type="button" onClick={() => onMessage(m)}>
              <Icon name={m.channel === "SMS" ? "sms" : "chat"} className="inbox-icon" />
              <span className="inbox-body">
                <span className="inbox-top">
                  <strong>{m.from}</strong>
                  <span className="muted small">{m.time}</span>
                </span>
                <span className="inbox-text">{m.text}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function MessageView({
  message,
  onBack,
  onPay,
}: {
  message: PhoneMessage;
  onBack: () => void;
  onPay: () => void;
}) {
  return (
    <div className="phone-page-body">
      <AppBar title={message.from} onBack={onBack} />
      <div className="thread">
        <p className="bubble">{message.text}</p>
        <span className="muted small">
          {message.channel} · {message.time}
        </span>
      </div>
      <div className="phone-footer">
        <button type="button" className="primary wide" onClick={onPay}>
          Pay {formatRupees(message.amount)} to {message.payee.vpa}
        </button>
      </div>
    </div>
  );
}

function UpiIdEntry({ onBack, onNext }: { onBack: () => void; onNext: (vpa: string) => void }) {
  const [vpa, setVpa] = useState("");
  const valid = VPA.test(vpa);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (valid) onNext(vpa.toLowerCase());
  }
  return (
    <form className="phone-page-body" onSubmit={submit}>
      <AppBar title="Pay UPI ID" onBack={onBack} />
      <label className="phone-field">
        UPI ID
        <input
          autoFocus
          value={vpa}
          placeholder="name@synthbank"
          autoCapitalize="none"
          autoComplete="off"
          onChange={(e) => setVpa(e.target.value.trim())}
        />
      </label>
      <p className="muted small">
        Try any new ID, e.g. <code>aarav.pandit.00720@synthbank</code>
      </p>
      <div className="phone-footer">
        <button type="submit" className="primary wide" disabled={!valid}>
          Continue
        </button>
      </div>
    </form>
  );
}

function AmountEntry({
  draft,
  error,
  onBack,
  onPay,
}: {
  draft: Draft;
  error: string | null;
  onBack: () => void;
  onPay: (draft: Draft) => void;
}) {
  const [amount, setAmount] = useState(draft.amount ? String(draft.amount) : "");
  const [note, setNote] = useState(draft.note);
  const value = Number(amount);
  const fixed = draft.qr?.amount !== undefined;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (value > 0) onPay({ ...draft, amount: value, note });
  }
  return (
    <form className="phone-page-body" onSubmit={submit} aria-label="Enter amount">
      <AppBar title="" onBack={onBack} />
      <div className="payee-head">
        <Avatar name={draft.payee.name} />
        <strong>Paying {draft.payee.name}</strong>
        <span className="muted small">{draft.payee.vpa}</span>
        {draft.qr && (
          <span className="chip-note">
            <Icon name="qr_code_2" />
            From a QR code{draft.qr.merchantCode ? " · shop" : ""}
          </span>
        )}
        {draft.payee.addedMinutesAgo === 0 && !draft.qr && (
          <span className="chip-note">
            <Icon name="person" />
            First payment to this UPI ID
          </span>
        )}
      </div>
      <label className="amount-field">
        <span className="sr-only">Amount in rupees</span>
        <span className="rupee" aria-hidden="true">
          ₹
        </span>
        <input
          inputMode="decimal"
          value={amount}
          placeholder="0"
          readOnly={fixed}
          aria-label="Amount"
          onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ""))}
        />
      </label>
      <label className="note-field">
        <span className="sr-only">Note</span>
        <input value={note} placeholder="Add a note" onChange={(e) => setNote(e.target.value)} />
      </label>
      {draft.message && (
        <div className="linked-message">
          <Icon name="sms" />
          <span>
            <strong>Paying from a message by {draft.message.from}</strong>
            <span className="muted small">TrustShield checks the message that led to this payment.</span>
          </span>
        </div>
      )}
      {error && <ErrorNotice>{error}</ErrorNotice>}
      <div className="phone-footer">
        <span className="muted small pay-from">
          <Icon name="account_balance" />
          {PERSONA.bank} {PERSONA.account}
        </span>
        <button type="submit" className="primary wide" disabled={!(value > 0)}>
          Proceed to pay
        </button>
      </div>
    </form>
  );
}

function Checking({ draft }: { draft: Draft }) {
  const steps = [
    draft.message ? "Reading the message behind this payment" : "Looking for scam signs",
    draft.qr ? "Checking the QR code's owner" : "Checking the recipient",
    "Comparing with your usual payments",
  ];
  return (
    <div className="checking" role="status" aria-live="polite">
      <span className="checking-shield">
        <ShieldMark size={44} />
      </span>
      <h2>TrustShield is checking this payment</h2>
      <p className="muted">
        {formatRupees(draft.amount)} to {draft.payee.name}
      </p>
      <ul className="checking-steps">
        {steps.map((s, i) => (
          <li key={s} style={{ animationDelay: `${i * 350}ms` }}>
            <Icon name="check" />
            {s}
          </li>
        ))}
      </ul>
    </div>
  );
}

const VERDICT_HEAD: Record<string, { icon: string; tone: string; title: string }> = {
  WARN: { icon: "info", tone: "caution", title: "Take a moment before you pay" },
  STEP_UP_VERIFICATION: { icon: "warning", tone: "warning", title: "Please confirm a few details first" },
  HOLD_AND_ESCALATE: { icon: "pan_tool", tone: "danger", title: "We've paused this payment for your safety" },
};

function Verdict({
  draft,
  result,
  onCancel,
  onContinue,
  onSimulated,
}: {
  draft: Draft;
  result: PaymentRiskResponse;
  onCancel: () => void;
  onContinue: () => void;
  onSimulated: (text: string) => void;
}) {
  const head = VERDICT_HEAD[result.decision] ?? VERDICT_HEAD.WARN;
  const held = result.decision === "HOLD_AND_ESCALATE";
  const stepUp = result.decision === "STEP_UP_VERIFICATION";
  const [confirmed, setConfirmed] = useState(false);
  return (
    <article className={`phone-page-body verdict-screen tone-${head.tone}`} aria-label="TrustShield check">
      <div className="verdict-head">
        <Icon name={head.icon} className="result-icon" />
        <h2>{head.title}</h2>
        <p className="muted small">
          {formatRupees(draft.amount)} to {draft.payee.vpa}
        </p>
      </div>
      <p className="sheet-message">{result.customer_message}</p>
      {(result.top_signals?.length ?? 0) > 0 && (
        <>
          <h3>Why we're checking</h3>
          <ul className="signals">
            {result.top_signals?.map((s) => (
              <li key={s.code}>
                <strong>{s.label}</strong>
                <span>{s.plain_explanation}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {stepUp && (
        <label className="check confirm-check">
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
          I've confirmed this person and this payment through a phone number or contact I already
          trust.
        </label>
      )}
      <div className="phone-footer stacked">
        <button type="button" className="primary wide" onClick={onCancel}>
          Cancel this payment
        </button>
        {result.safe_actions
          ?.filter((a) => a.code === "contact_bank_official" || a.code === "report_scam")
          .map((a) => (
            <button
              key={a.code}
              type="button"
              className="secondary wide"
              onClick={() => onSimulated(`Simulated: “${a.label}”.`)}
            >
              {a.code === "contact_bank_official" && <Icon name="call" />}
              {a.label}
            </button>
          ))}
        {!held && (
          <button
            type="button"
            className="text-button wide"
            disabled={stepUp && !confirmed}
            onClick={onContinue}
          >
            {stepUp ? "I've verified it, continue" : "I know them, continue"}
          </button>
        )}
      </div>
      {result.case_id && (
        <p className="muted small">
          A safety specialist will review this payment. Case reference {result.case_id}.
        </p>
      )}
    </article>
  );
}

const PIN_LENGTH = 6;

/** A dummy UPI PIN pad. Only the number of taps is kept: the digits are never stored or sent. */
function PinPad({
  draft,
  result,
  onBack,
  onDone,
}: {
  draft: Draft;
  result: PaymentRiskResponse;
  onBack: () => void;
  onDone: () => void;
}) {
  const [count, setCount] = useState(0);
  const [processing, setProcessing] = useState(false);
  const press = (key: string) => {
    if (processing) return;
    if (key === "back") setCount((c) => Math.max(0, c - 1));
    else if (key === "ok") {
      if (count < 4) return;
      setProcessing(true);
      window.setTimeout(onDone, 900);
    } else setCount((c) => Math.min(PIN_LENGTH, c + 1));
  };
  // A laptop keyboard works too; the key itself is never kept, only that one was pressed.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (/^[0-9]$/.test(e.key)) press("digit");
      else if (e.key === "Backspace") press("back");
      else if (e.key === "Enter") press("ok");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "back", "0", "ok"];
  return (
    <div className="pin-screen" aria-label="Enter UPI PIN">
      <div className="pin-top">
        <button type="button" className="icon-button" aria-label="Cancel" onClick={onBack}>
          <Icon name="close" />
        </button>
        <span className="muted small">
          {PERSONA.bank} {PERSONA.account}
        </span>
      </div>
      <div className="pin-summary">
        <span className="muted small">To {draft.payee.name}</span>
        <strong>{formatRupees(draft.amount)}</strong>
        {result.decision === "ALLOW" ? (
          <span className="badge badge-ok">
            <Icon name="verified" />
            Checked by TrustShield
          </span>
        ) : (
          <span className="badge badge-caution">Continuing after a TrustShield warning</span>
        )}
      </div>
      <p className="pin-demo" role="note">
        <Icon name="lock" />
        Demo only: never enter your real UPI PIN here. Any 4–6 digits work and nothing is stored.
      </p>
      <h2 className="pin-title">{processing ? "Processing…" : "Enter UPI PIN"}</h2>
      <div className="pin-dots" aria-label={`${count} of ${PIN_LENGTH} digits entered`}>
        {Array.from({ length: PIN_LENGTH }, (_, i) => (
          <span key={i} className={i < count ? "dot filled" : "dot"} />
        ))}
      </div>
      <div className="keypad">
        {keys.map((k) => (
          <button
            key={k}
            type="button"
            className={k === "ok" ? "key key-ok" : "key"}
            aria-label={k === "back" ? "Delete" : k === "ok" ? "Confirm PIN" : `Digit ${k}`}
            disabled={processing || (k === "ok" && count < 4)}
            onClick={() => press(k)}
          >
            {k === "back" ? <Icon name="backspace" /> : k === "ok" ? <Icon name="check" /> : k}
          </button>
        ))}
      </div>
    </div>
  );
}

function Paid({
  draft,
  result,
  upiRef,
  at,
  onDone,
}: {
  draft: Draft;
  result: PaymentRiskResponse;
  upiRef: string;
  at: Date;
  onDone: () => void;
}) {
  return (
    <div className="phone-page-body done-screen tone-ok" aria-label="Payment successful">
      <Icon name="check_circle" className="done-icon" />
      <h2>{formatRupees(draft.amount)} paid</h2>
      <p>to {draft.payee.name}</p>
      <dl className="receipt">
        <div>
          <dt>UPI ID</dt>
          <dd>{draft.payee.vpa}</dd>
        </div>
        <div>
          <dt>UPI ref. no.</dt>
          <dd>{upiRef}</dd>
        </div>
        <div>
          <dt>Time</dt>
          <dd>{at.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</dd>
        </div>
        {result.audit_id && (
          <div>
            <dt>TrustShield check</dt>
            <dd>{result.audit_id}</dd>
          </div>
        )}
      </dl>
      <p className="muted small">Simulated payment: no real money moved.</p>
      <div className="phone-footer">
        <button type="button" className="primary wide" onClick={onDone}>
          Done
        </button>
      </div>
    </div>
  );
}

function Cancelled({
  draft,
  result,
  onDone,
}: {
  draft: Draft;
  result: PaymentRiskResponse;
  onDone: () => void;
}) {
  return (
    <div className="phone-page-body done-screen tone-neutral" aria-label="Payment cancelled">
      <Icon name="task_alt" className="done-icon" />
      <h2>Payment cancelled</h2>
      <p>
        {formatRupees(draft.amount)} to {draft.payee.vpa} was not sent. No money left your account.
      </p>
      <p className="muted small">
        If someone is pressuring you to pay, stop and call your bank on the number on its official
        app or card.
      </p>
      {result.case_id && <p className="muted small">Case reference {result.case_id}</p>}
      {result.audit_id && <p className="muted small">Check reference {result.audit_id}</p>}
      <div className="phone-footer">
        <button type="button" className="primary wide" onClick={onDone}>
          Back to home
        </button>
      </div>
    </div>
  );
}

function NotAPayment({ qr, onDone }: { qr: OtherQr; onDone: () => void }) {
  const what =
    qr.reason === "link"
      ? `It opens a website (${hostOf(qr.raw)}), not a payment.`
      : "It isn't a normal payment to a shop or person.";
  return (
    <div className="phone-page-body verdict-screen tone-danger" aria-label="QR check result">
      <div className="verdict-head">
        <Icon name="gpp_bad" className="result-icon" />
        <h2>This QR code isn't a payment</h2>
      </div>
      <p className="sheet-message">
        {what} Don't pay, sign in, or share any details from it. If someone sent it to you, check
        with them through a contact you already trust.
      </p>
      <div className="phone-footer">
        <button type="button" className="primary wide" onClick={onDone}>
          Back to home
        </button>
      </div>
    </div>
  );
}
