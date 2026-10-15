-- One row: the synthetic world's clock. The feature views compute "as of" this, not
-- CURRENT_TIMESTAMP(), because the generated history ends at AS_OF.
CREATE TABLE IF NOT EXISTS `{{project}}.{{dataset}}.meta` (
  as_of TIMESTAMP,
  window_days INT64,
  recent_vpa_days INT64,
  seed INT64
)
OPTIONS (description = 'Generator parameters for the loaded dataset.');
