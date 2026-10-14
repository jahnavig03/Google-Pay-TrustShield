You are reading a screenshot of a UPI payment receipt that a customer showed to a shop owner.
The image is synthetic test data.

Read exactly what is printed. Do not guess or correct anything:
- amount: the amount paid in rupees, as a number (12,000.00 -> 12000). null if unreadable.
- txn_id: the UPI transaction / reference id (UTR), digits as printed. null if missing.
- vpa: the UPI id the money was paid TO (looks like name@bank). null if missing.
- timestamp: the payment date and time as ISO 8601. Use +05:30 unless the receipt shows another
  zone. null if missing.
- tamper_hints: first compare the typeface of the AMOUNT with the typeface of the other text
  on the receipt (labels, VPA, transaction id, date). Look at letter shapes: serif vs sans-serif,
  stroke contrast, the shape of digits such as 1, 2 and 0. Then list a hint only when you can
  see it in the image:
  - font_mismatch: the amount (or another key field) is set in a different typeface from the
    rest of the receipt, e.g. a serif amount on a sans-serif receipt. Size or boldness alone
    is normal for an amount and is NOT a mismatch.
  - edited_region: a patch, smudge, blur or background colour change around a key field
  - misaligned_text: a key field is out of line with the text around it
  - unusual_layout: the receipt doesn't look like a standard payment app receipt
  Return an empty list if the receipt looks normal.

Answer with the JSON object only.
