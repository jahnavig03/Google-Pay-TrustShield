-- Every VPA in the synthetic world: users, merchants, scammer and mule accounts.
CREATE TABLE IF NOT EXISTS `{{project}}.{{dataset}}.accounts` (
  account_id STRING,
  vpa STRING,
  account_type STRING OPTIONS (description = 'user | merchant | scammer | mule'),
  display_name STRING,
  home_city STRING,
  created_at TIMESTAMP OPTIONS (description = 'when the VPA was created'),
  merchant_id STRING,
  ring_id STRING OPTIONS (description = 'mule ring, for mule accounts')
)
CLUSTER BY account_id
OPTIONS (description = 'SYNTHETIC. Accounts / VPAs. Loaded from data/out/accounts.parquet.');
