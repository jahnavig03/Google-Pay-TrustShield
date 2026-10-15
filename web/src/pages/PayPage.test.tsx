import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import demo1 from "../../../shared/contracts/fixtures/demo1_payment_85k.json";
import { mockGateway, renderApp } from "../test/utils";

const EVALUATE = "POST /api/v1/payment-risk/evaluate";

describe("/pay", () => {
  it("demo 1: sends the fixture payment as customer and shows the hold sheet", async () => {
    const { calls } = mockGateway({ [EVALUATE]: () => ({ body: demo1.expected_response }) });
    renderApp("/customer/pay");

    await userEvent.click(screen.getByRole("button", { name: "Pay" }));

    const sheet = await screen.findByRole("article", { name: "Payment check result" });
    expect(within(sheet).getByRole("heading", { level: 2 })).toHaveTextContent(
      "We've paused this payment for your safety",
    );
    expect(sheet).toHaveTextContent(demo1.expected_response.customer_message);
    for (const signal of demo1.expected_response.top_signals) {
      expect(sheet).toHaveTextContent(signal.plain_explanation);
    }
    expect(sheet).not.toHaveTextContent("2.52"); // contributions are for analysts, not customers
    expect(within(sheet).getByRole("button", { name: "Cancel this payment" })).toBeVisible();
    expect(sheet).toHaveTextContent(`Case reference ${demo1.expected_response.case_id}`);

    const [call] = calls;
    expect(call.role).toBe("customer");
    const body = call.body as Record<string, unknown>;
    expect(body.amount).toBe(85000);
    expect(body.payee_vpa).toBe(demo1.request.payee_vpa);
    expect(body.transaction_id).toMatch(/^TXN-\d+$/);
  });

  it("a safe action is simulated, never executed", async () => {
    mockGateway({ [EVALUATE]: () => ({ body: demo1.expected_response }) });
    renderApp("/customer/pay");
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel this payment" }));
    expect(screen.getByText(/No real payment was made/)).toBeVisible();
  });

  it("an ALLOW shows the reassuring sheet without the signal list", async () => {
    mockGateway({
      [EVALUATE]: () => ({
        body: {
          ...demo1.expected_response,
          decision: "ALLOW",
          risk_score: 0.02,
          customer_message: "This payment looks fine. You can go ahead.",
          safe_actions: [{ code: "proceed", label: "Continue with the payment" }],
          case_id: null,
        },
      }),
    });
    renderApp("/customer/pay");
    await userEvent.click(screen.getByRole("button", { name: /Everyday ₹40/ }));
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    const sheet = await screen.findByRole("article", { name: "Payment check result" });
    expect(sheet).toHaveTextContent("This payment looks fine");
    expect(within(sheet).queryByText("Why we're checking")).toBeNull();
  });

  it("a governance block (422) shows a neutral message, not the rule text", async () => {
    mockGateway({
      [EVALUATE]: () => ({
        status: 422,
        body: { detail: { governance_outcome: "blocked", reason: "Governance rule 3: …" } },
      }),
    });
    renderApp("/customer/pay");
    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't complete this safety check");
    expect(alert).not.toHaveTextContent("Governance");
  });
});
