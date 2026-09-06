-- NutriPal database schema (V1 checkpoint)
--
-- CHECKPOINT, NOT FINAL. steps_readings, heart_rate_readings, weight_readings,
-- exercise_sessions, sleep_sessions/sleep_stages, and parts of the foods_db
-- family still need their own detailed review pass and will likely change.
-- food_log_entries, food_log_nutrients, and everything under "General
-- patterns" / "Multi-user" / "foods_db family" below are in their reviewed,
-- final-for-now form.
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
-- Dedup across the two ingestion sources (live API vs. Takeout bulk import)
-- uses a `fingerprint` CHAR(64) sha256 hash of each row's core identifying
-- fields, computed identically regardless of source, plus (where available)
-- a native ID from whichever source provides one. See
-- doc/wiki/Database-Schema.md for the exact fingerprint composition per
-- table and the identity-resolution priority (native ID before fingerprint).
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_ingestion_source_hist_id (id)
) ENGINE=InnoDB;

CREATE TABLE lut_nutrient_value_type (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL DEFAULT FALSE,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_lut_nutrient_value_type_name (name)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.lut_nutrient_value_type_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_nutrient_value_type_hist_id (id)
) ENGINE=InnoDB;

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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    is_obsolete BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_nutrient_hist_id (id)
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    email VARCHAR(255) NULL,
    name VARCHAR(255) NULL,
    status_id BIGINT UNSIGNED NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    name VARCHAR(255) NULL,
    status_id BIGINT UNSIGNED NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    priority INT UNSIGNED NOT NULL,
    status_id BIGINT UNSIGNED NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    factor_to_base DECIMAL(18,6) NOT NULL COMMENT 'grams for mass, milliliters for volume',
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    name VARCHAR(64) NOT NULL,
    dimension_id BIGINT UNSIGNED NOT NULL,
    factor_to_base DECIMAL(18,6) NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
-- report slightly different nutrition for "the same" food over time.
-- food_log_entries already snapshots resolved nutrition at logging time, so
-- versioning here never retroactively changes historical logs.
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
    has_nutrient_overrides BOOLEAN NOT NULL DEFAULT FALSE,
    fingerprint CHAR(64) NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_foods_db_fingerprint (user_id, group_id, fingerprint),
    KEY idx_foods_db_name (name, brand_name),
    CONSTRAINT fk_foods_db_dimension FOREIGN KEY (dimension_id) REFERENCES lut_dimension(id),
    CONSTRAINT fk_foods_db_group FOREIGN KEY (group_id) REFERENCES groups(id),
    CONSTRAINT fk_foods_db_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.foods_db_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
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
    has_nutrient_overrides BOOLEAN NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    food_id BIGINT UNSIGNED NOT NULL,
    unit_name VARCHAR(64) NOT NULL,
    equivalent_amount DECIMAL(10,4) NOT NULL,
    is_default BOOLEAN NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    label VARCHAR(64) NOT NULL,
    unit_conversion_id BIGINT UNSIGNED NULL,
    foods_db_custom_unit_id BIGINT UNSIGNED NULL,
    created_ts TIMESTAMP NOT NULL,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_lut_serving_unit_hist_id (id)
) ENGINE=InnoDB;

