-- NutriPal database schema (V2 checkpoint)
--
-- CHECKPOINT, NOT FINAL. This is the post-Takeout redesign: Google Takeout
-- is no longer an ingestion source for anything (Health Connect + the live
-- API only, going forward) — see doc/wiki/Database-Schema.md for the full
-- rationale per category. Major changes from the V1 checkpoint: food_log_
-- entries is now a strict reference (food_id + quantity, never a snapshot);
-- food_log_nutrients and the SRC/FIX/MOD modifier pattern are gone entirely
-- (foods_db versioning is now the sole correction mechanism); `fingerprint`
-- is gone everywhere (native IDs from the two remaining sources are the
-- sole identity mechanism); sleep_sessions dropped its score/summary columns.
-- Still open: the deferred cross-source reconciliation logic (upsert
-- priority, mixed-conflict resolution, tolerance-based foods_db version
-- matching) noted throughout — see doc/wiki/Database-Schema.md's Open Items.
--
-- ============================================================================
-- GENERAL PATTERNS (see doc/wiki/Database-Design-Patterns.md for full writeup)
-- ============================================================================
--
-- No ENUM types anywhere. Every categorical/enumerated concept is a lookup
-- table instead, prefixed `lut_` + singular field name (e.g. lut_status).
-- Many-to-many junction tables are prefixed `link_` (e.g. link_user_group).
-- A junction-like table that carries substantial data of its own beyond the
-- relationship (e.g. foods_db_last_used) keeps a descriptive name instead.
--
-- Every main table carries:
--   db_ts, created_ts, changed_by, changed_by_user_id
-- and gets a parallel <table>_hist table:
--   id_hist, db_hist_ts, <natural key columns>, valid_start_ts, valid_end_ts,
--   plus every other real column, copied from the PRE-update state.
--
-- Enforced via triggers, not application code:
--   - INSERT: <table>_hist untouched.
--   - UPDATE: a BEFORE UPDATE trigger unconditionally copies the pre-update
--     row into <table>_hist (no change-detection in the trigger — whether an
--     UPDATE should even be issued is the application's job, not the DB's),
--     and forces id/created_ts to stay unchanged.
--   - DELETE: a BEFORE DELETE trigger unconditionally raises an error.
--     "Deletion" is a status change instead (see lut_status).
--
-- changed_by/changed_by_user_id are explicit values the application always
-- supplies (no MySQL session variables) — unset means a direct DB write, not
-- something the app did. changed_by_user_id is not FK-enforced in this
-- checkpoint (avoids table-creation-order bootstrapping issues); it
-- conceptually always references users.id.
--
-- Identity/dedup across sources (Health Connect + the live API) relies
-- solely on `api_uid` — a real native ID (HC's uuid, or the API's dataPoint
-- ID) is available from at least one, usually both, remaining sources for
-- every table except sleep_stages (neither source provides a per-stage ID).
-- No content-hash fingerprint exists anywhere in this schema — it was
-- dropped once Takeout (the source most likely to lack any native ID) was
-- removed; tables with no native ID available (steps/heart-rate/HRV/
-- sleep-stages) currently have no DB-level duplicate guard at all, deferred
-- to application logic. See doc/wiki/Database-Schema.md.
--
-- Every user-owned table (including child tables, not just parents) carries
-- user_id directly, and every uniqueness constraint is scoped per-user.
--
-- ============================================================================
-- TWO SCHEMAS: `nutripal` (live data) + `nutripal_hist` (every _hist table)
-- ============================================================================
--
-- Split so history — which grows much faster than live data — can be backed
-- up, dumped, or eventually archived on its own cadence without touching the
-- live schema. Every _hist CREATE TABLE below is schema-qualified
-- (nutripal_hist.<table>_hist); main tables are created under the `nutripal`
-- default (see USE below). Cross-schema DML/FKs work fine in MySQL as long as
-- both schemas are on the same server (true locally and on Bluehost's shared
-- server) — each BEFORE UPDATE trigger's INSERT into its _hist table is
-- schema-qualified for exactly this reason (an unqualified name inside a
-- trigger resolves to the trigger's OWN schema, i.e. `nutripal`, not
-- `nutripal_hist`). No hist table declares a foreign key back to its main
-- table (verified: none exist in this file), so this split needed no other
-- structural change.
--
-- IMPORTANT — Bluehost naming: Bluehost's cPanel prefixes every database (and
-- DB user) name with an account-specific prefix (e.g. `theshaf2_`). The hist
-- schema name is baked literally into every trigger body below (raw SQL can't
-- parameterize identifiers), so deploying to Bluehost requires first
-- replacing every `nutripal_hist` occurrence in this file with the real
-- prefixed name (e.g. `theshaf2_nutripal_hist`) — this is a manual, one-time
-- find-and-replace step per deploy, not automated by anything yet.
--
-- ============================================================================

CREATE DATABASE IF NOT EXISTS nutripal;
CREATE DATABASE IF NOT EXISTS nutripal_hist;
USE nutripal;

-- ----------------------------------------------------------------------------
-- Lookup tables
-- ----------------------------------------------------------------------------

CREATE TABLE lut_status (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_status_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_status_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_status_hist_id (id)
) ENGINE=InnoDB;

CREATE TABLE lut_ingestion_source (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_ingestion_source_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_ingestion_source_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_ingestion_source_hist_id (id)
) ENGINE=InnoDB;

-- Originally just mass/volume (for foods_db). Extended for `measurements`
-- with length (height), pressure (blood pressure — a single-unit dimension,
-- no real conversions needed), and ratio (percentages, e.g. body fat %).
CREATE TABLE lut_dimension (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_dimension_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_dimension_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_dimension_hist_id (id)
) ENGINE=InnoDB;

CREATE TABLE lut_sleep_stage_type (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_sleep_stage_type_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_sleep_stage_type_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_sleep_stage_type_hist_id (id)
) ENGINE=InnoDB;

CREATE TABLE lut_meal_type (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_meal_type_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_meal_type_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_meal_type_hist_id (id)
) ENGINE=InnoDB;

CREATE TABLE lut_data_source (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_data_source_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_data_source_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_data_source_hist_id (id)
) ENGINE=InnoDB;

-- Deliberately curated, not a passive mirror of Google's data: a nutrient
-- value whose name isn't present here is DROPPED at ingest time, not stored
-- as free text and not auto-added. Adding a new nutrient is a future admin
-- action against this table.
CREATE TABLE lut_nutrient (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_nutrient_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_nutrient_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_nutrient_hist_id (id)
) ENGINE=InnoDB;

