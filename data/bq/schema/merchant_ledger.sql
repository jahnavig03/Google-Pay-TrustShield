-- PayGuard's source of truth: credits (settled / pending) and refunds per merchant.
CREATE TABLE IF NOT EXISTS `{{project}}.{{dataset}}.merchant_ledger` (
  ledger_entry_id STRING,
  merchant_id STRING,
  merchant_vpa STRING,
  entry_type STRING OPTIONS (description = 'credit | refund'),
  txn_id STRING,
  amount FLOAT64,
  counterparty_vpa STRING OPTIONS (description = 'payer for a credit, recipient for a refund'),
  initiated_at TIMESTAMP,
  settled_at TIMESTAMP,
  status STRING OPTIONS (description = 'settled | pending'),
  refund_of_txn_id STRING,
  refund_abuse_pattern STRING OPTIONS (description = 'none | serial_refunder | refund_exceeds_original | refund_to_different_vpa | duplicate_refund')
)
CLUSTER BY merchant_id, txn_id
OPTIONS (description = 'SYNTHETIC. Merchant ledger for PayGuard.');
