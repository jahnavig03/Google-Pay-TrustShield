import { render } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { App } from "../App";

export interface Call {
  method: string;
  path: string;
  role: string | null;
  body: unknown;
}

type Handler = (call: Call) => { status?: number; body: unknown };

/** Fake gateway: routes are "METHOD /path" (path params matched literally). Records every call. */
export function mockGateway(routes: Record<string, Handler>) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const url = new URL(request.url);
    const text = await request.clone().text();
    const call: Call = {
      method: request.method,
      path: url.pathname,
      role: request.headers.get("X-Demo-Role"),
      body: text ? JSON.parse(text) : null,
    };
    calls.push(call);
    const handler = routes[`${call.method} ${call.path}`];
    if (!handler) return new Response(JSON.stringify({ detail: "no mock" }), { status: 404 });
    const { status = 200, body } = handler(call);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

/** Render the whole app at `path`. `analystId` pre-signs-in an analyst (session storage). */
export function renderApp(path: string, options: { analystId?: string } = {}) {
  if (options.analystId) {
    window.sessionStorage.setItem("trustshield.analystSession", options.analystId);
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App queryClient={queryClient} />
    </MemoryRouter>,
  );
}
