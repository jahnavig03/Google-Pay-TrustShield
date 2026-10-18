import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { DISCLAIMER } from "./components/Layout";
import { ANALYST_ACCESS_CODE } from "./config";
import { mockGateway, renderApp } from "./test/utils";

const EMPTY_CASES = { "GET /api/v1/cases": () => ({ body: { cases: [] } }) };

describe("entry flow", () => {
  it.each(["/", "/customer", "/customer/pay", "/customer/merchant", "/analyst/login"])(
    "shows the disclaimer on %s",
    (path) => {
      mockGateway({});
      renderApp(path);
      expect(screen.getByRole("note")).toHaveTextContent(DISCLAIMER);
    },
  );

  it("landing shows the name and both ways in", () => {
    mockGateway({});
    renderApp("/");
    expect(screen.getByRole("heading", { level: 1, name: "TrustShield" })).toBeVisible();
    expect(screen.getByRole("link", { name: /Continue as customer/ })).toHaveAttribute(
      "href",
      "/customer",
    );
    expect(screen.getByRole("link", { name: /Sign in as analyst/ })).toHaveAttribute(
      "href",
      "/analyst/login",
    );
  });

  it("customer: landing -> choice -> payment check opens with only customer tabs", async () => {
    mockGateway({});
    renderApp("/");
    await userEvent.click(screen.getByRole("link", { name: /Continue as customer/ }));
    expect(screen.getByRole("heading", { name: "What would you like to do?" })).toBeVisible();
    await userEvent.click(screen.getByRole("link", { name: /Payment check/ }));

    expect(screen.getByRole("heading", { level: 1, name: "Payment check" })).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual([
      "smartphonePhone app",
      "paymentsPayment check",
      "storefrontMerchant check",
    ]);
    expect(within(nav).getByRole("link", { name: "Payment check" })).toHaveClass("active");
    expect(screen.queryByRole("link", { name: /Analyst console/ })).toBeNull();
  });

  it("customer: choosing merchant check opens that tab directly", async () => {
    mockGateway({});
    renderApp("/customer");
    await userEvent.click(screen.getByRole("link", { name: /Merchant check/ }));
    expect(screen.getByRole("heading", { level: 1, name: "Merchant check" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Merchant check" })).toHaveClass("active");
  });

  it("old /pay and /merchant links still work", () => {
    mockGateway({});
    renderApp("/pay");
    expect(screen.getByRole("heading", { level: 1, name: "Payment check" })).toBeVisible();
  });
});

describe("analyst sign-in", () => {
  it("the console is unreachable without signing in", () => {
    const { calls } = mockGateway(EMPTY_CASES);
    renderApp("/analyst");
    expect(screen.getByRole("heading", { name: "Analyst sign-in" })).toBeVisible();
    expect(calls).toHaveLength(0);
  });

  it("a wrong access code is refused", async () => {
    mockGateway(EMPTY_CASES);
    renderApp("/analyst/login");
    await userEvent.type(screen.getByLabelText("Access code"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("alert")).toHaveTextContent("access code isn't right");
    expect(screen.queryByRole("heading", { name: "Case queue" })).toBeNull();
  });

  it("signing in opens the console with only the analyst view, as the analyst role", async () => {
    const { calls } = mockGateway(EMPTY_CASES);
    renderApp("/analyst/login");
    await userEvent.type(screen.getByLabelText("Access code"), ANALYST_ACCESS_CODE);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Case queue" })).toBeVisible();
    expect(screen.getByTitle("Signed-in analyst")).toHaveTextContent("analyst_demo_01");
    expect(screen.queryByRole("link", { name: /Payment check/ })).toBeNull();
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c.role === "analyst")).toBe(true);
  });

  it("signing out returns to the landing page and locks the console again", async () => {
    mockGateway(EMPTY_CASES);
    renderApp("/analyst", { analystId: "analyst_demo_01" });
    await userEvent.click(await screen.findByRole("link", { name: /Sign out/ }));
    expect(await screen.findByRole("heading", { level: 1, name: "TrustShield" })).toBeVisible();
    expect(window.sessionStorage.getItem("trustshield.analystSession")).toBeNull();
  });
});
