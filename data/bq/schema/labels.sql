-- Ground truth per transaction (training labels for BQML; never shown to the risk engine).
CREATE TABLE IF NOT EXISTS `{{project}}.{{dataset}}.labels` (
  txn_id STRING,
  is_scam BOOL,
  scam_type STRING OPTIONS (description = 'urgency | fake_kyc | fake_refund | receive_money_first | qr_swap | mule_layering | none'),
  ring_id STRING OPTIONS (description = 'ring_a | ring_b for mule-ring payments'),
  is_hard_negative BOOL,
  hard_negative_type STRING,
  intended_payee_vpa STRING OPTIONS (description = 'qr_swap: the shop the payer meant to pay'),
  reported_by_user BOOL,
  reported_at TIMESTAMP
)
CLUSTER BY txn_id
OPTIONS (description = 'SYNTHETIC. Labels, one row per transaction.');
