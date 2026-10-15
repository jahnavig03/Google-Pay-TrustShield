import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import demo2 from "../../../shared/contracts/fixtures/demo2_analyst_case.json";
import { mockGateway, renderApp } from "../test/utils";

const CASE_ID = demo2.case.case_id;
const R = demo2.case.risk_score.toFixed(3);
const ANALYST = { analystId: "analyst_jane" };
const OTHER = {
  ...demo2.case_list.cases[0],
  case_id: "CASE-OTHER-1",
  payee_vpa: "someone.else@synthbank",
  status: "escalated",
  risk_score: 0.81,
  decision: "STEP_UP_VERIFICATION",
  amount: 12000,
};
const routes = {
  "GET /api/v1/cases": () => ({ body: { cases: [demo2.case_list.cases[0], OTHER] } }),
  [`GET /api/v1/cases/${CASE_ID}`]: () => ({ body: demo2.case }),
};

async function openTab(name: string) {
  await userEvent.click(await screen.findByRole("tab", { name }));
  return screen.getByRole("tabpanel");
}

describe("analyst console", () => {
  it("summarises the queue", async () => {
    mockGateway(routes);
    renderApp("/analyst", ANALYST);
    const kpis = await screen.findByRole("list", { name: "Queue summary" });
    await within(kpis).findByText(R);
    const tiles = within(kpis).getAllByRole("listitem").map((t) => t.textContent);
    // textContent includes the icon font's ligature name, so match the visible end.
    expect(tiles[0]).toMatch(/1Needs review$/);
    expect(tiles[1]).toMatch(/1Escalated$/);
    expect(tiles[2]).toMatch(/0Resolved$/);
    expect(tiles[3]).toContain(R);
  });

  it("filters and searches the queue", async () => {
    mockGateway(routes);
    renderApp("/analyst", ANALYST);
    await screen.findByRole("link", { name: /₹85,000/ });

    await userEvent.click(screen.getByRole("button", { name: "Escalated" }));
    expect(screen.queryByRole("link", { name: /₹85,000/ })).toBeNull();
    expect(screen.getByRole("link", { name: /₹12,000/ })).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "All" }));
    await userEvent.type(screen.getByLabelText("Search cases"), "kyc.helpdesk");
    expect(screen.getByRole("link", { name: /₹85,000/ })).toBeVisible();
    expect(screen.queryByRole("link", { name: /₹12,000/ })).toBeNull();
  });

  it("opens a case with risk meter and tabbed sections", async () => {
    mockGateway(routes);
    renderApp("/analyst", ANALYST);
    await userEvent.click(await screen.findByRole("link", { name: /₹85,000/ }));

    const detail = await screen.findByRole("article", { name: `Case ${CASE_ID}` });
    expect(within(detail).getByRole("img", { name: `Risk score ${R} out of 1` })).toBeVisible();
    expect(detail).toHaveTextContent("Recommended: Approve escalation");
    expect(screen.getByRole("tabpanel")).toHaveTextContent(demo2.case.summary);

    expect(await openTab("Timeline")).toHaveTextContent("Case created");
    expect(await openTab("Accounts")).toHaveTextContent("refund.desk.help@synthbank");
    expect(await openTab("Evidence & Q&A")).toHaveTextContent(demo2.case.citations[0].title);
  });

  it("shows 'not covered by policy' as an answer, not an error", async () => {
    mockGateway({
      ...routes,
      [`POST /api/v1/cases/${CASE_ID}/ask`]: () => ({
        body: { answer: "not covered by policy", citations: [] },
      }),
    });
    renderApp(`/analyst/${CASE_ID}`, ANALYST);
    await openTab("Evidence & Q&A");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/Not covered by policy/)).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a grounded answer with its citations", async () => {
    mockGateway({
      ...routes,
      [`POST /api/v1/cases/${CASE_ID}/ask`]: () => ({ body: demo2.ask_response }),
    });
    renderApp(`/analyst/${CASE_ID}`, ANALYST);
    await openTab("Evidence & Q&A");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));
    const qa = await screen.findByText(/Four signals combined/);
    expect(qa.closest(".qa")).toHaveTextContent("policy_kyc_03");
  });

  it("records the decision as the signed-in analyst, only with a reason", async () => {
    const { calls } = mockGateway({
      ...routes,
      [`POST /api/v1/cases/${CASE_ID}/decision`]: () => ({ body: demo2.decision_response }),
    });
    renderApp(`/analyst/${CASE_ID}`, ANALYST);
    const panel = await openTab("Decision");
    expect(panel).toHaveTextContent("Deciding as analyst_jane");
    const approve = within(panel).getByRole("button", { name: "Approve escalation" });
    expect(approve).toBeDisabled();

    await userEvent.type(within(panel).getByLabelText(/Reason/), "Urgency SMS and a new payee.");
    await userEvent.click(approve);

    expect(await screen.findByText(/Recorded: case is now Escalated/)).toHaveTextContent(
      demo2.decision_response.decision.audit_id,
    );
    expect(calls.find((c) => c.path.endsWith("/decision"))?.body).toEqual({
      action: "approve_escalation",
      analyst_id: "analyst_jane",
      reason: "Urgency SMS and a new payee.",
    });
  });

  it("explains a 409 from Governance", async () => {
    mockGateway({
      ...routes,
      [`POST /api/v1/cases/${CASE_ID}/decision`]: () => ({ status: 409, body: { detail: "x" } }),
    });
    renderApp(`/analyst/${CASE_ID}`, ANALYST);
    const panel = await openTab("Decision");
    await userEvent.type(within(panel).getByLabelText(/Reason/), "r");
    await userEvent.click(within(panel).getByRole("button", { name: "Close case" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("needs a recorded analyst approval");
  });
});
