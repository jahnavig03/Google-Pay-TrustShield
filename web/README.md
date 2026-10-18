# web/: TrustShield simulator (React + Vite + TypeScript)

**Owner: Sameer** (initial build by Jahnavi). One app, typed against `shared/contracts/openapi.json`.
Every page shows the pinned banner *"Built exclusively for the Google Cloud AI Builder Cup"*.

**Theme.** Material Design 3 structure with the palette Blue #3A81F1, Green #2DA94F,
Amber #FDBD00, Red #EA4335 and Flint #5F6368. These are used as accents by meaning (trust, safe,
caution, hold, neutral); text-bearing fills use a deeper tone of the same blue for AA contrast.
A light/dark toggle sits top right on every page. The choice is saved in `localStorage` and
applied before first paint (no flash), with a 0.3 s cross-fade. Dark mode uses a pure black
background, dark-grey surfaces and desaturated accents; the logo is single-colour (black or
white). No Google or Google Pay logos, no multi-colour brand mark, no copied screens.

| Route | Who | What |
| --- | --- | --- |
| `/` | everyone | Landing: logo, name, and two ways in |
| `/customer` | customer | Choose Payment check or Merchant check (one-line descriptions) |
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

## Phone payment app

`/customer/app` (`src/phone/`) is a simulated UPI app ("SynthPay") with TrustShield built in: home
screen with contacts and an SMS/chat inbox, Scan QR, Pay UPI ID, amount entry, the TrustShield check,
then allow → dummy PIN pad → receipt, warn → continue or cancel, step-up → confirm you verified, hold →
paused (no PIN). One synthetic customer and her messages live in `src/phone/scenarios.ts`. The PIN
pad keeps only the number of taps; digits are never stored or sent.

## QR scanning (Payment check)

**Scan QR** (next to "Pay to") opens a dialog: upload a photo, use the camera, or pick a sample QR
(`public/demo-qr/*.png`, synthetic). Decoding runs on the device with `jsQR`; the image is never
uploaded. A `upi://pay?pa=…&pn=…&am=…&mc=…` code fills the form and is sent as the optional `qr`
field, so the agents can check that the QR's name matches the UPI ID's registered owner and that a
shop QR (`mc=`) belongs to a registered merchant. Anything else (a website link, a collect request)
is flagged on the device as "not a payment" and never sent.

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
