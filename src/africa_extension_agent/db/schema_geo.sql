-- Idempotent: applied on seed AND on service start, so existing databases upgrade in place.
CREATE TABLE IF NOT EXISTS plots (
  plot_id TEXT PRIMARY KEY,
  household_id TEXT NOT NULL UNIQUE REFERENCES households(household_id),
  geometry_geojson TEXT,
  centroid_lat REAL, centroid_lon REAL,
  area_computed_ha REAL,
  geometry_source TEXT NOT NULL,     -- cadastre_andf | officer_gps | satellite_field | cooperative_file | village_only | synthetic
  verification_level TEXT NOT NULL,  -- cadastral | officer_surveyed | officer_matched | satellite_candidate | declared | synthetic_test
  gps_accuracy_m REAL,
  captured_on TEXT,
  tenure_type TEXT,                  -- certificate | customary | leased | sharecropped | unknown
  village TEXT, arrondissement TEXT,
  source_record_id TEXT,
  matched_by TEXT, matched_at TEXT
);
CREATE TABLE IF NOT EXISTS field_candidates (
  candidate_id TEXT PRIMARY KEY,
  source TEXT NOT NULL, source_record_id TEXT,
  geometry_geojson TEXT NOT NULL,
  centroid_lat REAL NOT NULL, centroid_lon REAL NOT NULL,
  area_ha REAL NOT NULL, confidence REAL,
  imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fc_pos ON field_candidates(centroid_lat, centroid_lon);
CREATE TABLE IF NOT EXISTS weather_cells (
  cell_id TEXT PRIMARY KEY, center_lat REAL NOT NULL, center_lon REAL NOT NULL, step_deg REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS weather_obs_grid (
  cell_id TEXT NOT NULL REFERENCES weather_cells(cell_id), obs_date TEXT NOT NULL, rainfall_mm REAL NOT NULL,
  source TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY (cell_id, obs_date)
);
CREATE TABLE IF NOT EXISTS weather_fc_grid (
  cell_id TEXT NOT NULL REFERENCES weather_cells(cell_id), forecast_date TEXT NOT NULL, expected_mm REAL NOT NULL,
  rain_probability REAL NOT NULL, issued_on TEXT NOT NULL, source TEXT NOT NULL, fetched_at TEXT NOT NULL,
  PRIMARY KEY (cell_id, forecast_date)
);
-- Append-only record of every officer plot<->field match (who, when, what it replaced).
CREATE TABLE IF NOT EXISTS plot_match_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, plot_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
  officer TEXT NOT NULL, ts_utc TEXT NOT NULL, previous_source TEXT, previous_verification TEXT
);
