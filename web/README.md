# web/: TrustShield simulator (React + Vite + TypeScript)

**Owner: Sameer** (initial build by Jahnavi, 15 Oct). One app with three routes, typed against
`shared/contracts/openapi.json`. Every page shows the banner *"Prototype simulator — synthetic data.
Not affiliated with Google Pay."* The look is our own neutral design, with no Google Pay logo,
colours or layout.

| Route | Who | What |
| --- | --- | --- |
| `/` | everyone | Landing: logo, name, and two ways in |
| `/customer` | customer | Choose Payment simulator or Merchant check (one-line descriptions) |
| `/customer/pay`, `/customer/merchant` | customer | Tabbed panel with only these two sections, opened on the chosen one |
| `/analyst/login` | analyst | Analyst ID + access code |
| `/analyst`, `/analyst/:caseId` | analyst (signed in) | Case queue (summary tiles, filters, search) and case detail (risk meter, tabs: Overview, Timeline, Accounts, Evidence & Q&A, Decision) |

Each page sends its own `X-Demo-Role` (customer / merchant / analyst) automatically.

**Analyst sign-in is a demo gate, not security.** The access code comes from
`VITE_ANALYST_ACCESS_CODE` (see `.env.example`; the default is `trustshield-demo`). Like every
`VITE_*` value it ships in the browser bundle, and the gateway still trusts `X-Demo-Role`. Real
protection = Firebase Auth or IAP in front of the analyst routes (PRD §7). The session lives in
`sessionStorage`, so closing the tab signs out; decisions are recorded under the signed-in
analyst ID.

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
