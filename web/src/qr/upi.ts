/**
 * Parse what a QR code contains. UPI payment QRs hold
 *   upi://pay?pa=<UPI ID>&pn=<name>&am=<amount>&cu=INR&mc=<merchant code>&tn=<note>
 * Anything else (a website link, plain text) is "not_upi": never something to pay from.
 */

export type ParsedQr =
  | {
      kind: "upi";
      raw: string;
      payeeVpa: string;
      payeeName?: string;
      amount?: number;
      merchantCode?: string;
      note?: string;
    }
  | { kind: "not_upi"; raw: string; reason: "link" | "upi_other" | "no_payee" | "text" };

const VPA = /^[a-z0-9._-]{2,256}@[a-z0-9.-]{2,64}$/i;

export function parseQr(text: string): ParsedQr {
  const raw = text.trim();
  const lower = raw.toLowerCase();
  if (/^https?:\/\//.test(lower)) return { kind: "not_upi", raw, reason: "link" };
  if (!lower.startsWith("upi://")) return { kind: "not_upi", raw, reason: "text" };
  if (!lower.startsWith("upi://pay")) return { kind: "not_upi", raw, reason: "upi_other" };

  const query = raw.includes("?") ? raw.slice(raw.indexOf("?") + 1) : "";
  const params = new URLSearchParams(query);
  const get = (key: string) => {
    for (const [k, v] of params) if (k.toLowerCase() === key) return v.trim();
    return undefined;
  };
  const pa = get("pa");
  if (!pa || !VPA.test(pa)) return { kind: "not_upi", raw, reason: "no_payee" };
  const am = Number(get("am"));
  return {
    kind: "upi",
    raw,
    payeeVpa: pa.toLowerCase(),
    payeeName: get("pn") || undefined,
    amount: Number.isFinite(am) && am > 0 ? am : undefined,
    merchantCode: get("mc") || undefined,
    note: get("tn") || undefined,
  };
}

export function hostOf(link: string): string {
  try {
    return new URL(link).host;
  } catch {
    return link.slice(0, 60);
  }
}
