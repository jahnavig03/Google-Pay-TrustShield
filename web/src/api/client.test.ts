import { describe, expect, it } from "vitest";

import { mockGateway } from "../test/utils";
import { ApiError, describeError, makeApi } from "./client";

describe("makeApi", () => {
  it("sends the demo role header to the gateway base URL", async () => {
    const { calls } = mockGateway({ "GET /api/v1/cases": () => ({ body: { cases: [] } }) });
    await makeApi("analyst", "http://gateway.test").listCases();
    expect(calls).toEqual([
      { method: "GET", path: "/api/v1/cases", role: "analyst", body: null },
    ]);
  });

  it("throws ApiError with the status and body on a non-2xx answer", async () => {
    mockGateway({
      "POST /api/v1/cases/C1/decision": () => ({ status: 409, body: { detail: "needs approval" } }),
    });
    const err = await makeApi("analyst", "http://gateway.test")
      .decideCase("C1", "approve_escalation", "a1", "r")
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(409);
    expect(describeError(err)).toBe("needs approval");
  });
});

describe("describeError", () => {
  it("never shows a governance block's internals to a customer", () => {
    const blocked = new ApiError(422, { detail: { reason: "Governance rule 3: …" } });
    expect(describeError(blocked, "customer")).toBe(
      "We couldn't complete this safety check. Please try again in a moment.",
    );
  });

  it("explains a role problem and an unreachable gateway", () => {
    expect(describeError(new ApiError(403, {}))).toMatch(/different demo role/);
    expect(describeError(new ApiError(0, "fetch failed"))).toMatch(/Couldn't reach/);
  });
});
