import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { mockGateway, renderApp } from "../test/utils";

const TRANSLATE = "POST /api/v1/translate";

afterEach(() => window.localStorage.clear());

describe("/customer/app language setting", () => {
  it("switching to Hindi translates the app through the gateway, keeping names and amounts", async () => {
    const { calls } = mockGateway({
      [TRANSLATE]: (call) => {
        const { texts } = call.body as { texts: string[] };
        return {
          body: {
            target_language: "hi",
            translations: texts.map((t) => `हि: ${t}`),
            provider: "google-cloud-translation",
          },
        };
      },
    });
    renderApp("/customer/app");

    await userEvent.click(screen.getByRole("button", { name: /Change language/ }));
    await userEvent.click(screen.getByRole("option", { name: /हिन्दी/ }));

    // Reviewed Hindi is used as-is; everything else comes from Cloud Translation.
    expect(screen.getByRole("button", { name: "QR स्कैन करें" })).toBeVisible();
    expect(await screen.findByText("हि: Protected by TrustShield")).toBeVisible();
    expect(screen.getByText("नमस्ते Priya")).toBeVisible(); // reviewed, with the name filled in

    const translateCalls = calls.filter((c) => c.path === "/api/v1/translate");
    const sent = translateCalls.flatMap((c) => (c.body as { texts: string[] }).texts);
    expect(translateCalls.every((c) => (c.body as { target_language: string }).target_language === "hi")).toBe(true);
    expect(sent).not.toContain("Hi Priya"); // names go in as placeholders, not baked into labels
    expect(sent).not.toContain("Scan QR"); // reviewed, so not sent
    expect(window.localStorage.getItem("synthpay.language")).toBe('"hi"');
  });

  it("if translation fails, the app stays in English", async () => {
    mockGateway({ [TRANSLATE]: () => ({ status: 502, body: { detail: "unavailable" } }) });
    renderApp("/customer/app");
    await userEvent.click(screen.getByRole("button", { name: /Change language/ }));
    await userEvent.click(screen.getByRole("option", { name: /தமிழ்/ }));
    await waitFor(() => expect(screen.getByText("Protected by TrustShield")).toBeVisible());
    expect(screen.getByText("Hi Priya")).toBeVisible();
  });
});
