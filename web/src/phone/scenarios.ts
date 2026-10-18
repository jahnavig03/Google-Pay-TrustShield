/**
 * The demo phone's world: one synthetic customer, her saved contacts and the messages on her
 * phone. All names, UPI IDs and messages are synthetic (they exist in the mock feature store).
 */

const MINUTES_PER_DAY = 60 * 24;

export const PERSONA = {
  name: "Priya",
  payerId: "payer_demo_001",
  bank: "Synth Bank",
  account: "••4821",
};

export interface Payee {
  name: string;
  vpa: string;
  /** How long ago this payee was saved; 0 for someone the customer has never paid. */
  addedMinutesAgo: number;
  tag?: string;
}

export interface PhoneMessage {
  id: string;
  from: string;
  channel: "SMS" | "Chat";
  time: string;
  text: string;
  /** The payment the message asks for, opened when the customer taps "Pay". */
  payee: Payee;
  amount: number;
  /** What TrustShield is expected to do (shown in the demo guide). */
  expect: string;
}

export const CONTACTS: Payee[] = [
  {
    name: "Anil Sharma",
    vpa: "landlord.sharma@synthbank",
    addedMinutesAgo: 400 * MINUTES_PER_DAY,
    tag: "Landlord",
  },
  {
    name: "Ramesh Tea Stall",
    vpa: "chai.ramesh@synthbank",
    addedMinutesAgo: 730 * MINUTES_PER_DAY,
    tag: "Shop",
  },
  {
    name: "Demo Kirana Store",
    vpa: "mer.demo0042@synthbank",
    addedMinutesAgo: 365 * MINUTES_PER_DAY,
    tag: "Shop",
  },
];

export const MESSAGES: PhoneMessage[] = [
  {
    id: "kyc",
    from: "VM-SYNBNK",
    channel: "SMS",
    time: "10:42",
    text:
      "Dear Customer, your bank account will be BLOCKED today because your KYC is pending. " +
      "To keep it active, transfer Rs 85,000 to the verification account " +
      "kyc.helpdesk.verify@synthbank immediately. Do not share this message. - Bank Security Team",
    payee: { name: "KYC Verification", vpa: "kyc.helpdesk.verify@synthbank", addedMinutesAgo: 0 },
    amount: 85000,
    expect: "Paused",
  },
  {
    id: "rent",
    from: "Anil Sharma",
    channel: "Chat",
    time: "09:15",
    text: "Hi Priya, rent of Rs 25,000 for October is due today. Thanks! - Anil",
    payee: CONTACTS[0],
    amount: 25000,
    expect: "Goes through",
  },
  {
    id: "olx",
    from: "Unknown number",
    channel: "Chat",
    time: "Yesterday",
    text:
      "Hi, I am an army officer, buying your sofa. Pay Rs 12,000 security deposit first and I " +
      "will send Rs 24,000 back immediately. Hurry, I am posting today.",
    payee: { name: "Capt. Vikram", vpa: "aarush.nath.00131@synthbank", addedMinutesAgo: 0 },
    amount: 12000,
    expect: "Asks you to verify",
  },
  {
    id: "job",
    from: "HR-JOBSIN",
    channel: "SMS",
    time: "Yesterday",
    text:
      "Congratulations, you are selected for a work-from-home job. Pay Rs 4,500 registration " +
      "fee today to confirm your joining. - HR Team",
    payee: { name: "Hiring Desk", vpa: "abeer.pandey.00228@synthbank", addedMinutesAgo: 0 },
    amount: 4500,
    expect: "Warns you",
  },
  {
    id: "refund",
    from: "AD-SHOPRF",
    channel: "SMS",
    time: "Mon",
    text:
      "Your refund of Rs 4,999 for order 88231 is pending. Pay Rs 10 processing fee to " +
      "refund.desk.help@synthbank to release it today.",
    payee: { name: "Refund Desk", vpa: "refund.desk.help@synthbank", addedMinutesAgo: 0 },
    amount: 10,
    expect: "Paused",
  },
];

/** Things to try, shown next to the phone (and below it on a real phone). */
export const GUIDE: { title: string; how: string; expect: string; tone: string }[] = [
  {
    title: "Your language",
    how: "Tap the अ/English chip → हिन्दी (or any of 10 Indian languages).",
    expect: "Translated",
    tone: "caution",
  },
  {
    title: "The “account blocked” SMS",
    how: "Tap the notification, then Pay ₹85,000.",
    expect: "Paused",
    tone: "danger",
  },
  {
    title: "Rent to your landlord",
    how: "Open Anil's message and pay ₹25,000.",
    expect: "Goes through",
    tone: "ok",
  },
  {
    title: "A swapped QR sticker",
    how: "Scan QR → Sample QRs → Tea stall (swapped).",
    expect: "Paused",
    tone: "danger",
  },
  {
    title: "The genuine tea stall QR",
    how: "Scan QR → Tea stall (genuine), pay ₹40.",
    expect: "Goes through",
    tone: "ok",
  },
  {
    title: "The “army buyer” chat",
    how: "Open the chat and pay the deposit.",
    expect: "Asks you to verify",
    tone: "warning",
  },
  {
    title: "A new UPI ID",
    how: "Pay UPI ID → any new ID, ₹15,000.",
    expect: "Warns you",
    tone: "caution",
  },
];

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter((w) => /^[A-Za-z]/.test(w))
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}
