-- Payee features, one row per lower-case payee VPA that received at least one payment.
-- Columns match features.json "payees" exactly. Same definitions as data/generator/features.py.
--   flags           'reported_by_users'    a payment into it was reported by the payer
--                   'vpa_created_recently' account created within meta.recent_vpa_days of as_of
--   reported_links  distinct OTHER accounts sharing a device_id or phone_id with the payee that
--                   received at least one payment labelled is_scam (mule / operator links)
--   fan_in_24h      distinct payers into the payee with ts in (as_of - 24h, as_of]
--   is_merchant     account_type = 'merchant'
-- Pinned demo rows (demo_payee_features) win over generated ones.
CREATE OR REPLACE VIEW `{{project}}.{{dataset}}.v_payee_features`
OPTIONS (description = 'Payee risk features for the agents (TRUSTSHIELD_FEATURE_STORE=bigquery).')
AS
WITH
  meta AS (
    SELECT as_of, window_days, recent_vpa_days FROM `{{project}}.{{dataset}}.meta` LIMIT 1
  ),
  tx AS (
    SELECT t.txn_id, t.payer_id, t.payee_account_id, t.ts, m.as_of
    FROM `{{project}}.{{dataset}}.transactions` AS t
    CROSS JOIN meta AS m
    WHERE t.ts >= TIMESTAMP_SUB(m.as_of, INTERVAL m.window_days DAY)
      AND t.ts <= m.as_of
  ),
  labelled AS (
    SELECT tx.payee_account_id, l.is_scam, l.reported_by_user, l.reported_at, tx.as_of
    FROM tx
    JOIN `{{project}}.{{dataset}}.labels` AS l USING (txn_id)
  ),
  scam_labelled AS (
    SELECT DISTINCT payee_account_id AS account_id FROM labelled WHERE is_scam
  ),
  reported AS (
    SELECT DISTINCT payee_account_id AS account_id
    FROM labelled
    WHERE reported_by_user AND reported_at <= as_of
  ),
  -- Accounts linked through a shared handset or SIM (two equi-joins; BigQuery prefers them to OR).
  links AS (
    SELECT a.account_id, b.account_id AS other_id
    FROM `{{project}}.{{dataset}}.devices` AS a
    JOIN `{{project}}.{{dataset}}.devices` AS b USING (device_id)
    WHERE a.account_id != b.account_id
    UNION DISTINCT
    SELECT a.account_id, b.account_id AS other_id
    FROM `{{project}}.{{dataset}}.devices` AS a
    JOIN `{{project}}.{{dataset}}.devices` AS b USING (phone_id)
    WHERE a.account_id != b.account_id
  ),
  link_counts AS (
    SELECT l.account_id, COUNT(DISTINCT l.other_id) AS reported_links
    FROM links AS l
    JOIN scam_labelled AS s ON s.account_id = l.other_id
    GROUP BY l.account_id
  ),
  fan_in AS (
    SELECT payee_account_id AS account_id, COUNT(DISTINCT payer_id) AS fan_in_24h
    FROM tx
    WHERE ts > TIMESTAMP_SUB(as_of, INTERVAL 24 HOUR)
    GROUP BY payee_account_id
  ),
  generated AS (
    SELECT
      LOWER(a.vpa) AS payee_vpa,
      ARRAY_CONCAT(
        IF(r.account_id IS NOT NULL, ['reported_by_users'], ARRAY<STRING>[]),
        IF(
          a.created_at >= TIMESTAMP_SUB(m.as_of, INTERVAL m.recent_vpa_days DAY),
          ['vpa_created_recently'],
          ARRAY<STRING>[]
        )
      ) AS flags,
      COALESCE(lc.reported_links, 0) AS reported_links,
      COALESCE(f.fan_in_24h, 0) AS fan_in_24h,
      a.account_type = 'merchant' AS is_merchant
    FROM (SELECT DISTINCT payee_account_id AS account_id FROM tx) AS p
    JOIN `{{project}}.{{dataset}}.accounts` AS a USING (account_id)
    CROSS JOIN meta AS m
    LEFT JOIN reported AS r USING (account_id)
    LEFT JOIN link_counts AS lc USING (account_id)
    LEFT JOIN fan_in AS f USING (account_id)
  ),
  pinned AS (
    SELECT LOWER(payee_vpa) AS payee_vpa, flags, reported_links, fan_in_24h, is_merchant
    FROM `{{project}}.{{dataset}}.demo_payee_features`
  )
SELECT * FROM pinned
UNION ALL
SELECT g.*
FROM generated AS g
WHERE g.payee_vpa NOT IN (SELECT payee_vpa FROM pinned)
