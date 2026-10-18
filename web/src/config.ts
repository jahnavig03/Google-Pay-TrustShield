/**
 * UI configuration. Values can be overridden with VITE_* variables (see web/.env.example).
 * The risk bands are for DISPLAY only; the agents' config/risk.yaml decides the real outcome.
 */

function num(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && value !== undefined && value !== "" ? parsed : fallback;
}

export const RISK_BANDS = {
  warn: num(import.meta.env.VITE_RISK_WARN, 0.35),
  stepUp: num(import.meta.env.VITE_RISK_STEP_UP, 0.7),
  hold: num(import.meta.env.VITE_RISK_HOLD, 0.9),
};

/**
 * Demo sign-in gate for the analyst console. NOT security: VITE_* values ship in the browser
 * bundle, and the gateway still trusts the X-Demo-Role header. Real auth = Firebase Auth / IAP.
 */
export const ANALYST_ACCESS_CODE: string =
  import.meta.env.VITE_ANALYST_ACCESS_CODE || "trustshield-demo";
