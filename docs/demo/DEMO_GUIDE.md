# TrustShield demo guide (team)

Everything below is **synthetic data**. Nothing touches real Google Pay accounts or people.

## Sign-ins

| Who | Demo role | Analyst console sign-in | Access code |
| --- | --- | --- | --- |
| Jahnavi | Narrator + customer (demo 1) | `analyst_jahnavi` | `trustshield-demo` |
| Sameer | Customer with a QR (demo 1b) | `analyst_sameer` | `trustshield-demo` |
| Hitesh | Fraud analyst (demo 2) | `analyst_hitesh` | `trustshield-demo` |
| Ronak | Shop owner / merchant (demo 3) | `analyst_ronak` | `trustshield-demo` |

The sign-in page suggests these IDs. The access code is a **demo gate, not security**: it ships in
the web app, and real protection would be Firebase Auth / IAP. Decisions are recorded under the ID
you sign in with, so each of us shows up in the audit log under our own name.

## Phone payment app (for judges: the real-life experience)

`/customer/app` (Customer → **Phone payment app**) is a simulated UPI app, "SynthPay", with
TrustShield built in. On a laptop it shows inside a phone frame; on a real phone it fills the screen.
The customer is Priya (`payer_demo_001`, usually pays ~₹1,800). A scam SMS arrives as a
notification a moment after the page opens.

| Try | How | Expect |
| --- | --- | --- |
| "Account blocked" SMS | Tap the notification → Pay ₹85,000 → Proceed | Paused (HOLD), never reaches the PIN screen; case opens |
| Rent | Open Anil Sharma's message → Pay ₹25,000 | Goes through: PIN pad → paid receipt with a TrustShield check ID |
| Swapped QR sticker | Scan QR → Sample QRs → Tea stall (swapped) | Paused: "QR name doesn't match" |
| Genuine tea stall | Scan QR → Tea stall (genuine) → ₹40 | Goes through |
| "Army buyer" chat | Unknown number → Pay ₹12,000 | Step-up: must tick "I've verified" before the PIN |
| Job fee SMS | HR-JOBSIN → Pay ₹4,500 | Warning: can continue after a pause |
| Refund SMS | AD-SHOPRF → Pay ₹10 | Paused |
| New UPI ID | Pay UPI ID → `aarav.pandit.00720@synthbank` → ₹15,000 | Warning |

