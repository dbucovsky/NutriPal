-- NutriPal lookup/reference data initialization
--
-- Canonical initialization script for a FRESH schema (run once, after
-- sql/schema.sql, before any real data is imported). Distinct from
-- sql/sample_data.sql, which is illustrative fake data for offline/
-- throwaway-DB review — this file is real reference data meant for an
-- actual working database.
--
-- Seeds: sentinel/status rows, unit conversions, and every lookup table
-- with a small, known, closed vocabulary confirmed directly against real
-- Google Health API responses and a real Google Takeout export (see
-- doc/wiki/Database-Schema.md). Two lookups are deliberately left EMPTY
-- here and populated dynamically by the importer instead, since their
-- real vocabularies are large/open-ended, not small/closed:
--   - lut_data_source (device/app names — grows as new devices appear)
--   - lut_activity_type (Fitbit's numeric activity taxonomy has 100+ values)
--
-- lut_nutrient is the one deliberately CURATED lookup (see
-- doc/wiki/Database-Design-Patterns.md's "curated allowlist" note) — it is
-- seeded here with the full real vocabulary observed in this account's
-- actual nutrition_log.csv (27 distinct nutrient keys), MINUS protein and
-- carbohydrates, which are promoted to top-level columns on
-- food_log_entries instead of stored as child rows. Any nutrient name the
-- importer encounters that isn't in this list is dropped and logged, not
-- auto-added.

USE nutripal;

-- ----------------------------------------------------------------------------
-- Status / sentinels
-- ----------------------------------------------------------------------------

INSERT INTO lut_status (id, name, description) VALUES
    (1, 'none', 'Reserved sentinel status row'),
    (2, 'active', 'Normal active state'),
    (3, 'disabled', 'Deactivated but retained for history'),
    (4, 'left', 'Membership ended (used on link_user_group)');

INSERT INTO users (id, email, name, status_id) VALUES
    (1, NULL, 'system', 1),
    (2, 'damian.bucovsky@gmail.com', 'Damian', 2);

INSERT INTO groups (id, name, status_id) VALUES
    (1, 'none', 1);

-- ----------------------------------------------------------------------------
-- Units — dimensions confirmed needed by real data: mass (nutrients,
-- foods_db), volume (foods_db), length (height, exercise distance)
-- ----------------------------------------------------------------------------

INSERT INTO lut_dimension (id, name, description) VALUES
    (1, 'mass', 'Mass-based quantities, base unit gram'),
    (2, 'volume', 'Volume-based quantities, base unit milliliter'),
    (3, 'length', 'Length-based quantities, base unit millimeter');

INSERT INTO unit_conversions (id, name, dimension_id, factor_to_base) VALUES
    (1, 'microgram', 1, 0.000001),
    (2, 'milligram', 1, 0.001),
    (3, 'gram', 1, 1),
    (4, 'kilogram', 1, 1000),
    (5, 'ounce', 1, 28.3495),
    (6, 'pound', 1, 453.592),
    (7, 'milliliter', 2, 1),
    (8, 'liter', 2, 1000),
    (9, 'teaspoon', 2, 4.92892),
    (10, 'tablespoon', 2, 14.7868),
    (11, 'cup', 2, 236.588),
    (12, 'fluid_ounce', 2, 29.5735),
    (13, 'millimeter', 3, 1),
    (14, 'mile', 3, 1609344),
    (15, 'meter', 3, 1000);

-- ----------------------------------------------------------------------------
-- Our own fixed vocabularies (not externally driven)
-- ----------------------------------------------------------------------------

-- google_takeout kept (not deleted) for historical traceability of any
-- past Takeout-sourced rows still in the database, but is no longer an
-- active ingestion source as of the post-Takeout redesign — see
-- doc/wiki/Database-Schema.md. health_connect is the new source, added
-- alongside the live API.
INSERT INTO lut_ingestion_source (id, name, description) VALUES
    (1, 'google_health_api', 'Live incremental sync from the Google Health API'),
    (2, 'google_takeout', 'Bulk historical import from a Google Takeout export (deprecated, no longer used)'),
    (3, 'mixed', 'Structural conflict between the two sources, resolved'),
    (4, 'nutripal', 'Created directly in the app'),
    (5, 'health_connect', 'Bulk import from an Android Health Connect export');

-- ----------------------------------------------------------------------------
-- Small closed vocabularies confirmed from real Google Health data
-- ----------------------------------------------------------------------------

-- Confirmed complete against this account's real nutrition_log.csv (6234
-- rows, every meal_type value accounted for): SNACK never actually appears,
-- but BEFORE_BREAKFAST/BEFORE_LUNCH/AFTER_DINNER do. Kept SNACK anyway since
-- it's part of Google's documented API vocabulary, just unused in this
-- particular account's history so far.
INSERT INTO lut_meal_type (id, name) VALUES
    (1, 'BREAKFAST'), (2, 'LUNCH'), (3, 'DINNER'), (4, 'SNACK'),
    (5, 'ANYTIME'), (6, 'BEFORE_DINNER'), (7, 'BEFORE_BREAKFAST'),
    (8, 'BEFORE_LUNCH'), (9, 'AFTER_DINNER');

INSERT INTO lut_recording_method (id, name, description) VALUES
    (1, 'ACTIVELY_MEASURED', 'User actively engaged the device/app to record this'),
    (2, 'PASSIVELY_MEASURED', 'Recorded automatically by continuous sensing'),
    (3, 'MANUAL', 'Hand-entered by the user'),
    (4, 'DERIVED', 'Computed/inferred from other data rather than measured directly');

INSERT INTO lut_sleep_type (id, name) VALUES
    (1, 'CLASSIC'), (2, 'STAGES');

INSERT INTO lut_gender (id, name) VALUES
    (1, 'male'), (2, 'female'), (3, 'unspecified');

INSERT INTO lut_max_hr_source (id, name) VALUES
    (1, 'age'), (2, 'observed'), (3, 'manual');

-- AWAKE/LIGHT/DEEP/REM cover the newer STAGES sleep-tracking model;
-- ASLEEP/RESTLESS/UNSPECIFIED are the older, coarser CLASSIC-mode
-- vocabulary (older/less capable trackers) — confirmed present in real
-- data (~0.45% of this account's sleep stage rows use the CLASSIC set).
INSERT INTO lut_sleep_stage_type (id, name) VALUES
    (1, 'AWAKE'), (2, 'LIGHT'), (3, 'DEEP'), (4, 'REM'),
    (5, 'ASLEEP'), (6, 'RESTLESS'), (7, 'UNSPECIFIED');

INSERT INTO lut_heart_rate_calc_method (id, name) VALUES
    (1, 'WITH_SLEEP');

INSERT INTO lut_measurement_type (id, name, description) VALUES
    (1, 'weight', 'Body weight'),
    (2, 'height', 'Body height');

-- Needed now that food_log_entries.serving_unit_id is required (not
-- optional traceability) — every logged food must resolve to a real
-- serving unit. 'gram' covers the common case where a source (Health
-- Connect, in particular) reports absolute nutrition with no separate
-- serving size, so quantity is nominally treated as grams.
INSERT INTO lut_serving_unit (id, label, unit_conversion_id) VALUES
    (1, 'gram', (SELECT id FROM unit_conversions WHERE name = 'gram'));

-- ----------------------------------------------------------------------------
-- lut_nutrient — curated, drop-if-unmapped at ingest. Combines the original
-- Google Takeout nutrition_log.csv vocabulary (27 keys, excluding PROTEIN/
-- CARBOHYDRATES — top-level foods_db columns, not child rows) with the
-- additional real nutrients confirmed in Health Connect's nutrition_record
-- table (manganese, selenium, chloride, molybdenum, chromium, vitamin K,
-- caffeine, and folate as a distinct nutrient from folic acid). HC's
-- total_fat/energy/energy_from_fat are likewise excluded — top-level
-- columns/derived summaries, not child rows. LEUCINE kept as a
-- never-reported-by-any-source illustrative example (would only ever be
-- entered by hand).
-- ----------------------------------------------------------------------------

INSERT INTO lut_nutrient (id, name) VALUES
    (1, 'SODIUM'), (2, 'POTASSIUM'), (3, 'DIETARY_FIBER'), (4, 'SUGAR'),
    (5, 'CALCIUM'), (6, 'IRON'), (7, 'VITAMIN_A'), (8, 'VITAMIN_C'),
    (9, 'CHOLESTEROL'), (10, 'SATURATED_FAT'), (11, 'LEUCINE'),
    (12, 'TRANS_FAT'), (13, 'BIOTIN'), (14, 'COPPER'), (15, 'FOLIC_ACID'),
    (16, 'IODINE'), (17, 'MAGNESIUM'), (18, 'NIACIN'),
    (19, 'PANTOTHENIC_ACID'), (20, 'PHOSPHORUS'), (21, 'RIBOFLAVIN'),
    (22, 'THIAMIN'), (23, 'VITAMIN_B12'), (24, 'VITAMIN_B6'),
    (25, 'VITAMIN_D'), (26, 'VITAMIN_E'), (27, 'ZINC'),
    (28, 'MANGANESE'), (29, 'SELENIUM'), (30, 'CHLORIDE'),
    (31, 'MOLYBDENUM'), (32, 'CHROMIUM'), (33, 'VITAMIN_K'),
    (34, 'CAFFEINE'), (35, 'FOLATE');
