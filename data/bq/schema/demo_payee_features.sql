-- Pinned demo payees, unioned into v_payee_features.
CREATE TABLE IF NOT EXISTS `{{project}}.{{dataset}}.demo_payee_features` (
  payee_vpa STRING,
  flags ARRAY<STRING>,
  reported_links INT64,
  fan_in_24h INT64,
  is_merchant BOOL
)
OPTIONS (description = 'Pinned demo rows from data/generator/pinned_features.json.');
