CREATE TABLE IF NOT EXISTS `{{project}}.{{dataset}}.merchants` (
  merchant_id STRING,
  account_id STRING,
  merchant_vpa STRING,
  name STRING,
  category STRING,
  city STRING
)
OPTIONS (description = 'SYNTHETIC. The 50 merchants (incl. demo MER-DEMO-0042).');
