import type { ReactNode } from "react";

import type { Role } from "../api/client";
import { useRole } from "../role";

/** Shown when the selected demo role can't use this page (the gateway would answer 403). */
/** Material Symbols icon (decorative: hidden from screen readers). */
export function Icon({ name, className = "" }: { name: string; className?: string }) {
  return (
    <span className={`material-symbols-outlined ${className}`.trim()} aria-hidden="true">
      {name}
    </span>
  );
}

export function RoleNotice({ needs }: { needs: Role }) {
  const { role, setRole } = useRole();
  if (role === needs) return null;
  return (
    <div className="notice notice-info" role="status">
      This page is for the <strong>{needs}</strong> role; you're browsing as <strong>{role}</strong>.{" "}
      <button type="button" className="link-button" onClick={() => setRole(needs)}>
        Switch to {needs}
      </button>
    </div>
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
