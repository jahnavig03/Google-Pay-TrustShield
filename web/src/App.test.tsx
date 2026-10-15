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

  it("opening a page directly adopts that page's role", async () => {
    const { calls } = mockGateway({ "GET /api/v1/cases": () => ({ body: { cases: [] } }) });
    renderApp("/analyst", "merchant");
    expect(await screen.findByText(/No cases yet/)).toBeVisible();
    expect(calls.every((c) => c.role === "analyst")).toBe(true);
  });

  it("switching to the wrong role warns and stops the analyst page calling the gateway", async () => {
    const { calls } = mockGateway({ "GET /api/v1/cases": () => ({ body: { cases: [] } }) });
    renderApp("/analyst", "analyst");
    await screen.findByText(/No cases yet/);
    const before = calls.length;

    await userEvent.selectOptions(screen.getByLabelText("Demo role"), "customer");
    expect(screen.getByRole("status")).toHaveTextContent("This page is for the analyst role");
    await userEvent.click(screen.getByRole("button", { name: "Switch to analyst" }));
    await userEvent.selectOptions(screen.getByLabelText("Demo role"), "merchant");
    await userEvent.click(screen.getByRole("link", { name: "Merchant check" }));
    expect(calls.slice(before).filter((c) => c.role !== "analyst")).toHaveLength(0);
  });
});
