import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { DISCLAIMER } from "./components/Layout";
import { mockGateway, renderApp } from "./test/utils";

describe("app shell", () => {
  it.each(["/pay", "/analyst", "/merchant"])("shows the disclaimer on %s", (path) => {
    mockGateway({ "GET /api/v1/cases": () => ({ body: { cases: [] } }) });
    renderApp(path, "customer");
    expect(screen.getByRole("note")).toHaveTextContent(DISCLAIMER);
  });

  it("navigating to a page switches to that page's demo role", async () => {
    const { calls } = mockGateway({ "GET /api/v1/cases": () => ({ body: { cases: [] } }) });
    renderApp("/pay", "customer");
    await userEvent.click(screen.getByRole("link", { name: "Analyst console" }));
    expect(await screen.findByText(/No cases yet/)).toBeVisible();
    expect(calls.at(-1)?.role).toBe("analyst");
    expect(screen.getByLabelText("Demo role")).toHaveValue("analyst");
  });

  it("warns when the selected role can't use the page", () => {
    mockGateway({});
    renderApp("/merchant", "customer");
    expect(screen.getByRole("status")).toHaveTextContent("This page is for the merchant role");
  });

  it("the analyst page never calls the gateway with a non-analyst role", async () => {
    const { calls } = mockGateway({ "GET /api/v1/cases": () => ({ body: { cases: [] } }) });
    renderApp("/analyst/CASE-1", "customer");
    expect(screen.getByRole("status")).toHaveTextContent("This page is for the analyst role");
    await userEvent.click(screen.getByRole("link", { name: "Merchant check" }));
    expect(calls).toHaveLength(0);
  });
});
