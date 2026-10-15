import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import demo3 from "../../../shared/contracts/fixtures/demo3_fake_screenshot_12k.json";
import { mockGateway, renderApp } from "../test/utils";
import { MAX_SCREENSHOT_BYTES } from "./MerchantPage";

const VERIFY = "POST /api/v1/merchant/payment-verify";

describe("/merchant", () => {
  it("demo 3: sends the fixture as merchant and shows a suspicious verdict", async () => {
    const { calls } = mockGateway({ [VERIFY]: () => ({ body: demo3.expected_response }) });
    renderApp("/merchant", "merchant");

    await userEvent.click(screen.getByRole("button", { name: /Demo 3/ }));
    await userEvent.click(screen.getByRole("button", { name: "Check payment" }));

    const verdict = await screen.findByRole("article", { name: "Verification result" });
    expect(verdict).toHaveTextContent("Suspicious");
    expect(verdict).toHaveTextContent("Risk: high");
    expect(verdict).toHaveTextContent(demo3.expected_response.recommended_action);
    expect(verdict).toHaveTextContent("428913570012");
    expect(calls[0].role).toBe("merchant");
    expect(calls[0].body).toEqual(demo3.request);
  });

  it("rejects a screenshot over 5 MB before sending anything", async () => {
    const { calls } = mockGateway({});
    renderApp("/merchant", "merchant");
    const big = new File([new Uint8Array(MAX_SCREENSHOT_BYTES + 1)], "big.png", {
      type: "image/png",
    });
    await userEvent.upload(screen.getByLabelText("Payment screenshot"), big);
    expect(await screen.findByRole("alert")).toHaveTextContent("larger than 5 MB");
    expect(calls).toHaveLength(0);
  });

  it("asks for a screenshot if none was added", async () => {
    mockGateway({});
    renderApp("/merchant", "merchant");
    await userEvent.type(screen.getByLabelText(/Amount the customer/), "500");
    await userEvent.type(screen.getByLabelText(/Transaction ID/), "123");
    await userEvent.click(screen.getByRole("button", { name: "Check payment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Add the customer's payment screenshot");
  });
});
