-- Payer features, one row per payer_id. Columns match features.json "payers" exactly.
-- Same definitions as data/generator/features.py; data/bq/verify.py checks the two agree.
--   median_amount  exact median of outgoing amounts in the window (PERCENTILE_CONT 0.5)
--   avg_daily_txn  outgoing count / window_days
--   txn_count_1h   outgoing count with ts in (as_of - 1h, as_of]
--   txn_count_24h  outgoing count with ts in (as_of - 24h, as_of]
-- "Now" is meta.as_of (the end of the synthetic history). For live traffic, swap it for
-- CURRENT_TIMESTAMP(). Pinned demo rows (demo_payer_features) win over generated ones.
CREATE OR REPLACE VIEW `{{project}}.{{dataset}}.v_payer_features`
OPTIONS (description = 'Payer behaviour features for the agents (TRUSTSHIELD_FEATURE_STORE=bigquery).')
AS
WITH
  meta AS (
    SELECT as_of, window_days FROM `{{project}}.{{dataset}}.meta` LIMIT 1
  ),
  outgoing AS (
    SELECT t.payer_id, t.amount, t.ts, m.as_of, m.window_days
    FROM `{{project}}.{{dataset}}.transactions` AS t
    CROSS JOIN meta AS m
    WHERE t.ts >= TIMESTAMP_SUB(m.as_of, INTERVAL m.window_days DAY)
      AND t.ts <= m.as_of
  ),
  medians AS (
    SELECT DISTINCT
      payer_id,
      PERCENTILE_CONT(amount, 0.5) OVER (PARTITION BY payer_id) AS median_amount
    FROM outgoing
  ),
  counts AS (
    SELECT
      payer_id,
      COUNT(*) AS n,
      COUNTIF(ts > TIMESTAMP_SUB(as_of, INTERVAL 1 HOUR)) AS txn_count_1h,
      COUNTIF(ts > TIMESTAMP_SUB(as_of, INTERVAL 24 HOUR)) AS txn_count_24h,
      ANY_VALUE(window_days) AS window_days
    FROM outgoing
    GROUP BY payer_id
  ),
  generated AS (
    SELECT
      c.payer_id,
      ROUND(m.median_amount, 2) AS median_amount,
      ROUND(c.n / c.window_days, 3) AS avg_daily_txn,
      c.txn_count_1h,
      c.txn_count_24h
    FROM counts AS c
    JOIN medians AS m USING (payer_id)
  ),
  pinned AS (
    SELECT payer_id, median_amount, avg_daily_txn, txn_count_1h, txn_count_24h
    FROM `{{project}}.{{dataset}}.demo_payer_features`
  )
SELECT * FROM pinned
UNION ALL
SELECT g.*
FROM generated AS g
-- NOT EXISTS, not NOT IN: stays correct even if a pinned key were ever NULL.
WHERE NOT EXISTS (SELECT 1 FROM pinned AS p WHERE p.payer_id = g.payer_id)
