PRAGMA foreign_keys = ON;

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE clusters (
  cluster_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  department TEXT NOT NULL,
  commune TEXT NOT NULL,
  agro_zone TEXT NOT NULL,
  latitude REAL, longitude REAL
);

CREATE TABLE households (
  household_id TEXT PRIMARY KEY,
  farmer_code TEXT NOT NULL UNIQUE,
  cluster_id TEXT NOT NULL REFERENCES clusters(cluster_id),
  crop TEXT NOT NULL,
  variety TEXT,
  area_ha REAL,
  soil_type TEXT,
  drainage TEXT,
  has_irrigation INTEGER NOT NULL DEFAULT 0,
  planting_status TEXT NOT NULL,
  planned_planting_date TEXT,
  planting_date TEXT,
  seed_in_hand INTEGER
);

CREATE TABLE rainfall_observations (
  cluster_id TEXT NOT NULL REFERENCES clusters(cluster_id),
  obs_date TEXT NOT NULL,
  rainfall_mm REAL NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY (cluster_id, obs_date)
);

CREATE TABLE rainfall_forecast (
  cluster_id TEXT NOT NULL REFERENCES clusters(cluster_id),
  forecast_date TEXT NOT NULL,
  expected_mm REAL NOT NULL,
  rain_probability REAL NOT NULL,
  issued_on TEXT NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY (cluster_id, forecast_date)
);

CREATE TABLE crop_calendar (
  crop TEXT NOT NULL,
  agro_zone TEXT NOT NULL,
  season TEXT NOT NULL,
  window_start TEXT NOT NULL,
  window_end TEXT NOT NULL,
  onset_rain_mm REAL NOT NULL,
  max_safe_dry_spell_days INTEGER NOT NULL,
  establishment_days INTEGER NOT NULL,
  notes TEXT,
  PRIMARY KEY (crop, agro_zone, season)
);

CREATE TABLE crop_varieties (
  crop TEXT NOT NULL,
  variety TEXT NOT NULL,
  maturity_days INTEGER NOT NULL,
  drought_tolerance TEXT NOT NULL,
  PRIMARY KEY (crop, variety)
);

CREATE TABLE pest_reports (
  report_id TEXT PRIMARY KEY,
  cluster_id TEXT NOT NULL REFERENCES clusters(cluster_id),
  report_date TEXT NOT NULL,
  pest TEXT NOT NULL,
  crop TEXT NOT NULL,
  severity TEXT NOT NULL,
  fields_scouted INTEGER NOT NULL,
  fields_affected INTEGER NOT NULL,
  growth_stage TEXT,
  reporter_code TEXT NOT NULL
);

CREATE TABLE audit_log (
  call_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  ts_utc TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  arguments_json TEXT NOT NULL,
  status TEXT NOT NULL,
  duration_ms INTEGER NOT NULL,
  result_sha256 TEXT,
  result_summary TEXT,
  result_count INTEGER,
  error TEXT
);
CREATE INDEX idx_audit_session ON audit_log(session_id, ts_utc);