**Language:** tap the language chip (top right of the app's home screen) → pick हिन्दी or any of 10
Indian languages. Menus, the SMS, and TrustShield's live warning and signals switch to that language
through Google Cloud Translation (cached, so each text is translated once). Names, amounts and UPI IDs
are never translated. On a message, "Show original" shows the English text the checks actually read.

The PIN pad is a dummy: any 6 digits work, only the count of taps is kept, nothing is sent, and the
screen says "never enter your real UPI PIN here".

## Sample data, per person

### Jahnavi: customer, payer `payer_demo_001` (usually pays ~₹1,800)
| # | Where | Input | Expected |
| --- | --- | --- | --- |
| 1 | Payment check → **Demo 1 · ₹85k scam** | ₹85,000 to `kyc.helpdesk.verify@synthbank`, payee added 4 min ago, new device, "account will be BLOCKED… KYC" SMS | **Paused** (R ≈ 0.997): urgent message, 47× usual amount, new recipient, linked to reported accounts, new device |
| 2 | Same, but paste a Hinglish message | "Aapka khata aaj band ho jayega, abhi ke abhi 85000 bhejo verification account me" | Paused; urgency spotted in Hinglish |
| 3 | Same payee, **delete the message**, untick new device | ₹85,000 | **Still paused** (R ≈ 0.90) on amount, the new payee and its links to reported accounts: no SMS needed |
| 4 | Payment check → **Everyday ₹40** | ₹40 to `chai.ramesh@synthbank` | **Looks fine** (allowed) |

### Sameer: customer with a QR, payer `payer_demo_003` (usually pays ~₹650)
Payment check → **Scan QR** → **Sample QRs** (or upload / show the PNGs in `web/public/demo-qr/` to a camera):
| # | QR | Expected |
| --- | --- | --- |
| 1 | **Tea stall (genuine)**: Ramesh Tea Stall → `chai.ramesh@synthbank`, ₹40 | **Looks fine**; "QR code checked: the name matches its UPI ID's owner" |
| 2 | **Tea stall (swapped sticker)**: says "Ramesh Tea Stall" but pays `refund.desk.help@synthbank`, ₹2,000 | **Paused**: "QR name doesn't match", reported recipient, linked to reported accounts |
| 3 | **'KYC update' link**: a website, not a payment | "This QR code isn't a payment": checked on the phone, nothing sent |
| 4 | **Landlord rent**: Anil Sharma, ₹25,000 (payer `payer_demo_002`) | **Looks fine**: big but genuine (a "hard negative") |

### Hitesh: fraud analyst
Sign in at **Sign in as analyst** with `analyst_hitesh`. Run Jahnavi #1 and Sameer #2 first, so cases exist.
| # | Action | Expected |
| --- | --- | --- |
| 1 | Case queue | Tiles: needs review / escalated / resolved / highest risk; red risk bars on held cases |
| 2 | Open the ₹85,000 case | Risk meter in the "hold" band, "Recommended: Approve escalation", tabs |
| 3 | **Evidence & Q&A** → Ask "Why was this payment flagged?", then "What does policy say about KYC update requests?", then "Who won the cricket match?" | The first two answer with the case's signals and quoted policy, each cited (`[policy_payment_safety_01]`, `[policy_kyc_03]`); the off-topic one says exactly **"not covered by policy"** instead of inventing an answer |
| 4 | **Decision** → reason → **Approve escalation** | "Recorded: case is now Escalated · Audit AUD-…"; the tile moves to Escalated |

### Ronak: shop owner, merchant `MER-DEMO-0042`
Merchant check → **Try an example** (synthetic screenshots from Ronak's ledger data):
| # | Example | Expected |
| --- | --- | --- |
| 1 | **Demo 3 · fake ₹12k** (UTR `428913570012`) | **Suspicious / high**: no such credit, timestamp 3 min after it was shown, amount in a different font. "Hold the goods for now." |
| 2 | **Genuine ₹1,488** | **Verified / low**: in the ledger and settled. "You can hand over the goods." |
| 3 | **Edited amount ₹21,040** | **Inconsistent / high**: the payment exists, but the screenshot's amount doesn't match the ledger |
| 4 | **Not in ledger ₹6,150** | **Not found / medium**: careful wording, "a genuine payment can take a few minutes to settle" |

Also: an upload over 5 MB is refused on the device, and pressing Check without a screenshot asks for one.

## Three-minute script

| Time | Who | Screen | Say (short) |
| --- | --- | --- | --- |
| 0:00 | Jahnavi | Landing | "UPI scams don't break the PIN. People are talked into paying. TrustShield checks the payment *and* the message or QR that caused it, before money moves." |
| 0:20 | Jahnavi | Demo 1 → Pay | "An 'account will be blocked' SMS, a payee added 4 minutes ago, a new phone, 47× the usual amount. TrustShield pauses it and explains why in plain words, without blaming anyone." |
| 0:50 | Jahnavi | Rent ₹25k → Pay | "A big but genuine rent payment goes straight through. On our synthetic test set, that's 88% fewer false alarms than simple amount/new-payee rules." |
| 1:00 | Sameer | Scan QR → swapped sticker → Pay | "A shop's QR covered with a fraudster's sticker. The name says Ramesh Tea Stall, but the UPI ID belongs to someone else, a reported account. Paused." |
| 1:20 | Sameer | Scan QR → 'KYC update' link | "And a QR that isn't a payment at all is caught right on the phone." |
| 1:30 | Hitesh | Sign in → queue → ₹85,000 case | "Anything above 0.70 opens a case automatically. The analyst sees the risk meter, timeline, linked accounts and cited policy." |
| 1:55 | Hitesh | Ask why → Decision → Approve | "Answers come only from retrieved policy. A hold needs a human: I approve with a reason, and it's written to the audit log with an ID." |
| 2:20 | Ronak | Merchant check → Demo 3, then Genuine ₹1,488 | "A shopkeeper gets a ₹12,000 'payment successful' screenshot. It isn't in the ledger, and the image looks edited: hold the goods. A real ₹1,488 payment? Verified, hand them over." |
| 2:40 | Jahnavi | Analyst console in dark mode / any | "Gemini on Vertex AI reads the messages, ADK agents run in parallel, BigQuery holds the features, Firestore keeps the audit trail. On our synthetic test set: 12 of 12 high-risk payments caught, about 1 second per payment with Gemini. Everything here is synthetic." |
| 3:00 | | | End |

## Before recording
1. Start fresh, so the queue is clean: restart the gateway (the in-memory store resets) or use the deployed URL.
2. Use light mode for the main take; show dark mode once (top-right toggle).
3. Browser zoom 100%, window about 1440×900; close other tabs.
4. Run Jahnavi #1 and Sameer #2 once before Hitesh's part, so the cases exist.
5. If Gemini is busy (429), the app falls back to its rules automatically; the demo still works.

Screenshots for the deck: `docs/screenshots/` (index in `docs/screenshots/README.md`).
