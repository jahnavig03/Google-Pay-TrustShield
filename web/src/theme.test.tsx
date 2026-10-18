import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { mockGateway, renderApp } from "./test/utils";
import { THEME_KEY } from "./theme";

afterEach(() => {
  delete document.documentElement.dataset.theme;
});

describe("theme toggle", () => {
  it.each(["/", "/customer", "/customer/pay", "/analyst/login"])("is on %s", (path) => {
    mockGateway({});
    renderApp(path);
    expect(screen.getByRole("button", { name: /Switch to (dark|light) mode/ })).toBeVisible();
  });

  it("switches the whole page and remembers the choice", async () => {
    mockGateway({});
    document.documentElement.dataset.theme = "light";
    renderApp("/");

    await userEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("light");
  });

  it("keeps the theme when moving between pages", async () => {
    mockGateway({});
    document.documentElement.dataset.theme = "light";
    renderApp("/");
    await userEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));
    await userEvent.click(screen.getByRole("link", { name: /Continue as customer/ }));
    await userEvent.click(screen.getByRole("link", { name: /Payment check/ }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeVisible();
  });
});
