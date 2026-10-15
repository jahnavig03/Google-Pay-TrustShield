# web/: TrustShield simulator (React + Vite + TypeScript)

**Owner: Sameer** (initial build by Jahnavi, 15 Oct). One app with three routes, typed against
`shared/contracts/openapi.json`. Every page shows the banner *"Prototype simulator — synthetic data.
Not affiliated with Google Pay."* The look is our own neutral design, with no Google Pay logo,
colours or layout.

| Route | Role (`X-Demo-Role`) | Demo |
| --- | --- | --- |
| `/pay` | customer | Payment simulator + warning sheet (PaySafe). Presets: demo 1 (₹85k scam), rent, everyday payment. |
| `/analyst` | analyst | Case list → case detail (signals, timeline, linked accounts, evidence), "Ask why", Approve / Outreach / Close with a reason (PayInvestigator) |
| `/merchant` | merchant | Screenshot + claimed amount / UTR → verdict card (PayGuard). Demo 3 preset; uploads ≤ 5 MB as `data:` URIs. |

Clicking a page in the top nav switches to that page's demo role; the role switcher overrides it.
A page used with the wrong role shows a notice and makes no calls.

## Run locally

```bash
# 1. gateway (mock mode, in-process store: no credentials, no emulator)
cd services/gateway && source .venv/bin/activate
TRUSTSHIELD_DOC_STORE=memory TRUSTSHIELD_PUBLISHER=noop uvicorn main:app --port 8000

# 2. web (Node 24)
cd web && npm install && npm run dev          # http://localhost:5173
```

`VITE_API_BASE_URL` sets the gateway URL (default `http://localhost:8000`; see `.env.example`).

## Scripts

| Script | What |
| --- | --- |
| `npm run dev` / `build` / `preview` | Vite |
| `npm test` | Vitest + Testing Library (fake gateway, contract fixtures as responses) |
| `npm run lint` | ESLint + TypeScript type check |
| `npm run gen:api` | Regenerate `src/api/schema.ts` from `shared/contracts/openapi.json` after a contract change |

## Deploy (Firebase Hosting)

```bash
cd web && VITE_API_BASE_URL=https://<cloud-run-url> npm run build
cd .. && firebase deploy --only hosting --project qualified-sun-511214-t1
```

Then add the Hosting URL to the gateway's `CORS_ALLOW_ORIGINS` on Cloud Run, or the browser can't
call the API. `firebase.json` serves `web/dist` with an SPA rewrite to `/index.html`.
