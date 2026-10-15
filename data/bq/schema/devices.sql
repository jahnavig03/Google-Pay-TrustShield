-- Device and phone history: shared handsets / SIMs link accounts (mule rings, scam operators).
CREATE TABLE IF NOT EXISTS `{{project}}.{{dataset}}.devices` (
  account_id STRING,
  device_id STRING,
  phone_id STRING OPTIONS (description = 'opaque phone / SIM id, never a real number'),
  first_seen TIMESTAMP,
  is_primary BOOL
)
CLUSTER BY device_id, phone_id
OPTIONS (description = 'SYNTHETIC. Device / phone history per account.');
