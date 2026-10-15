-- UPI payments over the 90-day window, with device and location context.
CREATE TABLE IF NOT EXISTS `{{project}}.{{dataset}}.transactions` (
  txn_id STRING OPTIONS (description = '12-digit UPI reference (UTR-like)'),
  ts TIMESTAMP,
  payer_id STRING,
  payer_vpa STRING,
  payee_vpa STRING,
  payee_account_id STRING,
  amount FLOAT64,
  currency STRING,
  channel STRING OPTIONS (description = 'p2p | p2m | qr | collect'),
  device_id STRING,
  device_changed BOOL OPTIONS (description = 'first payment from a device the payer never used before'),
  city STRING,
  lat FLOAT64,
  lon FLOAT64,
  location_changed BOOL OPTIONS (description = 'paid from outside the home city'),
  beneficiary_age_minutes INT64 OPTIONS (description = 'minutes since the payer added this payee'),
  message_context STRING OPTIONS (description = 'the message that asked the payer to pay, if any'),
  status STRING
)
CLUSTER BY payer_id, payee_account_id
OPTIONS (description = 'SYNTHETIC. 50,000 UPI payments.');
