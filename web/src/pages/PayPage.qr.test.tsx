import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import demo1 from "../../../shared/contracts/fixtures/demo1_payment_85k.json";
import { decodeBlob } from "../qr/decode";
import { mockGateway, renderApp } from "../test/utils";

// jsdom has no canvas / createImageBitmap: stub the decoder, keep everything else real.
vi.mock("../qr/decode", () => ({
  decodeBlob: vi.fn(),
  decodeVideoFrame: vi.fn(),
  MAX_QR_IMAGE_BYTES: 8 * 1024 * 1024,
}));

const SWAPPED =
  "upi://pay?pa=refund.desk.help@synthbank&pn=Ramesh%20Tea%20Stall&am=2000&cu=INR&mc=5812";
const sample = (file: string) => ({ [`GET /demo-qr/${file}`]: () => ({ body: "png" }) });

async function openSamples() {
  await userEvent.click(screen.getByRole("button", { name: "Scan QR" }));
  const dialog = screen.getByRole("dialog", { name: "Scan a QR code" });
  await userEvent.click(within(dialog).getByRole("tab", { name: /Sample QRs/ }));
  return dialog;
}

describe("/customer/pay QR scanning", () => {
  beforeEach(() => vi.mocked(decodeBlob).mockReset());

  it("a scanned UPI QR fills the form and travels with the payment", async () => {
    vi.mocked(decodeBlob).mockResolvedValue(SWAPPED);
    const { calls } = mockGateway({
      ...sample("tea-stall-swapped.png"),
      "POST /api/v1/payment-risk/evaluate": () => ({ body: demo1.expected_response }),
    });
    renderApp("/customer/pay");

    const dialog = await openSamples();
    await userEvent.click(within(dialog).getByRole("button", { name: /swapped sticker/ }));

    const card = await screen.findByRole("status", { name: "From QR code" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(card).toHaveTextContent("Ramesh Tea Stall");
    expect(card).toHaveTextContent("refund.desk.help@synthbank · ₹2,000 · shop QR");
    expect(screen.getByLabelText("Pay to (UPI ID)")).toHaveValue("refund.desk.help@synthbank");
    expect(screen.getByLabelText(/Amount/)).toHaveValue(2000);

    await userEvent.click(screen.getByRole("button", { name: "Pay" }));
    await screen.findByRole("article", { name: "Payment check result" });
    const body = calls.find((c) => c.path.endsWith("/evaluate"))?.body as Record<string, unknown>;
    expect(body).toMatchObject({
      payee_vpa: "refund.desk.help@synthbank",
      amount: 2000,
      payer_id: "payer_demo_003",
      beneficiary_age_minutes: 0,
      qr: { raw: SWAPPED, payee_name: "Ramesh Tea Stall", amount: 2000, merchant_code: "5812" },
    });
  });

  it("a link QR is flagged on the device and never sent as a payment", async () => {
    vi.mocked(decodeBlob).mockResolvedValue("https://kyc-verify.synthbank.example/update");
    const { calls } = mockGateway(sample("kyc-link.png"));
    renderApp("/customer/pay");

    const dialog = await openSamples();
    await userEvent.click(within(dialog).getByRole("button", { name: /KYC update/ }));

    const result = await screen.findByRole("article", { name: "QR check result" });
    expect(result).toHaveTextContent("This QR code isn't a payment");
    expect(result).toHaveTextContent("kyc-verify.synthbank.example");
    expect(calls.filter((c) => c.path.startsWith("/api/"))).toHaveLength(0);
  });

  it("an image without a QR explains what to do", async () => {
    vi.mocked(decodeBlob).mockResolvedValue(null);
    mockGateway({});
    renderApp("/customer/pay");
    await userEvent.click(screen.getByRole("button", { name: "Scan QR" }));
    const file = new File([new Uint8Array(10)], "photo.png", { type: "image/png" });
    await userEvent.upload(screen.getByLabelText("QR image"), file);
    expect(await screen.findByRole("alert")).toHaveTextContent("No QR code found");
  });

  it("typing a UPI ID by hand drops the QR", async () => {
    vi.mocked(decodeBlob).mockResolvedValue(SWAPPED);
    mockGateway(sample("tea-stall-swapped.png"));
    renderApp("/customer/pay");
    const dialog = await openSamples();
    await userEvent.click(within(dialog).getByRole("button", { name: /swapped sticker/ }));
    await screen.findByRole("status", { name: "From QR code" });
    await userEvent.type(screen.getByLabelText("Pay to (UPI ID)"), "x");
    expect(screen.queryByRole("status", { name: "From QR code" })).toBeNull();
  });

  it("a QR without an amount clears the old amount (the user types it)", async () => {
    vi.mocked(decodeBlob).mockResolvedValue("upi://pay?pa=someone.new@synthbank&pn=Someone");
    mockGateway({});
    renderApp("/customer/pay");
    await userEvent.click(screen.getByRole("button", { name: "Scan QR" }));
    const file = new File([new Uint8Array(10)], "qr.png", { type: "image/png" });
    await userEvent.upload(screen.getByLabelText("QR image"), file);
    await screen.findByRole("status", { name: "From QR code" });
    expect(screen.getByLabelText(/Amount/)).toHaveValue(null);
    expect(screen.getByLabelText(/Recipient added/)).toHaveValue(0);
  });

  it("Esc closes the scanner", async () => {
    mockGateway({});
    renderApp("/customer/pay");
    await userEvent.click(screen.getByRole("button", { name: "Scan QR" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
