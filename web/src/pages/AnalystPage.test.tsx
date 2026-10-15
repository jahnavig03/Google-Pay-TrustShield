import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import demo2 from "../../../shared/contracts/fixtures/demo2_analyst_case.json";
import { mockGateway, renderApp } from "../test/utils";

const CASE_ID = demo2.case.case_id;
const routes = {
  "GET /api/v1/cases": () => ({ body: demo2.case_list }),
  [`GET /api/v1/cases/${CASE_ID}`]: () => ({ body: demo2.case }),
};

describe("/analyst", () => {
  it("lists cases and opens one with signals, timeline, links and citations", async () => {
    const { calls } = mockGateway(routes);
    renderApp("/analyst", "analyst");

    await userEvent.click(await screen.findByRole("link", { name: /₹85,000/ }));

    const detail = await screen.findByRole("article", { name: `Case ${CASE_ID}` });
    expect(detail).toHaveTextContent(demo2.case.summary);
    expect(within(detail).getByRole("region", { name: "Top signals" })).toHaveTextContent("w·x");
    expect(within(detail).getByRole("region", { name: "Timeline" })).toHaveTextContent(
      "Case created",
    );
    expect(detail).toHaveTextContent("refund.desk.help@synthbank");
    expect(detail).toHaveTextContent(demo2.case.citations[0].title);
    expect(calls.every((c) => c.role === "analyst")).toBe(true);
  });

  it("shows 'not covered by policy' as an answer, not an error", async () => {
    mockGateway({
      ...routes,
      [`POST /api/v1/cases/${CASE_ID}/ask`]: () => ({
        body: { answer: "not covered by policy", citations: [] },
      }),
    });
    renderApp(`/analyst/${CASE_ID}`, "analyst");
    await userEvent.click(await screen.findByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/Not covered by policy/)).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a grounded answer with its citations", async () => {
    mockGateway({
      ...routes,
      [`POST /api/v1/cases/${CASE_ID}/ask`]: () => ({ body: demo2.ask_response }),
    });
    renderApp(`/analyst/${CASE_ID}`, "analyst");
    await userEvent.click(await screen.findByRole("button", { name: "Ask" }));
    const qa = await screen.findByText(/Four signals combined/);
    expect(qa.closest(".qa")).toHaveTextContent("policy_kyc_03");
  });

  it("records a decision only with a reason, then shows the audit id", async () => {
    const { calls } = mockGateway({
      ...routes,
      [`POST /api/v1/cases/${CASE_ID}/decision`]: () => ({ body: demo2.decision_response }),
    });
    renderApp(`/analyst/${CASE_ID}`, "analyst");
    const approve = await screen.findByRole("button", { name: "Approve escalation" });
    expect(approve).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/Reason/), "Urgency SMS and a new payee.");
    await userEvent.click(approve);

    expect(await screen.findByText(/Recorded: case is now Escalated/)).toHaveTextContent(
      demo2.decision_response.decision.audit_id,
    );
    const decision = calls.find((c) => c.path.endsWith("/decision"));
    expect(decision?.body).toEqual({
      action: "approve_escalation",
      analyst_id: "analyst_demo_01",
      reason: "Urgency SMS and a new payee.",
    });
  });

  it("explains a 409 from Governance", async () => {
    mockGateway({
      ...routes,
      [`POST /api/v1/cases/${CASE_ID}/decision`]: () => ({ status: 409, body: { detail: "x" } }),
    });
    renderApp(`/analyst/${CASE_ID}`, "analyst");
    await userEvent.type(await screen.findByLabelText(/Reason/), "r");
    await userEvent.click(screen.getByRole("button", { name: "Close case" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("needs a recorded analyst approval");
  });
});
