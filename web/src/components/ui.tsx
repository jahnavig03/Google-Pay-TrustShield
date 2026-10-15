import type { ReactNode } from "react";

/** Material Symbols icon (decorative: hidden from screen readers). */
export function Icon({ name, className = "" }: { name: string; className?: string }) {
  return (
    <span className={`material-symbols-outlined ${className}`.trim()} aria-hidden="true">
      {name}
    </span>
  );
}

export function ErrorNotice({ children }: { children: ReactNode }) {
  return (
    <div className="notice notice-error" role="alert">
      {children}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="spinner" role="status" aria-live="polite">
      <span className="spinner-dot" aria-hidden="true" />
      {label}
    </div>
  );
}

export function Badge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export function formatRupees(amount: number): string {
  return `₹${amount.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export const DECISION_TONE: Record<string, string> = {
  ALLOW: "ok",
  WARN: "caution",
  STEP_UP_VERIFICATION: "warning",
  HOLD_AND_ESCALATE: "danger",
};

export function humanize(code: string): string {
  return code.replace(/_/g, " ").replace(/\b\w/, (c) => c.toUpperCase());
}

/** "5 min ago" style relative time for queue rows. */
export function timeAgo(value: string, now: number = Date.now()): string {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return value;
  const minutes = Math.max(0, Math.round((now - then) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}