-- Google's dailyRestingHeartRateMetadata.calculationMethod (only "WITH_SLEEP"
-- observed in real data so far; likely a small bounded vocabulary).
CREATE TABLE lut_heart_rate_calc_method (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_heart_rate_calc_method_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_heart_rate_calc_method_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_heart_rate_calc_method_hist_id (id)
) ENGINE=InnoDB;

-- Backs the generic `measurements` table below — e.g. 'weight', 'height',
-- 'blood_pressure_systolic', 'blood_pressure_diastolic', 'body_fat_percent'.
-- A multi-value reading (blood pressure) is two separate type rows, not one.
CREATE TABLE lut_measurement_type (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_measurement_type_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_measurement_type_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_measurement_type_hist_id (id)
) ENGINE=InnoDB;

-- How a reading was captured — distinct from data_source_id (WHICH device/
-- app). Google's live API reports dataSource.recordingMethod
-- (ACTIVELY_MEASURED/PASSIVELY_MEASURED/MANUAL/DERIVED) on every data type;
-- Takeout's exercise export has an analogous logType (auto_detected/
-- tracker/...). Nullable everywhere it's used — most Takeout CSV formats
-- (steps/heart-rate/weight) don't carry this at all.
CREATE TABLE lut_recording_method (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_recording_method_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_recording_method_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_recording_method_hist_id (id)
) ENGINE=InnoDB;

-- Canonical activity types for exercise_sessions. Two disjoint raw
-- vocabularies resolve here: Takeout's Fitbit-legacy numeric activityTypeId
-- (e.g. 90013=Walk, 3000=Workout) and the live API's string exerciseType
-- (e.g. "WALKING") — mapping either raw code to a canonical row is an
-- ingest-time concern, not modeled here.
CREATE TABLE lut_activity_type (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_activity_type_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_activity_type_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_activity_type_hist_id (id)
) ENGINE=InnoDB;

