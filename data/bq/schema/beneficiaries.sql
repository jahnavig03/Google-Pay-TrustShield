-- When each payer added each payee (beneficiary age at payment time = ts - added_at).
CREATE TABLE IF NOT EXISTS `{{project}}.{{dataset}}.beneficiaries` (
  payer_id STRING,
  payee_vpa STRING,
  payee_account_id STRING,
  added_at TIMESTAMP
)
CLUSTER BY payer_id
OPTIONS (description = 'SYNTHETIC. Payer -> payee relationships.');
