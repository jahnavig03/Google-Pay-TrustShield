-- Pinned demo payers (payer_demo_001..004), unioned into v_payer_features.
CREATE TABLE IF NOT EXISTS `{{project}}.{{dataset}}.demo_payer_features` (
  payer_id STRING,
  median_amount FLOAT64,
  avg_daily_txn FLOAT64,
  txn_count_1h INT64,
  txn_count_24h INT64
)
OPTIONS (description = 'Pinned demo rows from data/generator/pinned_features.json.');