-- CLASSIC/STAGES — confirmed identical vocabulary in both the live API
-- (sleep.type) and Takeout (UserSleeps.sleep_type).
CREATE TABLE lut_sleep_type (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_sleep_type_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_sleep_type_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_sleep_type_hist_id (id)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- Multi-user readiness (schema shape only — no auth/registration UX yet)
-- ----------------------------------------------------------------------------

-- id=1 is a reserved sentinel ("no user" / "system"), never a real account.
-- Real users start at id=2. Exactly one real row is seeded for now.
CREATE TABLE users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NULL,
    name VARCHAR(255) NULL,
    status_id BIGINT UNSIGNED NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    CONSTRAINT fk_users_status FOREIGN KEY (status_id) REFERENCES lut_status(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.users_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    email VARCHAR(255) NULL,
    name VARCHAR(255) NULL,
    status_id BIGINT UNSIGNED NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_users_hist_id (id)
) ENGINE=InnoDB;

-- id=1 is a reserved sentinel ("no group"), real groups start at id=2.
CREATE TABLE groups (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NULL,
    status_id BIGINT UNSIGNED NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    CONSTRAINT fk_groups_status FOREIGN KEY (status_id) REFERENCES lut_status(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.groups_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(255) NULL,
    status_id BIGINT UNSIGNED NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_groups_hist_id (id)
) ENGINE=InnoDB;

-- Membership is many-to-many; priority is this user's own ranking of their
-- groups (strictly unique per user, gaps allowed, e.g. 1, 5, 10).
CREATE TABLE link_user_group (
    user_id BIGINT UNSIGNED NOT NULL,
    group_id BIGINT UNSIGNED NOT NULL,
    priority INT UNSIGNED NOT NULL,
    status_id BIGINT UNSIGNED NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    PRIMARY KEY (user_id, group_id),
    UNIQUE KEY uq_link_user_group_priority (user_id, priority),
    CONSTRAINT fk_link_user_group_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_link_user_group_group FOREIGN KEY (group_id) REFERENCES groups(id),
    CONSTRAINT fk_link_user_group_status FOREIGN KEY (status_id) REFERENCES lut_status(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.link_user_group_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    group_id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    priority INT UNSIGNED NOT NULL,
    status_id BIGINT UNSIGNED NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_link_user_group_hist_key (user_id, group_id)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- foods_db family
-- ----------------------------------------------------------------------------

-- Universal unit conversions, independent of any specific food. Extended
-- with milligram so nutrient quantities can reuse this same table as their
-- single source of truth for units rather than a separate concept.
CREATE TABLE unit_conversions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    dimension_id BIGINT UNSIGNED NOT NULL,
    factor_to_base DECIMAL(18,6) NOT NULL COMMENT 'in the dimension''s own base unit: grams (mass), milliliters (volume), millimeters (length), mmHg (pressure), percent (ratio)',
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_unit_conversions_name (name),
    CONSTRAINT fk_unit_conversions_dimension FOREIGN KEY (dimension_id) REFERENCES lut_dimension(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.unit_conversions_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(64) NOT NULL,
    dimension_id BIGINT UNSIGNED NOT NULL,
    factor_to_base DECIMAL(18,6) NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_unit_conversions_hist_id (id)
) ENGINE=InnoDB;

-- Nutrition always normalized per 100 units of `dimension` (100g or 100mL),
-- matching label convention, so scaling to any logged quantity/unit is the
-- same math regardless of source unit.
--
-- Ownership (three-tier sharing): group_id/user_id sentinel = id 1 in their
-- respective tables ("no group"/"no user"). Universal = both sentinel.
-- Group-owned = real group_id, sentinel user_id. User-owned = real user_id
-- (group_id can be anything, it's provenance only — a non-sentinel user_id
-- alone means user-owned). Resolution priority for a given user U: (1) a row
-- with user_id=U wins outright; (2) else walk U's groups in link_user_group
-- priority order, first match wins; (3) else fall back to the universal row.
-- This resolution logic lives in the application/query layer.
--
-- Versioning: `version` is plain, no self-referencing link. NULL and 0 are
-- equivalent (the original entry is version NULL, displayed as "v0" once a
-- sibling exists). "All versions of a food" = rows sharing
-- (name, brand_name, dimension_id). Real-world need: manufacturers/resellers
-- report slightly different nutrition for "the same" food over time — and
-- now, every food_log_entries row references a SPECIFIC foods_db version
-- (food_id is required, not a snapshot), so versioning is what keeps past
-- logs stable when a food's nutrition genuinely changes: editing in place is
-- never allowed, a real difference always creates a new version instead.
-- Precision noise (floating-point/rounding) must NOT trigger a new version —
-- matching an incoming value against the latest version uses a tolerance,
-- not exact equality; this is application-layer matching logic, not
-- something a DB constraint can express (deferred to ingest-time
-- implementation, alongside the other reconciliation logic).
--
-- No `fingerprint`/provenance columns here (deliberately, unlike every
-- ingested table) — provenance describes how a LOG EVENT reached us, not an
-- inherent property of a catalog food, since many different log events (from
-- different sources, over years) can all reference the same foods_db row.
-- See doc/wiki/Database-Design-Patterns.md. No hard DB-level uniqueness
-- constraint on (name, brand_name, dimension_id, version) either — real
-- uniqueness now depends on the tolerance-based matching above, which only
-- application code can evaluate; idx_foods_db_name below is for lookup
-- performance only, not an integrity constraint.
CREATE TABLE foods_db (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    brand_name VARCHAR(255) NULL,
    dimension_id BIGINT UNSIGNED NOT NULL,
    version INT UNSIGNED NULL,
    group_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    energy_kcal DECIMAL(8,2) NULL,
    is_energy_estimated BOOLEAN NOT NULL DEFAULT FALSE,
    total_protein_g DECIMAL(8,2) NULL,
    total_carbohydrate_g DECIMAL(8,2) NULL,
    total_fat_g DECIMAL(8,2) NULL,
    notes VARCHAR(1000) NULL,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_foods_db_name (name, brand_name),
    CONSTRAINT fk_foods_db_dimension FOREIGN KEY (dimension_id) REFERENCES lut_dimension(id),
    CONSTRAINT fk_foods_db_group FOREIGN KEY (group_id) REFERENCES groups(id),
    CONSTRAINT fk_foods_db_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.foods_db_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    name VARCHAR(255) NOT NULL,
    brand_name VARCHAR(255) NULL,
    dimension_id BIGINT UNSIGNED NOT NULL,
    version INT UNSIGNED NULL,
    group_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    energy_kcal DECIMAL(8,2) NULL,
    is_energy_estimated BOOLEAN NOT NULL,
    total_protein_g DECIMAL(8,2) NULL,
    total_carbohydrate_g DECIMAL(8,2) NULL,
    total_fat_g DECIMAL(8,2) NULL,
    notes VARCHAR(1000) NULL,
    is_archived BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_foods_db_hist_id (id)
) ENGINE=InnoDB;

-- Per-food named units beyond the universal standard ones (e.g. "medium
-- orange", "18in pie slice"). Tied to one specific foods_db row (one
-- version) — not automatically shared across other versions of the food.
CREATE TABLE foods_db_custom_units (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    food_id BIGINT UNSIGNED NOT NULL,
    unit_name VARCHAR(64) NOT NULL,
    equivalent_amount DECIMAL(10,4) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_foods_db_custom_units_name (food_id, unit_name),
    CONSTRAINT fk_foods_db_custom_units_food FOREIGN KEY (food_id) REFERENCES foods_db(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.foods_db_custom_units_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    food_id BIGINT UNSIGNED NOT NULL,
    unit_name VARCHAR(64) NOT NULL,
    equivalent_amount DECIMAL(10,4) NOT NULL,
    is_default BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_foods_db_custom_units_hist_id (id)
) ENGINE=InnoDB;

-- Resolves a food_log_entries.serving_unit_id to whichever real unit
-- definition applies. Exactly one of unit_conversion_id/
-- foods_db_custom_unit_id is populated when the unit is recognized; both may
-- be NULL for a Google-synced entry whose reported label doesn't map to
-- anything defined (the raw `label` is still recorded). Structurally larger/
-- less universal than the other lut_ tables (every food's custom units each
-- get their own row here too), but follows the same naming/history pattern.
CREATE TABLE lut_serving_unit (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(64) NOT NULL,
    unit_conversion_id BIGINT UNSIGNED NULL,
    foods_db_custom_unit_id BIGINT UNSIGNED NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_serving_unit_label (label),
    CONSTRAINT fk_lut_serving_unit_conversion FOREIGN KEY (unit_conversion_id) REFERENCES unit_conversions(id),
    CONSTRAINT fk_lut_serving_unit_custom FOREIGN KEY (foods_db_custom_unit_id) REFERENCES foods_db_custom_units(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_serving_unit_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    label VARCHAR(64) NOT NULL,
    unit_conversion_id BIGINT UNSIGNED NULL,
    foods_db_custom_unit_id BIGINT UNSIGNED NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_serving_unit_hist_id (id)
) ENGINE=InnoDB;

-- Full micronutrient tracking for catalog foods. Sets up a future enrichment
-- workflow: catalog nutrients Google/Health Connect doesn't track can be
-- added here directly (matching/enrichment logic deferred).
-- One row per nutrient per food (version) — no more SRC/FIX/MOD value types:
-- modifiers were dropped entirely in favor of versioning as the sole
-- correction mechanism (a real change to a nutrient value creates a new
-- foods_db version; this row is simply "the value," not one of several
-- competing claims about it).
CREATE TABLE foods_db_nutrients (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    food_id BIGINT UNSIGNED NOT NULL,
    nutrient_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(10,4) NOT NULL,
    unit_id BIGINT UNSIGNED NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_foods_db_nutrients (food_id, nutrient_id),
    CONSTRAINT fk_foods_db_nutrients_food FOREIGN KEY (food_id) REFERENCES foods_db(id),
    CONSTRAINT fk_foods_db_nutrients_nutrient FOREIGN KEY (nutrient_id) REFERENCES lut_nutrient(id),
    CONSTRAINT fk_foods_db_nutrients_unit FOREIGN KEY (unit_id) REFERENCES unit_conversions(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.foods_db_nutrients_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    food_id BIGINT UNSIGNED NOT NULL,
    nutrient_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(10,4) NOT NULL,
    unit_id BIGINT UNSIGNED NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_foods_db_nutrients_hist_id (id)
) ENGINE=InnoDB;

-- Kept separate from foods_db itself to keep high-churn write activity out
-- of the main catalog table. Keyed by (user_id, food_id), not just food_id,
-- since usage is always personal even for a universal/group-owned food.
-- `score` is a bounded, self-decaying recency-weighted frequency (NOT a
-- plain lifetime counter, which would be unbounded and fade too slowly once
-- abandoned) — see doc/wiki/Database-Schema.md for the exact write
-- algorithm and why the decay must be computed before last_used_at is
-- overwritten. `times_used` is a plain lifetime count, display-only, never
-- used for ranking. Does not get a `link_` prefix despite connecting
-- users/foods_db — it carries substantial data of its own, not a pure link.
-- last_serving_amount/last_serving_unit_id: the quantity actually logged
-- last time, cached purely to prefill "log again" — not used for ranking,
-- and NULL until this food has been logged at least once with a serving.
CREATE TABLE foods_db_last_used (
    user_id BIGINT UNSIGNED NOT NULL,
    food_id BIGINT UNSIGNED NOT NULL,
    last_used_at DATETIME NOT NULL,
    times_used INT UNSIGNED NOT NULL DEFAULT 0,
    score DECIMAL(10,4) NOT NULL DEFAULT 0,
    last_serving_amount DECIMAL(8,2) NULL,
    last_serving_unit_id BIGINT UNSIGNED NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    PRIMARY KEY (user_id, food_id),
    CONSTRAINT fk_foods_db_last_used_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_foods_db_last_used_food FOREIGN KEY (food_id) REFERENCES foods_db(id),
    CONSTRAINT fk_foods_db_last_used_serving_unit FOREIGN KEY (last_serving_unit_id) REFERENCES lut_serving_unit(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.foods_db_last_used_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    food_id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at DATETIME NOT NULL,
    times_used INT UNSIGNED NOT NULL,
    score DECIMAL(10,4) NOT NULL,
    last_serving_amount DECIMAL(8,2) NULL,
    last_serving_unit_id BIGINT UNSIGNED NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_foods_db_last_used_hist_key (user_id, food_id)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- Food log (reviewed, final for now)
-- ----------------------------------------------------------------------------

-- end_time is ALWAYS start_time + 1 minute (confirmed against 6,234 of 6,235
-- real Takeout rows) — not a real duration. Google's data model requires
-- every entry to be interval-shaped, so a single moment gets padded into a
-- fixed 1-minute window. Kept as two columns (matches Google's own model,
-- keeps import/export/comparison simple) rather than collapsing to one
-- `consumed_at` column. Any code creating new entries must follow the same
-- convention: end_time = start_time + 1 minute.
--
-- STRICT REFERENCE MODEL: a log entry is always food_id + quantity, never a
-- standalone snapshot. food_id/serving_amount/serving_unit_id are all
-- required (not optional traceability) — there is no other way to represent
-- what was logged. Nutrition is always derived at read time by joining to
-- foods_db/foods_db_nutrients and scaling by the resolved quantity; nothing
-- nutritional is stored on this table. This mirrors how Google itself logs
-- food — one row per ingredient/item (e.g. "Yellow Onion", "Tomatoes",
-- "Breaded Chicken Cutlet" all logged separately under the same meal_type
-- and a shared time window) rather than one row per composed meal — so no
-- separate "meal" grouping construct is needed; a meal is just several rows
-- sharing meal_type_id and a close start_time. A "recipe" (a named template
-- of ingredient+quantity pairs for quickly generating several rows at once)
-- is a wholly separate, not-yet-built concept — it is never referenced here,
-- only expanded into individual rows at logging time.
--
-- No `fingerprint` (dropped everywhere — see
-- doc/wiki/Database-Design-Patterns.md): both remaining ingestion sources
-- (Health Connect, the live API) provide a real native ID per food-log
-- event, so api_uid is now the sole identity mechanism. `nutripal`-created
-- entries (future custom logging) simply have api_uid = NULL and never
-- needed cross-source dedup in the first place.
--
-- App-level invariant (not DB-enforced): if serving_unit_id resolves to a
-- foods_db_custom_units row, that row's own food_id must match this food_id.
CREATE TABLE food_log_entries (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    meal_type_id BIGINT UNSIGNED NOT NULL,
    food_id BIGINT UNSIGNED NOT NULL,
    serving_amount DECIMAL(8,2) NOT NULL,
    serving_unit_id BIGINT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_food_log_entries_api_uid (user_id, api_uid),
    KEY idx_food_log_entries_start_time (user_id, start_time),
    KEY idx_food_log_entries_food (food_id),
    CONSTRAINT fk_food_log_entries_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_food_log_entries_meal_type FOREIGN KEY (meal_type_id) REFERENCES lut_meal_type(id),
    CONSTRAINT fk_food_log_entries_serving_unit FOREIGN KEY (serving_unit_id) REFERENCES lut_serving_unit(id),
    CONSTRAINT fk_food_log_entries_food FOREIGN KEY (food_id) REFERENCES foods_db(id),
    CONSTRAINT fk_food_log_entries_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_food_log_entries_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.food_log_entries_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    meal_type_id BIGINT UNSIGNED NOT NULL,
    food_id BIGINT UNSIGNED NOT NULL,
    serving_amount DECIMAL(8,2) NOT NULL,
    serving_unit_id BIGINT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_food_log_entries_hist_id (id)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- Remaining original health-data tables — carrying forward the columns
-- already drafted pre-checkpoint, with the general patterns (history,
-- ingestion_source/api_uid rename, lookups for data_source/stage_type)
-- layered on mechanically. NOT yet individually re-reviewed table-by-table
-- the way food_log_entries was — expect another pass.
-- ----------------------------------------------------------------------------

CREATE TABLE steps_readings (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    steps INT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_steps_readings_api_uid (user_id, api_uid),
    -- Health Connect gives steps a real per-row uuid, so the key above
    -- catches HC-sourced duplicates - but the live API has no native id for
    -- steps at all, leaving api_uid NULL (a no-op) for every live-sync
    -- insert. A real --full live sync duplicated ~138,000 rows this way
    -- (its dedup preload is deliberately skipped in full mode). Same fix as
    -- heart_rate_readings: enforce the real identity directly.
    UNIQUE KEY uq_steps_readings_reading (user_id, reading_time),
    KEY idx_steps_readings_time (user_id, reading_time),
    CONSTRAINT fk_steps_readings_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_steps_readings_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_steps_readings_recording_method FOREIGN KEY (recording_method_id) REFERENCES lut_recording_method(id),
    CONSTRAINT fk_steps_readings_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.steps_readings_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    steps INT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_steps_readings_hist_id (id)
) ENGINE=InnoDB;

CREATE TABLE heart_rate_readings (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    bpm SMALLINT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_heart_rate_readings_api_uid (user_id, api_uid),
    -- Individual bpm samples have no native per-sample id from any source
    -- (Health Connect's series table and the live API's per-point data both
    -- lack one — only a parent session/recording carries a uuid, if that).
    -- api_uid is therefore always NULL here, making the constraint above a
    -- no-op for this table. One reading per user+timestamp is this table's
    -- actual real-world identity (already assumed by the live sync's
    -- insert-missing dedup) - enforce it for real so every ingest path is
    -- naturally idempotent via INSERT IGNORE, not just the live API path
    -- (which happens to already dedup itself in PHP before inserting).
    UNIQUE KEY uq_heart_rate_readings_reading (user_id, reading_time),
    KEY idx_heart_rate_readings_time (user_id, reading_time),
    CONSTRAINT fk_heart_rate_readings_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_heart_rate_readings_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_heart_rate_readings_recording_method FOREIGN KEY (recording_method_id) REFERENCES lut_recording_method(id),
    CONSTRAINT fk_heart_rate_readings_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.heart_rate_readings_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    bpm SMALLINT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_heart_rate_readings_hist_id (id)
) ENGINE=InnoDB;

-- A distinct DERIVED metric from continuous bpm (root-mean-square of
-- successive beat-interval differences, in milliseconds) — far fewer
-- samples per day than heart_rate_readings, same point-in-time shape.
CREATE TABLE heart_rate_variability_readings (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    rmssd_ms DECIMAL(6,2) NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_heart_rate_variability_readings_api_uid (user_id, api_uid),
    -- Same latent gap as steps_readings/heart_rate_readings, fixed
    -- proactively here even though it hasn't actually duplicated yet: HC
    -- rows get a real api_uid, but the live API's HRV points have no native
    -- id, leaving api_uid NULL for every live-sync insert. Both tables
    -- share the same generic insert function in sync-google-health.php.
    UNIQUE KEY uq_heart_rate_variability_readings_reading (user_id, reading_time),
    KEY idx_heart_rate_variability_readings_time (user_id, reading_time),
    CONSTRAINT fk_heart_rate_variability_readings_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_heart_rate_variability_readings_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_heart_rate_variability_readings_recording_method FOREIGN KEY (recording_method_id) REFERENCES lut_recording_method(id),
    CONSTRAINT fk_heart_rate_variability_readings_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.heart_rate_variability_readings_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    rmssd_ms DECIMAL(6,2) NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_heart_rate_variability_readings_hist_id (id)
) ENGINE=InnoDB;

-- One DERIVED value PER CALENDAR DAY (not a point-in-time reading) — Google
-- computes at most one resting-HR figure per user per day. The natural key
-- IS (user_id, reading_date): no fingerprint/api_uid needed, unlike the
-- point-sample tables, since the date itself is already a stable identity
-- that doesn't change if a resync recalculates the value (that's a plain
-- UPDATE, captured by history as usual).
CREATE TABLE daily_resting_heart_rate (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_date DATE NOT NULL,
    bpm SMALLINT UNSIGNED NOT NULL,
    calculation_method_id BIGINT UNSIGNED NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_daily_resting_heart_rate_date (user_id, reading_date),
    CONSTRAINT fk_daily_resting_heart_rate_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_daily_resting_heart_rate_calc_method FOREIGN KEY (calculation_method_id) REFERENCES lut_heart_rate_calc_method(id),
    CONSTRAINT fk_daily_resting_heart_rate_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_daily_resting_heart_rate_recording_method FOREIGN KEY (recording_method_id) REFERENCES lut_recording_method(id),
    CONSTRAINT fk_daily_resting_heart_rate_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.daily_resting_heart_rate_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_date DATE NOT NULL,
    bpm SMALLINT UNSIGNED NOT NULL,
    calculation_method_id BIGINT UNSIGNED NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_daily_resting_heart_rate_hist_id (id)
) ENGINE=InnoDB;

-- Generic point-in-time scalar body metric (weight, height, blood pressure
-- systolic/diastolic, body fat %, etc.) — one row per (user, type, time).
-- Deliberately generalized instead of one table per metric (like
-- foods_db_nutrients' nutrient_id/quantity/unit_id shape) since new
-- characteristics are just a new lut_measurement_type row, not a migration.
-- A multi-value reading (e.g. blood pressure) becomes multiple rows sharing
-- the same reading_time — the app pairs them back together by matching
-- (user_id, reading_time), same deferred-to-app-logic approach used
-- elsewhere for cross-source reconciliation. Scoped to point-in-time scalar
-- metrics only — steps/heart-rate/exercise/sleep keep their own specialized
-- tables (intervals, sessions, multi-device overlap, high sample volume).
CREATE TABLE measurements (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    measurement_type_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    value DECIMAL(10,4) NOT NULL,
    unit_id BIGINT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_measurements_api_uid (user_id, measurement_type_id, api_uid),
    -- Cross-source duplicate guard: Health Connect and the live API each
    -- assign their own api_uid to the same real reading, so the key above
    -- (real and working per-source) can't catch the same weight/height
    -- value logged by both. Confirmed via real data: 513 of 521 HC weight
    -- readings match a live-API row on this exact triple, even though the
    -- two sources sometimes round the value slightly differently (HC to
    -- the nearest 100g, the live API to the gram) - so value is
    -- deliberately NOT part of this key.
    UNIQUE KEY uq_measurements_reading (user_id, measurement_type_id, reading_time),
    KEY idx_measurements_time (user_id, measurement_type_id, reading_time),
    CONSTRAINT fk_measurements_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_measurements_type FOREIGN KEY (measurement_type_id) REFERENCES lut_measurement_type(id),
    CONSTRAINT fk_measurements_unit FOREIGN KEY (unit_id) REFERENCES unit_conversions(id),
    CONSTRAINT fk_measurements_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_measurements_recording_method FOREIGN KEY (recording_method_id) REFERENCES lut_recording_method(id),
    CONSTRAINT fk_measurements_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.measurements_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    measurement_type_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    value DECIMAL(10,4) NOT NULL,
    unit_id BIGINT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_measurements_hist_id (id)
) ENGINE=InnoDB;

-- activity_type_id resolves two disjoint raw vocabularies to one canonical
-- lut_activity_type row: Takeout's Fitbit-legacy numeric activityTypeId
-- (e.g. 90013, 3000) and the live API's string exerciseType (e.g.
-- "WALKING"). Mapping raw codes to canonical rows is an ingest-time concern,
-- deferred like other reconciliation logic. activity_name stays as the
-- free-text display label already present in both sources (e.g. "Walk").
-- device_name was removed — redundant with data_source_id, which already
-- captures the same "which device/app" concept everywhere else (confirmed:
-- Takeout's exercise source.name and the API's dataSource.device.displayName
-- are the same single concept, not two).
-- distance_unit_id is unit_conversions-backed, not free text. Ingest always
-- normalizes to METERS regardless of source (the live API reports
-- millimeters, Takeout reports miles) — pairing a millimeter-scale value
-- from one source with a mile-scale value from the other in the same
-- DECIMAL column made the precision budget unworkable (a real bug found
-- via sync-google-health.php: DECIMAL(10,4)'s 6 integer digits overflowed
-- on a routine few-km walk expressed in millimeters). distance_unit_id is
-- kept (not hardcoded/dropped) for consistency with this schema's general
-- pattern of always pairing a quantity with an explicit unit reference,
-- even though in practice it will always resolve to 'meter' going forward.
-- has_gps promoted to a real column — present in both sources consistently,
-- cheap and useful for filtering without parsing raw_details JSON.
CREATE TABLE exercise_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NULL,
    activity_name VARCHAR(128) NULL,
    activity_type_id BIGINT UNSIGNED NULL,
    duration_ms INT UNSIGNED NULL,
    active_duration_ms INT UNSIGNED NULL,
    calories INT UNSIGNED NULL,
    distance DECIMAL(10,4) NULL,
    distance_unit_id BIGINT UNSIGNED NULL,
    steps INT UNSIGNED NULL,
    average_heart_rate SMALLINT UNSIGNED NULL,
    has_gps BOOLEAN NOT NULL DEFAULT FALSE,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    raw_details JSON NULL COMMENT 'Heart-rate zones, active-zone-minutes breakdown, GPS points, etc. — preserved but not individually columned in V1',
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_exercise_sessions_api_uid (user_id, api_uid),
    -- Cross-source duplicate guard, same reasoning as measurements above.
    -- Confirmed via real data: 1980 of 2015 HC exercise sessions match a
    -- live-API session on start_time alone, with end_time also matching
    -- exactly in every sampled case (unlike sleep, where end_time can drift
    -- by up to ~1 minute between sources) - start_time alone is still the
    -- safer key, since it's the one guaranteed to align.
    UNIQUE KEY uq_exercise_sessions_start (user_id, start_time),
    KEY idx_exercise_sessions_start_time (user_id, start_time),
    CONSTRAINT fk_exercise_sessions_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_exercise_sessions_activity_type FOREIGN KEY (activity_type_id) REFERENCES lut_activity_type(id),
    CONSTRAINT fk_exercise_sessions_distance_unit FOREIGN KEY (distance_unit_id) REFERENCES unit_conversions(id),
    CONSTRAINT fk_exercise_sessions_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_exercise_sessions_recording_method FOREIGN KEY (recording_method_id) REFERENCES lut_recording_method(id),
    CONSTRAINT fk_exercise_sessions_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.exercise_sessions_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NULL,
    activity_name VARCHAR(128) NULL,
    activity_type_id BIGINT UNSIGNED NULL,
    duration_ms INT UNSIGNED NULL,
    active_duration_ms INT UNSIGNED NULL,
    calories INT UNSIGNED NULL,
    distance DECIMAL(10,4) NULL,
    distance_unit_id BIGINT UNSIGNED NULL,
    steps INT UNSIGNED NULL,
    average_heart_rate SMALLINT UNSIGNED NULL,
    has_gps BOOLEAN NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    raw_details JSON NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_exercise_sessions_hist_id (id)
) ENGINE=InnoDB;

-- sleep_type_id: CLASSIC/STAGES — nullable, since Health Connect has no
-- equivalent concept at all (sessions are just start/end + stages there).
-- main_sleep: distinguishes an overnight sleep from a nap (API's
-- `mainSleep`) — also nullable, HC has no equivalent flag either.
--
-- Deliberately minimal: no scores (dropped entirely — not available from
-- either remaining source, and not wanted even when Takeout had them), and
-- no minutes_*/efficiency summary columns — all of that is derivable by
-- summing sleep_stages durations by stage_type at read time, so it isn't
-- stored redundantly here. This table is now just session identity +
-- boundaries + provenance; sleep_stages carries the real detail (when + what
-- per zone).
--
-- No `fingerprint` (dropped everywhere) and no `sleep_id` (Takeout-specific
-- native ID, now unused) — api_uid (HC's uuid or the API's native id) is a
-- real per-source identity, but Health Connect and the live API assign
-- different ids to the same real sleep session, so it can't catch a
-- cross-source duplicate on its own — see uq_sleep_sessions_start below.
CREATE TABLE sleep_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    sleep_type_id BIGINT UNSIGNED NULL,
    main_sleep BOOLEAN NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_sleep_sessions_api_uid (user_id, api_uid),
    -- Cross-source duplicate guard, same reasoning as measurements/exercise
    -- above. Confirmed via real data: 660 of 710 HC sleep sessions match a
    -- live-API session on start_time alone; end_time can drift by up to
    -- ~1 minute between sources (stage-boundary rounding differences), so
    -- only start_time — which matches exactly every time — is safe to key on.
    UNIQUE KEY uq_sleep_sessions_start (user_id, start_time),
    KEY idx_sleep_sessions_start_time (user_id, start_time),
    CONSTRAINT fk_sleep_sessions_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_sleep_sessions_type FOREIGN KEY (sleep_type_id) REFERENCES lut_sleep_type(id),
    CONSTRAINT fk_sleep_sessions_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_sleep_sessions_recording_method FOREIGN KEY (recording_method_id) REFERENCES lut_recording_method(id),
    CONSTRAINT fk_sleep_sessions_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.sleep_sessions_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    sleep_type_id BIGINT UNSIGNED NULL,
    main_sleep BOOLEAN NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    recording_method_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_sleep_sessions_hist_id (id)
) ENGINE=InnoDB;

-- Confirmed via real data (both the live API's embedded sleep.stages[] and
-- Health Connect's sleep_stages_table) that NEITHER remaining source gives a
-- native per-stage ID — api_uid stays nullable here and, realistically,
-- will most often be NULL, making the api_uid unique key below a no-op.
-- A stage's real identity is its (session, type, start) triple — a session
-- can't have two stages of the same type starting at the same instant —
-- so that's enforced as a real DB-level constraint (see
-- uq_sleep_stages_natural below). Found via a re-import of the same real HC
-- export duplicating nothing here only by accident (a related bug meant
-- every stage for an already-known session was silently dropped instead of
-- re-checked); fixed together in import-health-connect.php.
-- data_source_id/recording_method_id deliberately omitted — a stage
-- inherits its parent session's device/recording-method, no need to repeat
-- it per stage row.
CREATE TABLE sleep_stages (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    sleep_session_id BIGINT UNSIGNED NOT NULL,
    stage_type_id BIGINT UNSIGNED NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_sleep_stages_api_uid (user_id, api_uid),
    UNIQUE KEY uq_sleep_stages_natural (user_id, sleep_session_id, stage_type_id, start_time),
    KEY idx_sleep_stages_session (sleep_session_id),
    CONSTRAINT fk_sleep_stages_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_sleep_stages_session FOREIGN KEY (sleep_session_id) REFERENCES sleep_sessions(id),
    CONSTRAINT fk_sleep_stages_type FOREIGN KEY (stage_type_id) REFERENCES lut_sleep_stage_type(id),
    CONSTRAINT fk_sleep_stages_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.sleep_stages_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_end_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NOT NULL,
    sleep_session_id BIGINT UNSIGNED NOT NULL,
    stage_type_id BIGINT UNSIGNED NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_sleep_stages_hist_id (id)
) ENGINE=InnoDB;

-- ============================================================================
-- TRIGGERS — one BEFORE UPDATE + one BEFORE DELETE per table (except _hist
-- tables, which are append-only and never updated/deleted by design).
-- BEFORE UPDATE unconditionally snapshots the pre-update row into <table>_hist
-- and forces id/created_ts immutability. BEFORE DELETE unconditionally
-- errors. No change-detection logic here by design — see the header comment.
-- ============================================================================

DELIMITER $$

CREATE TRIGGER trg_lut_status_bu BEFORE UPDATE ON lut_status FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_status_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_status_bd BEFORE DELETE ON lut_status FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_status; change status instead.';
END$$

CREATE TRIGGER trg_lut_ingestion_source_bu BEFORE UPDATE ON lut_ingestion_source FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_ingestion_source_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_ingestion_source_bd BEFORE DELETE ON lut_ingestion_source FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_ingestion_source; change status instead.';
END$$

CREATE TRIGGER trg_lut_dimension_bu BEFORE UPDATE ON lut_dimension FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_dimension_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_dimension_bd BEFORE DELETE ON lut_dimension FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_dimension; change status instead.';
END$$

CREATE TRIGGER trg_lut_sleep_stage_type_bu BEFORE UPDATE ON lut_sleep_stage_type FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_sleep_stage_type_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_sleep_stage_type_bd BEFORE DELETE ON lut_sleep_stage_type FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_sleep_stage_type; change status instead.';
END$$

CREATE TRIGGER trg_lut_meal_type_bu BEFORE UPDATE ON lut_meal_type FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_meal_type_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_meal_type_bd BEFORE DELETE ON lut_meal_type FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_meal_type; change status instead.';
END$$

CREATE TRIGGER trg_lut_data_source_bu BEFORE UPDATE ON lut_data_source FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_data_source_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_data_source_bd BEFORE DELETE ON lut_data_source FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_data_source; change status instead.';
END$$

CREATE TRIGGER trg_lut_nutrient_bu BEFORE UPDATE ON lut_nutrient FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_nutrient_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_nutrient_bd BEFORE DELETE ON lut_nutrient FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_nutrient; change status instead.';
END$$

CREATE TRIGGER trg_lut_heart_rate_calc_method_bu BEFORE UPDATE ON lut_heart_rate_calc_method FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_heart_rate_calc_method_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_heart_rate_calc_method_bd BEFORE DELETE ON lut_heart_rate_calc_method FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_heart_rate_calc_method; change status instead.';
END$$

CREATE TRIGGER trg_lut_measurement_type_bu BEFORE UPDATE ON lut_measurement_type FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_measurement_type_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_measurement_type_bd BEFORE DELETE ON lut_measurement_type FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_measurement_type; change status instead.';
END$$

CREATE TRIGGER trg_lut_recording_method_bu BEFORE UPDATE ON lut_recording_method FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_recording_method_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_recording_method_bd BEFORE DELETE ON lut_recording_method FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_recording_method; change status instead.';
END$$

CREATE TRIGGER trg_lut_activity_type_bu BEFORE UPDATE ON lut_activity_type FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_activity_type_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_activity_type_bd BEFORE DELETE ON lut_activity_type FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_activity_type; change status instead.';
END$$

CREATE TRIGGER trg_lut_sleep_type_bu BEFORE UPDATE ON lut_sleep_type FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_sleep_type_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_sleep_type_bd BEFORE DELETE ON lut_sleep_type FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_sleep_type; change status instead.';
END$$

CREATE TRIGGER trg_users_bu BEFORE UPDATE ON users FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.users_hist (id, valid_start_ts, valid_end_ts, email, name, status_id, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.email, OLD.name, OLD.status_id, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_users_bd BEFORE DELETE ON users FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on users; change status instead.';
END$$

CREATE TRIGGER trg_groups_bu BEFORE UPDATE ON groups FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.groups_hist (id, valid_start_ts, valid_end_ts, name, status_id, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.status_id, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_groups_bd BEFORE DELETE ON groups FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on groups; change status instead.';
END$$

CREATE TRIGGER trg_link_user_group_bu BEFORE UPDATE ON link_user_group FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.link_user_group_hist (user_id, group_id, valid_start_ts, valid_end_ts, priority, status_id, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.user_id, OLD.group_id, OLD.db_ts, NOW(), OLD.priority, OLD.status_id, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.user_id = OLD.user_id;
    SET NEW.group_id = OLD.group_id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_link_user_group_bd BEFORE DELETE ON link_user_group FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on link_user_group; change status instead.';
END$$

CREATE TRIGGER trg_unit_conversions_bu BEFORE UPDATE ON unit_conversions FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.unit_conversions_hist (id, valid_start_ts, valid_end_ts, name, dimension_id, factor_to_base, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.dimension_id, OLD.factor_to_base, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_unit_conversions_bd BEFORE DELETE ON unit_conversions FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on unit_conversions.';
END$$

CREATE TRIGGER trg_foods_db_bu BEFORE UPDATE ON foods_db FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.foods_db_hist (id, valid_start_ts, valid_end_ts, name, brand_name, dimension_id, version, group_id, user_id, energy_kcal, is_energy_estimated, total_protein_g, total_carbohydrate_g, total_fat_g, notes, is_archived, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.brand_name, OLD.dimension_id, OLD.version, OLD.group_id, OLD.user_id, OLD.energy_kcal, OLD.is_energy_estimated, OLD.total_protein_g, OLD.total_carbohydrate_g, OLD.total_fat_g, OLD.notes, OLD.is_archived, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_foods_db_bd BEFORE DELETE ON foods_db FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on foods_db; use is_archived instead.';
END$$

CREATE TRIGGER trg_foods_db_custom_units_bu BEFORE UPDATE ON foods_db_custom_units FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.foods_db_custom_units_hist (id, valid_start_ts, valid_end_ts, food_id, unit_name, equivalent_amount, is_default, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.food_id, OLD.unit_name, OLD.equivalent_amount, OLD.is_default, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_foods_db_custom_units_bd BEFORE DELETE ON foods_db_custom_units FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on foods_db_custom_units.';
END$$

CREATE TRIGGER trg_lut_serving_unit_bu BEFORE UPDATE ON lut_serving_unit FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_serving_unit_hist (id, valid_start_ts, valid_end_ts, label, unit_conversion_id, foods_db_custom_unit_id, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.label, OLD.unit_conversion_id, OLD.foods_db_custom_unit_id, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_serving_unit_bd BEFORE DELETE ON lut_serving_unit FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_serving_unit.';
END$$

CREATE TRIGGER trg_foods_db_nutrients_bu BEFORE UPDATE ON foods_db_nutrients FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.foods_db_nutrients_hist (id, valid_start_ts, valid_end_ts, food_id, nutrient_id, quantity, unit_id, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.food_id, OLD.nutrient_id, OLD.quantity, OLD.unit_id, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_foods_db_nutrients_bd BEFORE DELETE ON foods_db_nutrients FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on foods_db_nutrients.';
END$$

CREATE TRIGGER trg_foods_db_last_used_bu BEFORE UPDATE ON foods_db_last_used FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.foods_db_last_used_hist (user_id, food_id, valid_start_ts, valid_end_ts, last_used_at, times_used, score, last_serving_amount, last_serving_unit_id, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.user_id, OLD.food_id, OLD.db_ts, NOW(), OLD.last_used_at, OLD.times_used, OLD.score, OLD.last_serving_amount, OLD.last_serving_unit_id, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.user_id = OLD.user_id;
    SET NEW.food_id = OLD.food_id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_foods_db_last_used_bd BEFORE DELETE ON foods_db_last_used FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on foods_db_last_used.';
END$$

CREATE TRIGGER trg_food_log_entries_bu BEFORE UPDATE ON food_log_entries FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.food_log_entries_hist (id, valid_start_ts, valid_end_ts, user_id, start_time, end_time, meal_type_id, food_id, serving_amount, serving_unit_id, data_source_id, ingestion_source_id, api_uid, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.start_time, OLD.end_time, OLD.meal_type_id, OLD.food_id, OLD.serving_amount, OLD.serving_unit_id, OLD.data_source_id, OLD.ingestion_source_id, OLD.api_uid, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_food_log_entries_bd BEFORE DELETE ON food_log_entries FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on food_log_entries.';
END$$


CREATE TRIGGER trg_steps_readings_bu BEFORE UPDATE ON steps_readings FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.steps_readings_hist (id, valid_start_ts, valid_end_ts, user_id, reading_time, steps, data_source_id, recording_method_id, ingestion_source_id, api_uid, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.reading_time, OLD.steps, OLD.data_source_id, OLD.recording_method_id, OLD.ingestion_source_id, OLD.api_uid, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_steps_readings_bd BEFORE DELETE ON steps_readings FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on steps_readings.';
END$$

CREATE TRIGGER trg_heart_rate_readings_bu BEFORE UPDATE ON heart_rate_readings FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.heart_rate_readings_hist (id, valid_start_ts, valid_end_ts, user_id, reading_time, bpm, data_source_id, recording_method_id, ingestion_source_id, api_uid, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.reading_time, OLD.bpm, OLD.data_source_id, OLD.recording_method_id, OLD.ingestion_source_id, OLD.api_uid, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_heart_rate_readings_bd BEFORE DELETE ON heart_rate_readings FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on heart_rate_readings.';
END$$

CREATE TRIGGER trg_heart_rate_variability_readings_bu BEFORE UPDATE ON heart_rate_variability_readings FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.heart_rate_variability_readings_hist (id, valid_start_ts, valid_end_ts, user_id, reading_time, rmssd_ms, data_source_id, recording_method_id, ingestion_source_id, api_uid, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.reading_time, OLD.rmssd_ms, OLD.data_source_id, OLD.recording_method_id, OLD.ingestion_source_id, OLD.api_uid, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_heart_rate_variability_readings_bd BEFORE DELETE ON heart_rate_variability_readings FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on heart_rate_variability_readings.';
END$$

CREATE TRIGGER trg_daily_resting_heart_rate_bu BEFORE UPDATE ON daily_resting_heart_rate FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.daily_resting_heart_rate_hist (id, valid_start_ts, valid_end_ts, user_id, reading_date, bpm, calculation_method_id, data_source_id, recording_method_id, ingestion_source_id, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.reading_date, OLD.bpm, OLD.calculation_method_id, OLD.data_source_id, OLD.recording_method_id, OLD.ingestion_source_id, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_daily_resting_heart_rate_bd BEFORE DELETE ON daily_resting_heart_rate FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on daily_resting_heart_rate.';
END$$

CREATE TRIGGER trg_measurements_bu BEFORE UPDATE ON measurements FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.measurements_hist (id, valid_start_ts, valid_end_ts, user_id, measurement_type_id, reading_time, value, unit_id, data_source_id, recording_method_id, ingestion_source_id, api_uid, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.measurement_type_id, OLD.reading_time, OLD.value, OLD.unit_id, OLD.data_source_id, OLD.recording_method_id, OLD.ingestion_source_id, OLD.api_uid, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_measurements_bd BEFORE DELETE ON measurements FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on measurements.';
END$$

CREATE TRIGGER trg_exercise_sessions_bu BEFORE UPDATE ON exercise_sessions FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.exercise_sessions_hist (id, valid_start_ts, valid_end_ts, user_id, start_time, end_time, activity_name, activity_type_id, duration_ms, active_duration_ms, calories, distance, distance_unit_id, steps, average_heart_rate, has_gps, data_source_id, recording_method_id, ingestion_source_id, api_uid, raw_details, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.start_time, OLD.end_time, OLD.activity_name, OLD.activity_type_id, OLD.duration_ms, OLD.active_duration_ms, OLD.calories, OLD.distance, OLD.distance_unit_id, OLD.steps, OLD.average_heart_rate, OLD.has_gps, OLD.data_source_id, OLD.recording_method_id, OLD.ingestion_source_id, OLD.api_uid, OLD.raw_details, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_exercise_sessions_bd BEFORE DELETE ON exercise_sessions FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on exercise_sessions.';
END$$

CREATE TRIGGER trg_sleep_sessions_bu BEFORE UPDATE ON sleep_sessions FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.sleep_sessions_hist (id, valid_start_ts, valid_end_ts, user_id, sleep_type_id, main_sleep, start_time, end_time, data_source_id, recording_method_id, ingestion_source_id, api_uid, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.sleep_type_id, OLD.main_sleep, OLD.start_time, OLD.end_time, OLD.data_source_id, OLD.recording_method_id, OLD.ingestion_source_id, OLD.api_uid, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_sleep_sessions_bd BEFORE DELETE ON sleep_sessions FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on sleep_sessions.';
END$$

CREATE TRIGGER trg_sleep_stages_bu BEFORE UPDATE ON sleep_stages FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.sleep_stages_hist (id, valid_start_ts, valid_end_ts, user_id, sleep_session_id, stage_type_id, start_time, end_time, ingestion_source_id, api_uid, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.sleep_session_id, OLD.stage_type_id, OLD.start_time, OLD.end_time, OLD.ingestion_source_id, OLD.api_uid, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_sleep_stages_bd BEFORE DELETE ON sleep_stages FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on sleep_stages.';
END$$

DELIMITER ;
