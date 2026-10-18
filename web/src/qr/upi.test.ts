import { describe, expect, it } from "vitest";

import { hostOf, parseQr } from "./upi";

describe("parseQr", () => {
  it("reads a UPI payment QR", () => {
    expect(
      parseQr("upi://pay?pa=Chai.Ramesh@synthbank&pn=Ramesh%20Tea%20Stall&am=40&cu=INR&mc=5812"),
    ).toEqual({
      kind: "upi",
      raw: "upi://pay?pa=Chai.Ramesh@synthbank&pn=Ramesh%20Tea%20Stall&am=40&cu=INR&mc=5812",
      payeeVpa: "chai.ramesh@synthbank",
      payeeName: "Ramesh Tea Stall",
      amount: 40,
      merchantCode: "5812",
      note: undefined,
    });
  });

  it("is case-insensitive about the scheme and keys", () => {
    const qr = parseQr("UPI://PAY?PA=a.b@synthbank&PN=A");
    expect(qr.kind).toBe("upi");
  });

  it.each([
    ["https://kyc-verify.synthbank.example/update", "link"],
    ["upi://collect?pa=a@synthbank", "upi_other"],
    ["upi://pay?pn=NoPayee", "no_payee"],
    ["upi://pay?pa=not-a-vpa", "no_payee"],
    ["hello", "text"],
  ])("%s is not a payment (%s)", (text, reason) => {
    expect(parseQr(text)).toMatchObject({ kind: "not_upi", reason });
  });

  it("ignores a missing or bad amount", () => {
    const qr = parseQr("upi://pay?pa=ab@synthbank&am=abc");
    expect(qr.kind).toBe("upi");
    expect(qr.kind === "upi" ? qr.amount : "n/a").toBeUndefined();
  });

  it("hostOf shows only the site", () => {
    expect(hostOf("https://kyc-verify.synthbank.example/update?x=1")).toBe(
      "kyc-verify.synthbank.example",
    );
  });
});
