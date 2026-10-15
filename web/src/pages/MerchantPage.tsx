import { useMutation } from "@tanstack/react-query";
import { useState, type ChangeEvent, type FormEvent } from "react";

import demo3 from "../../../shared/contracts/fixtures/demo3_fake_screenshot_12k.json";
import {
  describeError,
  type MerchantVerifyRequest,
  type MerchantVerifyResponse,
} from "../api/client";
import {
  Badge,
  ErrorNotice,
  Icon,
  RoleNotice,
  Spinner,
  formatDateTime,
  formatRupees,
} from "../components/ui";
import { usePageRole, useRole } from "../role";

/** Matches the server-side cap on inline screenshots. */
export const MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024;

const STATUS: Record<string, { label: string; tone: string; icon: string }> = {
  verified: { label: "Verified", tone: "ok", icon: "verified" },
  pending: { label: "Pending", tone: "caution", icon: "schedule" },
  inconsistent: { label: "Inconsistent", tone: "warning", icon: "error" },
  not_found_in_ledger: { label: "Not found in ledger", tone: "warning", icon: "search_off" },
  suspicious: { label: "Suspicious", tone: "danger", icon: "gpp_bad" },
};

const EMPTY: MerchantVerifyRequest = {
  merchant_id: "MER-DEMO-0042",
  uploaded_screenshot: "",
  claimed_amount: 0,
  claimed_transaction_id: "",
};

function readAsDataUri(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("Couldn't read the file"));
    reader.readAsDataURL(file);
  });
}

export function MerchantPage() {
  usePageRole("merchant");
  const { api } = useRole();
  const [form, setForm] = useState<MerchantVerifyRequest>(EMPTY);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const verify = useMutation({
    mutationFn: (body: MerchantVerifyRequest) => api.verifyMerchantPayment(body),
  });

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setFileError(null);
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setFileError("Please choose an image file (PNG or JPEG).");
      return;
    }
    if (file.size > MAX_SCREENSHOT_BYTES) {
      setFileError("That image is larger than 5 MB. Please upload a smaller screenshot.");
      return;
    }
    const uri = await readAsDataUri(file);
    setFileName(file.name);
    setForm((prev) => ({ ...prev, uploaded_screenshot: uri }));
  }

  function loadDemo3() {
    setForm({ ...demo3.request });
    setFileName(demo3.request.uploaded_screenshot);
    setFileError(null);
    verify.reset();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.uploaded_screenshot) {
      setFileError("Add the customer's payment screenshot first.");
      return;
    }
    verify.mutate(form);
  }

  const preview = form.uploaded_screenshot.startsWith("data:image/") ? form.uploaded_screenshot : null;

  return (
    <section className="page">
      <header className="page-header">
        <h1>Merchant check</h1>
        <p className="muted">
          A customer shows you a “payment successful” screenshot. Check it against your ledger
          before you hand over the goods.
        </p>
      </header>
      <RoleNotice needs="merchant" />

      <div className="two-col">
        <form className="card form" onSubmit={submit} aria-label="Screenshot check">
          <button type="button" className="preset" onClick={loadDemo3}>
            <strong>Demo 3: ₹12,000 screenshot</strong>
            <span>Screenshot that never settled</span>
          </button>
          <label>
            Merchant ID
            <input
              required
              value={form.merchant_id}
              onChange={(e) => setForm({ ...form, merchant_id: e.target.value.trim() })}
            />
          </label>
          <label>
            Payment screenshot
            <input type="file" accept="image/*" onChange={onFile} />
          </label>
          {fileName && <p className="muted small">Using: {fileName}</p>}
          {preview && <img className="preview" src={preview} alt="Uploaded payment screenshot" />}
          <label>
            Amount the customer says they paid (₹)
            <input
              type="number"
              min={1}
              step="any"
              required
              value={form.claimed_amount || ""}
              onChange={(e) => setForm({ ...form, claimed_amount: Number(e.target.value) })}
            />
          </label>
          <label>
            Transaction ID (UTR) on the screenshot
            <input
              required
              value={form.claimed_transaction_id}
              onChange={(e) => setForm({ ...form, claimed_transaction_id: e.target.value.trim() })}
            />
          </label>
          {fileError && <ErrorNotice>{fileError}</ErrorNotice>}
          <button type="submit" className="primary" disabled={verify.isPending}>
            {verify.isPending ? "Checking…" : "Check payment"}
          </button>
        </form>

        <div aria-live="polite">
          {verify.isPending && <Spinner label="Reading the screenshot and checking your ledger…" />}
          {verify.isError && <ErrorNotice>{describeError(verify.error)}</ErrorNotice>}
          {verify.data && <Verdict result={verify.data} />}
          {verify.isIdle && (
            <div className="card empty">
              <p className="muted">Load demo 3 or upload a screenshot, then press Check payment.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Verdict({ result }: { result: MerchantVerifyResponse }) {
  const status = STATUS[result.payment_status] ?? {
    label: result.payment_status,
    tone: "neutral",
    icon: "info",
  };
  const x = result.extracted;
  return (
    <article className={`card verdict tone-${status.tone}`} aria-label="Verification result">
      <div className="result-head">
        <Icon name={status.icon} className="result-icon" />
        <h2>{status.label}</h2>
        <Badge tone={status.tone}>Risk: {result.risk_level}</Badge>
      </div>
      <p className="verdict-action">{result.recommended_action}</p>
      <p>{result.explanation}</p>
      {x && (
        <>
          <h3>Read from the screenshot</h3>
          <dl className="facts">
            <div>
              <dt>Amount</dt>
              <dd>{x.amount != null ? formatRupees(x.amount) : "unreadable"}</dd>
            </div>
            <div>
              <dt>Transaction ID</dt>
              <dd>{x.txn_id ?? "unreadable"}</dd>
            </div>
            <div>
              <dt>Paid to</dt>
              <dd>{x.vpa ?? "unreadable"}</dd>
            </div>
            <div>
              <dt>Time</dt>
              <dd>{x.timestamp ? formatDateTime(x.timestamp) : "unreadable"}</dd>
            </div>
          </dl>
        </>
      )}
      {result.audit_id && <p className="muted small">Check reference {result.audit_id}</p>}
    </article>
  );
}