-- Full micronutrient tracking for catalog foods, same SRC/FIX/MOD model as
-- food_log_nutrients (see there for the effective-value formula). Sets up a
-- future enrichment workflow: catalog nutrients Google doesn't track can
-- supplement a matched Google-sourced log entry (matching logic deferred).
CREATE TABLE foods_db_nutrients (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    food_id BIGINT UNSIGNED NOT NULL,
    nutrient_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(10,4) NOT NULL,
    unit_id BIGINT UNSIGNED NOT NULL,
    value_type_id BIGINT UNSIGNED NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_foods_db_nutrients (food_id, nutrient_id, value_type_id),
    CONSTRAINT fk_foods_db_nutrients_food FOREIGN KEY (food_id) REFERENCES foods_db(id),
    CONSTRAINT fk_foods_db_nutrients_nutrient FOREIGN KEY (nutrient_id) REFERENCES lut_nutrient(id),
    CONSTRAINT fk_foods_db_nutrients_unit FOREIGN KEY (unit_id) REFERENCES unit_conversions(id),
    CONSTRAINT fk_foods_db_nutrients_value_type FOREIGN KEY (value_type_id) REFERENCES lut_nutrient_value_type(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.foods_db_nutrients_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    food_id BIGINT UNSIGNED NOT NULL,
    nutrient_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(10,4) NOT NULL,
    unit_id BIGINT UNSIGNED NOT NULL,
    value_type_id BIGINT UNSIGNED NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    last_used_at DATETIME NOT NULL,
    times_used INT UNSIGNED NOT NULL,
    score DECIMAL(10,4) NOT NULL,
    last_serving_amount DECIMAL(8,2) NULL,
    last_serving_unit_id BIGINT UNSIGNED NULL,
    created_ts TIMESTAMP NOT NULL,
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
-- food_id (nullable): which foods_db row (a specific version) this entry was
-- logged from, if any. Most Google-synced entries won't have one unless/until
-- a future matching/enrichment pass links them. Nutrition here is always a
-- snapshot resolved at logging time (via serving_amount/serving_unit_id
-- against foods_db's per-100 values) — food_id is for traceability/"log
-- again," never live-joined for display, so re-versioning a catalog food
-- never retroactively changes past logs. App-level invariant (not
-- DB-enforced): if serving_unit_id resolves to a foods_db_custom_units row,
-- that row's own food_id must match this food_id.
CREATE TABLE food_log_entries (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    brand_name VARCHAR(255) NULL,
    food_name VARCHAR(255) NOT NULL,
    meal_type_id BIGINT UNSIGNED NOT NULL,
    energy_kcal DECIMAL(8,2) NULL,
    is_energy_estimated BOOLEAN NOT NULL DEFAULT FALSE,
    total_protein_g DECIMAL(8,2) NULL,
    total_carbohydrate_g DECIMAL(8,2) NULL,
    total_fat_g DECIMAL(8,2) NULL,
    serving_amount DECIMAL(8,2) NULL,
    serving_unit_id BIGINT UNSIGNED NULL,
    food_id BIGINT UNSIGNED NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    has_nutrient_overrides BOOLEAN NOT NULL DEFAULT FALSE,
    fingerprint CHAR(64) NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_food_log_entries_fingerprint (user_id, fingerprint),
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
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    brand_name VARCHAR(255) NULL,
    food_name VARCHAR(255) NOT NULL,
    meal_type_id BIGINT UNSIGNED NOT NULL,
    energy_kcal DECIMAL(8,2) NULL,
    is_energy_estimated BOOLEAN NOT NULL,
    total_protein_g DECIMAL(8,2) NULL,
    total_carbohydrate_g DECIMAL(8,2) NULL,
    total_fat_g DECIMAL(8,2) NULL,
    serving_amount DECIMAL(8,2) NULL,
    serving_unit_id BIGINT UNSIGNED NULL,
    food_id BIGINT UNSIGNED NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    has_nutrient_overrides BOOLEAN NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    created_ts TIMESTAMP NOT NULL,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_food_log_entries_hist_id (id)
) ENGINE=InnoDB;

-- One row per nutrient PER VALUE TYPE per entry (up to 3: SRC/FIX/MOD).
-- Effective value (computed at read time, never stored/overwritten):
--   IF a FIX row exists: effective = FIX
--   ELSE: effective = GREATEST(0, COALESCE(SRC,0) + COALESCE(MOD,0))
-- (clamped at zero — a negative MOD could otherwise push a quantity below
-- zero, which is physically meaningless; FIX itself is validated
-- non-negative at entry time). SRC is always preserved untouched — a
-- correction never overwrites the original imported value.
-- nutrient_id: dropped at ingest if not in lut_nutrient (see there).
CREATE TABLE food_log_nutrients (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    food_log_entry_id BIGINT UNSIGNED NOT NULL,
    nutrient_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(10,4) NOT NULL,
    unit_id BIGINT UNSIGNED NOT NULL,
    value_type_id BIGINT UNSIGNED NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_food_log_nutrients (food_log_entry_id, nutrient_id, value_type_id),
    CONSTRAINT fk_food_log_nutrients_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_food_log_nutrients_entry FOREIGN KEY (food_log_entry_id) REFERENCES food_log_entries(id),
    CONSTRAINT fk_food_log_nutrients_nutrient FOREIGN KEY (nutrient_id) REFERENCES lut_nutrient(id),
    CONSTRAINT fk_food_log_nutrients_unit FOREIGN KEY (unit_id) REFERENCES unit_conversions(id),
    CONSTRAINT fk_food_log_nutrients_value_type FOREIGN KEY (value_type_id) REFERENCES lut_nutrient_value_type(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.food_log_nutrients_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    food_log_entry_id BIGINT UNSIGNED NOT NULL,
    nutrient_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(10,4) NOT NULL,
    unit_id BIGINT UNSIGNED NOT NULL,
    value_type_id BIGINT UNSIGNED NOT NULL,
    created_ts TIMESTAMP NOT NULL,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_food_log_nutrients_hist_id (id)
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
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    fingerprint CHAR(64) NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_steps_readings_fingerprint (user_id, fingerprint),
    UNIQUE KEY uq_steps_readings_api_uid (user_id, api_uid),
    KEY idx_steps_readings_time (user_id, reading_time),
    CONSTRAINT fk_steps_readings_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_steps_readings_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_steps_readings_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.steps_readings_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    steps INT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    fingerprint CHAR(64) NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    fingerprint CHAR(64) NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_heart_rate_readings_fingerprint (user_id, fingerprint),
    UNIQUE KEY uq_heart_rate_readings_api_uid (user_id, api_uid),
    KEY idx_heart_rate_readings_time (user_id, reading_time),
    CONSTRAINT fk_heart_rate_readings_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_heart_rate_readings_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_heart_rate_readings_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.heart_rate_readings_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    bpm SMALLINT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    fingerprint CHAR(64) NOT NULL,
    created_ts TIMESTAMP NOT NULL,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_heart_rate_readings_hist_id (id)
) ENGINE=InnoDB;

CREATE TABLE weight_readings (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    weight_grams INT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    fingerprint CHAR(64) NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_weight_readings_fingerprint (user_id, fingerprint),
    UNIQUE KEY uq_weight_readings_api_uid (user_id, api_uid),
    KEY idx_weight_readings_time (user_id, reading_time),
    CONSTRAINT fk_weight_readings_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_weight_readings_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_weight_readings_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.weight_readings_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    reading_time DATETIME NOT NULL,
    weight_grams INT UNSIGNED NOT NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    fingerprint CHAR(64) NOT NULL,
    created_ts TIMESTAMP NOT NULL,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_weight_readings_hist_id (id)
) ENGINE=InnoDB;

CREATE TABLE exercise_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    log_id VARCHAR(64) NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NULL,
    activity_name VARCHAR(128) NULL,
    activity_type_id BIGINT UNSIGNED NULL,
    duration_ms INT UNSIGNED NULL,
    active_duration_ms INT UNSIGNED NULL,
    calories INT UNSIGNED NULL,
    distance DECIMAL(10,4) NULL,
    distance_unit VARCHAR(16) NULL,
    steps INT UNSIGNED NULL,
    average_heart_rate SMALLINT UNSIGNED NULL,
    device_name VARCHAR(128) NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    fingerprint CHAR(64) NOT NULL,
    raw_details JSON NULL COMMENT 'Heart-rate zones, active-zone-minutes breakdown, GPS, etc. — preserved but not individually columned in V1',
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_exercise_sessions_fingerprint (user_id, fingerprint),
    UNIQUE KEY uq_exercise_sessions_api_uid (user_id, api_uid),
    UNIQUE KEY uq_exercise_sessions_log_id (user_id, log_id),
    KEY idx_exercise_sessions_start_time (user_id, start_time),
    CONSTRAINT fk_exercise_sessions_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_exercise_sessions_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_exercise_sessions_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.exercise_sessions_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    log_id VARCHAR(64) NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NULL,
    activity_name VARCHAR(128) NULL,
    activity_type_id BIGINT UNSIGNED NULL,
    duration_ms INT UNSIGNED NULL,
    active_duration_ms INT UNSIGNED NULL,
    calories INT UNSIGNED NULL,
    distance DECIMAL(10,4) NULL,
    distance_unit VARCHAR(16) NULL,
    steps INT UNSIGNED NULL,
    average_heart_rate SMALLINT UNSIGNED NULL,
    device_name VARCHAR(128) NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    fingerprint CHAR(64) NOT NULL,
    raw_details JSON NULL,
    created_ts TIMESTAMP NOT NULL,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_exercise_sessions_hist_id (id)
) ENGINE=InnoDB;

CREATE TABLE sleep_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    sleep_id VARCHAR(64) NULL,
    sleep_type VARCHAR(32) NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    minutes_in_sleep_period INT UNSIGNED NULL,
    minutes_asleep INT UNSIGNED NULL,
    minutes_awake INT UNSIGNED NULL,
    minutes_to_fall_asleep INT UNSIGNED NULL,
    minutes_after_wake_up INT UNSIGNED NULL,
    overall_score TINYINT UNSIGNED NULL,
    duration_score TINYINT UNSIGNED NULL,
    composition_score TINYINT UNSIGNED NULL,
    revitalization_score TINYINT UNSIGNED NULL,
    resting_heart_rate SMALLINT UNSIGNED NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    fingerprint CHAR(64) NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_sleep_sessions_fingerprint (user_id, fingerprint),
    UNIQUE KEY uq_sleep_sessions_api_uid (user_id, api_uid),
    UNIQUE KEY uq_sleep_sessions_sleep_id (user_id, sleep_id),
    KEY idx_sleep_sessions_start_time (user_id, start_time),
    CONSTRAINT fk_sleep_sessions_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_sleep_sessions_data_source FOREIGN KEY (data_source_id) REFERENCES lut_data_source(id),
    CONSTRAINT fk_sleep_sessions_ingestion_source FOREIGN KEY (ingestion_source_id) REFERENCES lut_ingestion_source(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.sleep_sessions_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    sleep_id VARCHAR(64) NULL,
    sleep_type VARCHAR(32) NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    minutes_in_sleep_period INT UNSIGNED NULL,
    minutes_asleep INT UNSIGNED NULL,
    minutes_awake INT UNSIGNED NULL,
    minutes_to_fall_asleep INT UNSIGNED NULL,
    minutes_after_wake_up INT UNSIGNED NULL,
    overall_score TINYINT UNSIGNED NULL,
    duration_score TINYINT UNSIGNED NULL,
    composition_score TINYINT UNSIGNED NULL,
    revitalization_score TINYINT UNSIGNED NULL,
    resting_heart_rate SMALLINT UNSIGNED NULL,
    data_source_id BIGINT UNSIGNED NULL,
    ingestion_source_id BIGINT UNSIGNED NOT NULL,
    api_uid VARCHAR(255) NULL,
    fingerprint CHAR(64) NOT NULL,
    created_ts TIMESTAMP NOT NULL,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    KEY idx_sleep_sessions_hist_id (id)
) ENGINE=InnoDB;

CREATE TABLE sleep_stages (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    sleep_session_id BIGINT UNSIGNED NOT NULL,
    sleep_stage_id VARCHAR(64) NULL,
    stage_type_id BIGINT UNSIGNED NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    db_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NULL,
    changed_by_user_id BIGINT UNSIGNED NULL,
    UNIQUE KEY uq_sleep_stages_sleep_stage_id (user_id, sleep_stage_id),
    KEY idx_sleep_stages_session (sleep_session_id),
    CONSTRAINT fk_sleep_stages_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_sleep_stages_session FOREIGN KEY (sleep_session_id) REFERENCES sleep_sessions(id),
    CONSTRAINT fk_sleep_stages_type FOREIGN KEY (stage_type_id) REFERENCES lut_sleep_stage_type(id)
) ENGINE=InnoDB;

CREATE TABLE nutripal_hist.sleep_stages_hist (
    id_hist BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    db_hist_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id BIGINT UNSIGNED NOT NULL,
    valid_start_ts TIMESTAMP NOT NULL,
    valid_end_ts TIMESTAMP NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    sleep_session_id BIGINT UNSIGNED NOT NULL,
    sleep_stage_id VARCHAR(64) NULL,
    stage_type_id BIGINT UNSIGNED NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    created_ts TIMESTAMP NOT NULL,
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

CREATE TRIGGER trg_lut_nutrient_value_type_bu BEFORE UPDATE ON lut_nutrient_value_type FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.lut_nutrient_value_type_hist (id, valid_start_ts, valid_end_ts, name, description, is_obsolete, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.description, OLD.is_obsolete, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_lut_nutrient_value_type_bd BEFORE DELETE ON lut_nutrient_value_type FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on lut_nutrient_value_type; change status instead.';
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
    INSERT INTO nutripal_hist.foods_db_hist (id, valid_start_ts, valid_end_ts, name, brand_name, dimension_id, version, group_id, user_id, energy_kcal, is_energy_estimated, total_protein_g, total_carbohydrate_g, total_fat_g, notes, is_archived, has_nutrient_overrides, fingerprint, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.name, OLD.brand_name, OLD.dimension_id, OLD.version, OLD.group_id, OLD.user_id, OLD.energy_kcal, OLD.is_energy_estimated, OLD.total_protein_g, OLD.total_carbohydrate_g, OLD.total_fat_g, OLD.notes, OLD.is_archived, OLD.has_nutrient_overrides, OLD.fingerprint, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
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
    INSERT INTO nutripal_hist.foods_db_nutrients_hist (id, valid_start_ts, valid_end_ts, food_id, nutrient_id, quantity, unit_id, value_type_id, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.food_id, OLD.nutrient_id, OLD.quantity, OLD.unit_id, OLD.value_type_id, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
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
    INSERT INTO nutripal_hist.food_log_entries_hist (id, valid_start_ts, valid_end_ts, user_id, start_time, end_time, brand_name, food_name, meal_type_id, energy_kcal, is_energy_estimated, total_protein_g, total_carbohydrate_g, total_fat_g, serving_amount, serving_unit_id, food_id, data_source_id, ingestion_source_id, api_uid, has_nutrient_overrides, fingerprint, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.start_time, OLD.end_time, OLD.brand_name, OLD.food_name, OLD.meal_type_id, OLD.energy_kcal, OLD.is_energy_estimated, OLD.total_protein_g, OLD.total_carbohydrate_g, OLD.total_fat_g, OLD.serving_amount, OLD.serving_unit_id, OLD.food_id, OLD.data_source_id, OLD.ingestion_source_id, OLD.api_uid, OLD.has_nutrient_overrides, OLD.fingerprint, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_food_log_entries_bd BEFORE DELETE ON food_log_entries FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on food_log_entries.';
END$$

CREATE TRIGGER trg_food_log_nutrients_bu BEFORE UPDATE ON food_log_nutrients FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.food_log_nutrients_hist (id, valid_start_ts, valid_end_ts, user_id, food_log_entry_id, nutrient_id, quantity, unit_id, value_type_id, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.food_log_entry_id, OLD.nutrient_id, OLD.quantity, OLD.unit_id, OLD.value_type_id, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_food_log_nutrients_bd BEFORE DELETE ON food_log_nutrients FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on food_log_nutrients.';
END$$

CREATE TRIGGER trg_steps_readings_bu BEFORE UPDATE ON steps_readings FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.steps_readings_hist (id, valid_start_ts, valid_end_ts, user_id, reading_time, steps, data_source_id, ingestion_source_id, api_uid, fingerprint, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.reading_time, OLD.steps, OLD.data_source_id, OLD.ingestion_source_id, OLD.api_uid, OLD.fingerprint, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_steps_readings_bd BEFORE DELETE ON steps_readings FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on steps_readings.';
END$$

CREATE TRIGGER trg_heart_rate_readings_bu BEFORE UPDATE ON heart_rate_readings FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.heart_rate_readings_hist (id, valid_start_ts, valid_end_ts, user_id, reading_time, bpm, data_source_id, ingestion_source_id, api_uid, fingerprint, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.reading_time, OLD.bpm, OLD.data_source_id, OLD.ingestion_source_id, OLD.api_uid, OLD.fingerprint, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_heart_rate_readings_bd BEFORE DELETE ON heart_rate_readings FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on heart_rate_readings.';
END$$

CREATE TRIGGER trg_weight_readings_bu BEFORE UPDATE ON weight_readings FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.weight_readings_hist (id, valid_start_ts, valid_end_ts, user_id, reading_time, weight_grams, data_source_id, ingestion_source_id, api_uid, fingerprint, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.reading_time, OLD.weight_grams, OLD.data_source_id, OLD.ingestion_source_id, OLD.api_uid, OLD.fingerprint, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_weight_readings_bd BEFORE DELETE ON weight_readings FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on weight_readings.';
END$$

CREATE TRIGGER trg_exercise_sessions_bu BEFORE UPDATE ON exercise_sessions FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.exercise_sessions_hist (id, valid_start_ts, valid_end_ts, user_id, log_id, start_time, end_time, activity_name, activity_type_id, duration_ms, active_duration_ms, calories, distance, distance_unit, steps, average_heart_rate, device_name, data_source_id, ingestion_source_id, api_uid, fingerprint, raw_details, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.log_id, OLD.start_time, OLD.end_time, OLD.activity_name, OLD.activity_type_id, OLD.duration_ms, OLD.active_duration_ms, OLD.calories, OLD.distance, OLD.distance_unit, OLD.steps, OLD.average_heart_rate, OLD.device_name, OLD.data_source_id, OLD.ingestion_source_id, OLD.api_uid, OLD.fingerprint, OLD.raw_details, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_exercise_sessions_bd BEFORE DELETE ON exercise_sessions FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on exercise_sessions.';
END$$

CREATE TRIGGER trg_sleep_sessions_bu BEFORE UPDATE ON sleep_sessions FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.sleep_sessions_hist (id, valid_start_ts, valid_end_ts, user_id, sleep_id, sleep_type, start_time, end_time, minutes_in_sleep_period, minutes_asleep, minutes_awake, minutes_to_fall_asleep, minutes_after_wake_up, overall_score, duration_score, composition_score, revitalization_score, resting_heart_rate, data_source_id, ingestion_source_id, api_uid, fingerprint, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.sleep_id, OLD.sleep_type, OLD.start_time, OLD.end_time, OLD.minutes_in_sleep_period, OLD.minutes_asleep, OLD.minutes_awake, OLD.minutes_to_fall_asleep, OLD.minutes_after_wake_up, OLD.overall_score, OLD.duration_score, OLD.composition_score, OLD.revitalization_score, OLD.resting_heart_rate, OLD.data_source_id, OLD.ingestion_source_id, OLD.api_uid, OLD.fingerprint, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_sleep_sessions_bd BEFORE DELETE ON sleep_sessions FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on sleep_sessions.';
END$$

CREATE TRIGGER trg_sleep_stages_bu BEFORE UPDATE ON sleep_stages FOR EACH ROW BEGIN
    INSERT INTO nutripal_hist.sleep_stages_hist (id, valid_start_ts, valid_end_ts, user_id, sleep_session_id, sleep_stage_id, stage_type_id, start_time, end_time, created_ts, changed_by, changed_by_user_id)
    VALUES (OLD.id, OLD.db_ts, NOW(), OLD.user_id, OLD.sleep_session_id, OLD.sleep_stage_id, OLD.stage_type_id, OLD.start_time, OLD.end_time, OLD.created_ts, OLD.changed_by, OLD.changed_by_user_id);
    SET NEW.id = OLD.id;
    SET NEW.created_ts = OLD.created_ts;
    SET NEW.db_ts = NOW();
END$$
CREATE TRIGGER trg_sleep_stages_bd BEFORE DELETE ON sleep_stages FOR EACH ROW BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Delete is not allowed on sleep_stages.';
END$$

DELIMITER ;
