/**
 * Typed client for the TrustShield gateway. Types are generated from
 * shared/contracts/openapi.json (`npm run gen:api`), so the UI can't drift from the contract.
 */
import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

type Schemas = components["schemas"];
export type PaymentRiskRequest = Schemas["PaymentRiskRequest"];
export type PaymentRiskResponse = Schemas["PaymentRiskResponse"];
export type Decision = Schemas["Decision"];
export type Signal = Schemas["Signal"];
export type MerchantVerifyRequest = Schemas["MerchantVerifyRequest"];
export type MerchantVerifyResponse = Schemas["MerchantVerifyResponse"];
export type PaymentStatus = Schemas["PaymentStatus"];
export type Case = Schemas["Case"];
export type CaseSummary = Schemas["CaseSummary"];
export type CaseAnswer = Schemas["CaseAnswer"];
export type AnalystAction = Schemas["AnalystAction"];
export type CaseDecisionResponse = Schemas["CaseDecisionResponse"];

/** Demo roles, sent as X-Demo-Role (stands in for real auth in the prototype). */
export type Role = "customer" | "analyst" | "merchant";
export const ROLES: Role[] = ["customer", "analyst", "merchant"];

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

/** A non-2xx answer from the gateway, with its HTTP status and body. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(`Gateway answered HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: { data?: T; error?: unknown; response: Response };
  try {
    result = await call;
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : String(err));
  }
  const { data, error, response } = result;
  if (!response.ok || data === undefined) throw new ApiError(response.status, error);
  return data;
}

export function makeApi(role: Role, baseUrl: string = API_BASE_URL) {
  const client = createClient<paths>({ baseUrl, headers: { "X-Demo-Role": role } });
  return {
    evaluatePayment: (body: PaymentRiskRequest) =>
      unwrap(client.POST("/api/v1/payment-risk/evaluate", { body })),
    verifyMerchantPayment: (body: MerchantVerifyRequest) =>
      unwrap(client.POST("/api/v1/merchant/payment-verify", { body })),
    listCases: () => unwrap(client.GET("/api/v1/cases")),
    getCase: (caseId: string) =>
      unwrap(client.GET("/api/v1/cases/{case_id}", { params: { path: { case_id: caseId } } })),
    askCase: (caseId: string, question: string) =>
      unwrap(
        client.POST("/api/v1/cases/{case_id}/ask", {
          params: { path: { case_id: caseId } },
          body: { question },
        }),
      ),
    decideCase: (caseId: string, action: AnalystAction, analystId: string, reason: string) =>
      unwrap(
        client.POST("/api/v1/cases/{case_id}/decision", {
          params: { path: { case_id: caseId } },
          body: { action, analyst_id: analystId, reason },
        }),
      ),
  };
}

export type Api = ReturnType<typeof makeApi>;

/** One plain sentence for any failed call. Never shows raw server text to a customer. */
export function describeError(err: unknown, audience: "customer" | "staff" = "staff"): string {
  if (!(err instanceof ApiError)) return "Something went wrong. Please try again.";
  if (err.status === 0) return "Couldn't reach the TrustShield service. Is the gateway running?";
  if (err.status === 401 || err.status === 403)
    return "This page needs a different demo role. Use the role switcher at the top.";
  if (err.status === 422 && audience === "customer")
    return "We couldn't complete this safety check. Please try again in a moment.";
  if (err.status === 404) return "Not found. It may have been removed or never existed.";
  const detail = (err.detail as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "reason" in detail)
    return String((detail as { reason: unknown }).reason);
  return `The service answered with an error (HTTP ${err.status}). Please try again.`;
}
