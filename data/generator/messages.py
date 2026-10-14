"""message_context text attached to synthetic payments (the message that asked the payer to pay).

These templates feed the *training data* only. The held-out eval set
(evals/heldout_messages.jsonl) is written separately and shares no text with them.
"""

from __future__ import annotations

import random

SCAM_TEMPLATES: dict[str, list[str]] = {
    "urgency": [
        "URGENT: your account will be frozen in 1 hour. Move Rs {amount} to the safe account given by our officer to protect it.",
        "Final warning from bank security team. Suspicious login found. Transfer Rs {amount} now or all funds will be locked.",
        "Sir aapka account aaj block ho raha hai. Abhi Rs {amount} safe account mein transfer karo, baad mein wapas mil jayega.",
        "Your debit card and UPI will stop tonight. Pay Rs {amount} immediately to the verification desk to continue services.",
        "Jaldi karo, 30 min mein account seal ho jayega. Rs {amount} is UPI pe bhejo aur screenshot share karo.",
    ],
    "fake_kyc": [
        "Your KYC is pending. Pay Rs {amount} verification charge today or wallet will be deactivated.",
        "KYC update required as per new rules. Complete by paying Rs {amount} to the KYC desk UPI ID.",
        "Aapka KYC expire ho gaya hai. Rs {amount} fees bhejo, warna kal se payment band.",
        "Dear user, PAN not linked. Pay Rs {amount} processing fee to link and avoid suspension.",
    ],
    "fake_refund": [
        "We sent you Rs {double} by mistake as refund. Please return Rs {amount} to this UPI ID.",
        "Your order refund of Rs {amount} is stuck. Pay Rs {amount} first to release it, it will come back double.",
        "Galti se aapko refund chala gaya. Please Rs {amount} wapas bhej do, customer care se bol raha hoon.",
        "Refund processing needs a one time security deposit of Rs {amount}. It is fully refundable.",
    ],
    "receive_money_first": [
        "You have won a cashback of Rs {double}. Approve the collect request of Rs {amount} to receive it.",
        "Buyer here for your OLX item. I sent a request, just enter PIN to receive Rs {amount}.",
        "Lottery prize Rs {double} ready. Accept the request of Rs {amount} to get the money in your account.",
        "Paisa receive karne ke liye request accept karo, Rs {amount} turant aa jayega.",
    ],
    "qr_swap": [
        "Scan this QR to pay {merchant}",
        "Pay {merchant} - new QR, old one not working",
        "{merchant} payments - scan and pay",
    ],
}

LEGIT_URGENT = {
    "big_legit_rent": [
        "Rent for this month Rs {amount}. Please pay by the 5th.",
        "Bhai rent bhej dena aaj, Rs {amount}. Thanks.",
    ],
    "big_legit_fees": [
        "Term fee of Rs {amount} due by Friday. Late fee applies after that.",
        "Exam form fee Rs {amount}, last date today. Pay at the school counter or UPI.",
    ],
    "big_legit_gift": [
        "Happy birthday! Sending Rs {amount} as gift, enjoy.",
        "Shaadi ka shagun, Rs {amount}. Bahut badhai!",
    ],
    "big_legit_medical": [
        "Hospital deposit Rs {amount} needed before the procedure today.",
        "Pharmacy bill Rs {amount}, please pay at the counter.",
    ],
    "new_genuine_payee": [
        "Plumber visit done, Rs {amount} please.",
        "Tuition fee for this month Rs {amount}. Thank you.",
        "Bill split for dinner, your share Rs {amount}.",
        "Cab driver: Rs {amount} for the airport drop.",
        "Electrician charges Rs {amount}, thank you sir.",
    ],
}

NORMAL_NOTES = [
    "dinner",
    "groceries",
    "movie tickets",
    "petrol",
    "chai",
    "lunch split",
    "auto fare",
    "recharge",
    "thanks!",
    "trip expenses",
]


def scam_message(rng: random.Random, archetype: str, amount: float, merchant: str = "") -> str:
    template = rng.choice(SCAM_TEMPLATES[archetype])
    return template.format(amount=f"{amount:,.0f}", double=f"{amount * 2:,.0f}", merchant=merchant)


def legit_message(rng: random.Random, kind: str, amount: float) -> str:
    return rng.choice(LEGIT_URGENT[kind]).format(amount=f"{amount:,.0f}")
