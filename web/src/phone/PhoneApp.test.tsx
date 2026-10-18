import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import demo1 from "../../../shared/contracts/fixtures/demo1_payment_85k.json";
import { mockGateway, renderApp } from "../test/utils";
import { MESSAGES, PERSONA } from "./scenarios";

const EVALUATE = "POST /api/v1/payment-risk/evaluate";
const SLOW = { timeout: 4000 }; // the check screen stays up for at least 1.2 s

const ALLOW = {
  ...demo1.expected_response,
  decision: "ALLOW",
  risk_score: 0.02,
  customer_message: "This payment looks fine. You can go ahead.",
  safe_actions: [{ code: "proceed", label: "Continue with the payment" }],
  case_id: null,
  audit_id: "AUD-TEST-ALLOW",
};

describe("/customer/app", () => {
  it("the 'account blocked' SMS is paused, never reaches the PIN pad, and can be cancelled", async () => {
    const { calls } = mockGateway({ [EVALUATE]: () => ({ body: demo1.expected_response }) });
    renderApp("/customer/app");

    await userEvent.click(screen.getByRole("button", { name: /^VM-SYNBNK/ }));
    await userEvent.click(screen.getByRole("button", { name: /Pay ₹85,000/ }));
    await userEvent.click(screen.getByRole("button", { name: "Proceed to pay" }));

    const verdict = await screen.findByRole("article", { name: "TrustShield check" }, SLOW);
    expect(verdict).toHaveTextContent("We've paused this payment for your safety");
    expect(within(verdict).queryByRole("button", { name: /continue/i })).toBeNull();
    expect(screen.queryByRole("button", { name: "Confirm PIN" })).toBeNull();

    const body = calls[0].body as Record<string, unknown>;
    expect(calls[0].role).toBe("customer");
    expect(body.payer_id).toBe(PERSONA.payerId);
    expect(body.message_context).toBe(MESSAGES[0].text);
    expect(body.beneficiary_age_minutes).toBe(0);

    await userEvent.click(within(verdict).getByRole("button", { name: "Cancel this payment" }));
    expect(screen.getByLabelText("Payment cancelled")).toHaveTextContent("No money left your account");
  });

  it("an allowed payment goes to the dummy PIN pad; the digits are never shown or sent", async () => {
    const { calls } = mockGateway({ [EVALUATE]: () => ({ body: ALLOW }) });
    renderApp("/customer/app");

    await userEvent.click(screen.getByRole("button", { name: "Pay Ramesh Tea Stall" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Amount" }), "40");
    await userEvent.click(screen.getByRole("button", { name: "Proceed to pay" }));

    const pin = await screen.findByLabelText("Enter UPI PIN", {}, SLOW);
    expect(pin).toHaveTextContent("never enter your real UPI PIN");
    expect(pin).toHaveTextContent("Checked by TrustShield");
    const confirm = within(pin).getByRole("button", { name: "Confirm PIN" });
    for (const digit of ["7", "3", "1"]) {
      await userEvent.click(within(pin).getByRole("button", { name: `Digit ${digit}` }));
    }
    expect(confirm).toBeDisabled(); // at least 4 digits
    await userEvent.click(within(pin).getByRole("button", { name: "Digit 9" }));
    expect(pin).not.toHaveTextContent("7319");
    await userEvent.click(confirm);

    const paid = await screen.findByLabelText("Payment successful", {}, SLOW);
    expect(paid).toHaveTextContent("₹40 paid");
    expect(paid).toHaveTextContent("AUD-TEST-ALLOW");
    expect(calls).toHaveLength(1);
    expect(JSON.stringify(calls[0].body)).not.toContain("7319");
  });

  it("a step-up asks the customer to confirm they verified the payee before continuing", async () => {
    mockGateway({
      [EVALUATE]: () => ({
        body: { ...demo1.expected_response, decision: "STEP_UP_VERIFICATION", risk_score: 0.77 },
      }),
    });
    renderApp("/customer/app");

    await userEvent.click(screen.getByRole("button", { name: /^Unknown number/ }));
    await userEvent.click(screen.getByRole("button", { name: /Pay ₹12,000/ }));
    await userEvent.click(screen.getByRole("button", { name: "Proceed to pay" }));

    const verdict = await screen.findByRole("article", { name: "TrustShield check" }, SLOW);
    const go = within(verdict).getByRole("button", { name: "I've verified it, continue" });
    expect(go).toBeDisabled();
    await userEvent.click(within(verdict).getByRole("checkbox"));
    await userEvent.click(go);
    expect(await screen.findByLabelText("Enter UPI PIN")).toHaveTextContent(
      "Continuing after a TrustShield warning",
    );
  });
});
