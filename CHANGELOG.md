# Changelog

## V0.0.15 — 2026-09-08 12:00
### Changes
- Added `scripts/fetch-recent-compare.php`, an exploratory script that pulls the last N days of every relevant data type from the live Google Health API and writes each to its own temp JSON file (not the database), to cross-check against what's already in the DB from the Health Connect bulk import.
- **Cross-source comparison, 10-day window**: nutrition, HRV, exercise, and sleep counts matched the DB exactly per day once both sides were bucketed by the same local calendar day (the API returns local civil dates; comparing against the DB's raw UTC dates made a day look "missing" that wasn't — a bucketing artifact, not a data gap). Steps/heart-rate matched almost exactly, with the handful of day-level discrepancies consistent with the already-documented multi-device step overlap. Found one genuine (not artifact) discrepancy: a Health-Connect-sourced weight reading on one date with no corresponding entry in the live API's history for the same date.
- **Major finding**: the live API's `nutrition-log` data does not have the "quantity problem" that drove this session's Health Connect fix — every entry checked included a real `serving` field (amount + human unit, e.g. "2 oz") and a link to a canonical `food` resource carrying true gram-conversion multipliers per unit. Health Connect has neither. Recorded as a project memory (`google_health_api_food_data_quality`) since it changes the best fix path for the placeholder "reported serving" units once the live-API sync is built — likely no manual correction or external reference database needed for foods the API has already seen.

## V0.0.14 — 2026-09-08 10:00
### Changes
- Created the real `nutripal`/`nutripal_hist` databases for the first time and added `sql/init_lookups.sql`, a canonical reference-data initialization script (sentinels, units, and every small-closed-vocabulary lookup) distinct from the illustrative `sql/sample_data.sql`. Added `src/Database.php` (minimal PDO connection helper) and `DB_HOST`/`DB_NAME`/`DB_USER`/`DB_PASS` to `.env`/`.env.example`.
- Built `scripts/import-takeout.php` and ran it end-to-end against a real ~3-year Takeout export as a full-scale schema test (~12.1 million rows, 11.5M heart-rate readings). Found and fixed three real gaps the design review missed: `lut_meal_type` missing `BEFORE_BREAKFAST`/`BEFORE_LUNCH`/`AFTER_DINNER`; `lut_sleep_stage_type` missing the older `CLASSIC`-mode vocabulary (`ASLEEP`/`RESTLESS`/`UNSPECIFIED`, 264 of 58,010 rows, backfilled via `scripts/import-takeout-supplement-sleep-stages.php`); nutrition data's literal `N/A` sentinel string (~21% of values) was silently casting to `0.0` instead of being treated as unreported.
- **Inspected a real Android Health Connect SQLite export and, based on real category-by-category tradeoffs, decided to drop Google Takeout as an active ingestion source entirely** (nutrition, sleep, steps, heart rate, weight/height, exercise) in favor of Health Connect (bulk history) + the live Google Health API (incremental sync) going forward. Takeout's importer/schema-support code is kept as a historical artifact, not deleted; `lut_ingestion_source`'s `google_takeout` row is kept for traceability of already-imported rows but documented as deprecated.
- **Major `food_log_entries`/`foods_db` redesign** to a strict reference model: a log entry now always points at exactly one `foods_db` row plus a `serving_amount` multiplier, rather than duplicating nutrition data inline. Dropped the `SRC`/`FIX`/`MOD` nutrient-modifier system (and `lut_nutrient_value_type`) entirely — a genuine change to a food's nutrition now creates a new `foods_db` version instead of a competing override row. Moved `ingestion_source_id`/`data_source_id`/`api_uid` onto the log (provenance of an event), out of the catalog (a property of a food). Dropped `fingerprint` everywhere in favor of `api_uid` as the sole identity key, with a disclosed gap: `steps_readings`/`heart_rate_readings`/`heart_rate_variability_readings`/`sleep_stages` now have no DB-level duplicate guard at all, deferred to application logic.
- Rewrote `sql/schema.sql` end to end reflecting the above (dropped `food_log_nutrients` entirely — nutrition is now always derived by joining through `food_id`; drastically simplified `sleep_sessions`, removing every score/duration column Health Connect has no concept of). Verified via a full throwaway-database test (structural audits across all 30 tables/hist tables/60 triggers, plus live insert/update/delete/trigger checks) before touching real data.
- Built `scripts/import-health-connect.php`, a new importer for HC's 78-table SQLite export covering nutrition, weight, height, steps, heart rate (parent + series), HRV, sleep (sessions + stages), and exercise. Found and fixed two real bugs by actually running the import and inspecting results rather than trusting a clean-looking log: `PDOStatement::fetch()` returning `false` (not `null`) on no match was silently producing wrong version numbers for brand-new foods; and all four `catch` blocks checking the whole SQLSTATE `23000` class (rather than MySQL's specific error code 1062) were mislabeling a real foreign-key failure — a missing `lut_serving_unit` seed row for `'gram'` — as "2,376 duplicates," silently zeroing out `food_log_entries` with no visible error.
- **Found and fixed the "quantity problem"**: Health Connect's `nutrition_record_table` reports absolute totals with no serving/mass field at all, so the original tolerance-based `foods_db` version-matching couldn't distinguish "same food at a different amount" from "a genuinely different food" — confirmed concretely when "Yellow Onion" produced 41 near-duplicate versions that were actually clean multiples of one another (the same onion at ~41 unknown quantities). Fixed with ratio-based matching (checks every existing version sharing a food's name for a single scale factor that consistently explains the incoming energy/protein/carb/fat readings) plus a per-food placeholder custom unit ("reported serving", `equivalent_amount = 100`) so a future real-world correction only ever touches one row, never historical log entries.
- Wiped and recreated the real `nutripal`/`nutripal_hist` databases fresh and re-ran the full Health Connect import as the official test of the redesigned schema: 220,237 steps, 2,854,655 heart-rate readings, 22,036 HRV readings, 710 sleep sessions / 33,121 stages, 2,015 exercise sessions, 520 weight / 1 height reading, and 2,376 nutrition log entries resolving to 583 catalog foods (531 distinct names) — zero errors. Verified the quantity fix directly: max versions for any one food name dropped from 41 to 4, zero log entries landed with an extreme serving ratio.
- Added `/storage/import-logs/` and `/ref/` to `.gitignore` — both can contain real personal health data and must never be committed.

### Known bugs (not yet fixed)
- `sql/sample_data.sql` is now stale/incompatible with the redesigned schema (still reflects the old `food_name`/`brand_name`/`food_log_nutrients`/`SRC`-`FIX`-`MOD` shape) — not rewritten this pass.
- `lut_activity_type` isn't a true canonical mapping yet — both importers do a plain find-or-create keyed on each source's raw activity code, so the same real-world activity can produce multiple rows across sources.
- `daily_resting_heart_rate`'s multiple-readings-per-day question (whether Health Connect can report more than one per day, and how to dedup if so) was left unresolved — no `api_uid` added, structurally unchanged from V0.0.13.
- Health Connect's `exercise_session_record_table` has no calories/distance/steps/average-heart-rate columns (stored in separate generic time-series tables with no FK back to the session) — not cross-referenced; those four columns are left `NULL` for HC-sourced exercise sessions. GPS route points are not imported, only a `has_gps` flag.

### Planned (not yet implemented)
- UI to correct the placeholder "reported serving" custom units created by the quantity-problem fix: edit a food's unit directly, search for a specific food to adjust, and a post-sync/import review list of every food still on the placeholder unit (e.g. eggs → 1 egg, cottage cheese → 1 cup/4oz, chicken → ounces) — must keep historical log totals unchanged when a unit is corrected.
- Real canonical mapping for `lut_activity_type` across both Health Connect's and the live API's activity vocabularies.
- Matching catalog foods against a real reference nutrition database (e.g. USDA FoodData Central) for true gram-accurate quantities, rather than the placeholder unit.
- Rewrite or retire `sql/sample_data.sql` to match the redesigned schema.
- Resolve the `daily_resting_heart_rate` multiple-readings-per-day open question.
- Build the "recipe" template feature (a separate, not-yet-designed concept — food log entries stay ingredient-level and never reference a recipe directly).
- Build the live-API-to-database sync (currently only bulk importers write to the database).
- React frontend.

## V0.0.13 — 2026-09-07 22:00
### Changes
- Completed the table-by-table schema review for every remaining health-data table (`steps_readings`, `heart_rate_readings`, `measurements` [weight/height/etc.], `exercise_sessions`, `sleep_sessions`/`sleep_stages`), grounded in real API responses and a direct inspection of the real Takeout export zip rather than assumptions — every change below was driven by an actual data-shape finding, verified against a live throwaway MariaDB database after each table.
- **New tables discovered via real data, not originally modeled**: `heart_rate_variability_readings` and `daily_resting_heart_rate` (distinct metrics from continuous bpm, confirmed via the live API); `lut_recording_method` (a genuinely new cross-cutting concept — *how* a reading was captured, e.g. `ACTIVELY_MEASURED`/`MANUAL`/`DERIVED` — present on every metric checked, added to steps/heart-rate/HRV/resting-HR/measurements/exercise/sleep); `lut_activity_type` (resolving Takeout's numeric Fitbit activity codes and the API's string `exerciseType` into one canonical vocabulary); `lut_sleep_type` (`CLASSIC`/`STAGES`).
- **`weight_readings` and `height_readings` (height also newly added) merged into a single generic `measurements` table** (`measurement_type_id`/`value`/`unit_id`, per the "generic characteristic/value/unit table" pattern also documented in `doc/wiki/Database-Design-Patterns.md`) — extensible to future body metrics like blood pressure or body fat % without new tables. `unit_conversions`/`lut_dimension` extended with length/pressure/ratio dimensions to support it.
- **Real bugs caught and fixed**: sleep score columns (`overall_score` etc.) were `TINYINT UNSIGNED` but real Takeout values are floats and use `-1` as a "not computed" sentinel — neither fits an unsigned integer; changed to `DECIMAL(6,2)` with `-1` translated to `NULL` at ingest. `sleep_stages` had no `fingerprint`/`ingestion_source_id` at all — confirmed via real data that the live API returns stage-level detail with no native ID, meaning API-sourced stages had no dedup mechanism whatsoever; fixed.
- **Removed a redundant column**: `exercise_sessions.device_name` duplicated `data_source_id` (confirmed both sources report exactly one "which device" concept).
- **Fixed free-text units**: `exercise_sessions.distance_unit` → `distance_unit_id` (`unit_conversions`-backed) — confirmed Takeout genuinely varies distance units (miles observed) while the API always reports fixed millimeters.
- Added `food_log_entries.food_id` (nullable FK → `foods_db`) and `foods_db_last_used.last_serving_amount`/`last_serving_unit_id`, closing the previously-open `food_log_entries` ↔ `foods_db` linkage gap.
- Split the schema into two databases (`nutripal` + `nutripal_hist`) so audit history can be backed up/archived independently of live data; documented the Bluehost account-prefix deploy caveat.
- Corrected stale documentation: Takeout's `UserSleeps`/`UserSleepStages`/`UserSleepScores` files are actually split into several multi-year-range CSVs, not single all-history files as previously documented; discovered a second, richer legacy Fitbit-format sleep export (`Global Export Data/sleep-*.json`) and several unreviewed sleep-adjacent files (sleep profile, a second sleep-score source, sleep temperature, respiratory rate).
- Every change re-verified end-to-end against a throwaway MariaDB database (insert/update/delete-block/FK enforcement), never touching the real `nutripal` database.

### Known bugs (not yet fixed)
- Multi-device step overlap can double-count daily step totals if summed naively — deliberately deferred to application/aggregation logic (see `doc/wiki/Database-Schema.md` Open Items), not a schema gap.

### Planned (not yet implemented)
- Mapping raw activity-type codes (Fitbit numeric IDs, API string enum) into canonical `lut_activity_type` rows — real reference-data work, deferred to ingest-time implementation
- Deciding which raw Takeout sleep format the importer will parse, and reviewing the newly-discovered sleep-adjacent Takeout files
- Create the actual MySQL database and run `sql/schema.sql` (needs confirmation before touching the local database, per project convention)
- Build `scripts/import-takeout.php` to parse an extracted Takeout export and load it into the schema
- Build the live-API-to-database sync (currently the fetch scripts only write debug JSON, not the DB)
- Meal planning — logging an intended future meal, distinct from a consumed entry
- React frontend

## V0.0.12 — 2026-09-06 16:00
### Changes
- Verified `sql/schema.sql` + `sql/sample_data.sql` by actually running them: loaded into throwaway databases (`nutripal_verify`/`nutripal_verify_hist`, never touching real `nutripal`), confirmed table/trigger counts, exercised the cross-schema history trigger (update + inspect the resulting hist row), the delete-block trigger, and FK enforcement — then dropped both throwaway databases.
- **Bug found and fixed**: every `_hist` table's `valid_start_ts`/`valid_end_ts`/`created_ts` columns were `TIMESTAMP NOT NULL` with no explicit `DEFAULT`. MariaDB (this XAMPP install's config: `explicit_defaults_for_timestamp=0`, `NO_ZERO_DATE` in `sql_mode`) rejects that for any `TIMESTAMP NOT NULL` column beyond the first one in a table, since it can't fall back to its usual implicit zero-date default. Fixed by adding `DEFAULT CURRENT_TIMESTAMP` to all three columns across all 25 hist tables — harmless, since the trigger always supplies real values explicitly; this only satisfies MariaDB's DDL validation. Would have blocked schema creation entirely on first real use.

## V0.0.11 — 2026-09-06 15:00
### Changes
- Designed the `food_log_entries` ↔ `foods_db` linkage: added nullable `food_id` (FK → `foods_db`) to `food_log_entries`, recording which catalog version an entry was logged from without live-joining for display (nutrition stays a logging-time snapshot, so re-versioning a catalog food never rewrites past logs). The quantity side needed no new column — `serving_amount`/`serving_unit_id` already resolve to a total gram/mL amount against `foods_db`'s per-100 nutrition.
- Added `last_serving_amount`/`last_serving_unit_id` to `foods_db_last_used`, caching the last quantity logged for a food so "log again" can prefill the same serving, not just identify the food.
- Updated `sql/schema.sql` (both tables + their `_hist` tables and update triggers) and `doc/wiki/Database-Schema.md` accordingly; `sql/sample_data.sql` needed no change since it doesn't yet populate `foods_db`.
- Split the schema into two databases: `nutripal` (live data) and `nutripal_hist` (every `_hist` audit table), so history can be backed up/archived on its own cadence. Every `_hist` table and every trigger's history-insert target is now schema-qualified. Documented as a general reusable pattern in `doc/wiki/Database-Design-Patterns.md`, and flagged clearly in `sql/schema.sql`'s header that Bluehost's account-specific database-name prefix (`theshaf2_`) must be substituted for `nutripal_hist` before deploying there, since the hist schema name is baked literally into every trigger body.

### Planned (not yet implemented)
- Finish the table-by-table schema review for `steps_readings`, `heart_rate_readings`, `weight_readings`, `exercise_sessions`, `sleep_sessions`/`sleep_stages`
- Meal planning — logging an intended future meal, distinct from a consumed entry
- Create the actual MySQL database and run `sql/schema.sql` (needs confirmation before touching the local database, per project convention)
- Build `scripts/import-takeout.php` to parse an extracted Takeout export and load it into the schema
- Build the live-API-to-database sync (currently the fetch scripts only write debug JSON, not the DB)
- React frontend

## V0.0.10 — 2026-09-06 14:00
### Changes
- Decided to support ingesting Google Takeout exports as a second data source alongside the live API — for fast new-user initialization (full history at once) and periodic completeness checks against the incremental API sync
- Surveyed the Takeout export format across all 6 confirmed-available categories (food, steps, exercise, heart rate, sleep, weight) — documented in `doc/wiki/Database-Schema.md` (per-month CSVs for most types, a single all-history CSV for nutrition/weight, legacy Fitbit-format JSON for exercise, and ID-bearing CSVs for sleep/sleep stages/sleep scores)
- Extensive schema design review (`food_log_entries`/`food_log_nutrients` fully finalized; a new `foods_db` personal food catalog designed from scratch; general cross-cutting patterns established and applied everywhere):
  - **No ENUM types anywhere** — every categorical value (`ingestion_source`, `meal_type`, `data_source`, `nutrient`, `dimension`, `stage_type`, `status`, etc.) is a `lut_` lookup table instead, each with its own history
  - **Full audit history + provenance** on every table — a parallel `<table>_hist` table, trigger-enforced insert/update/no-delete behavior, and a `changed_by`/`changed_by_user_id` pair recording what caused each write
  - **`SRC`/`FIX`/`MOD` non-destructive nutrient correction model** — lets a nutrient value be corrected or supplemented (e.g. tracking amino acids Google never reports) without ever overwriting the original imported value
  - **Multi-user readiness** (`users`, `groups`, `link_user_group`) built into the schema now, though no login/registration UX exists yet — the app still operates as a single hardcoded user
  - **`foods_db`** — a personal + historically-encountered food catalog with three-tier ownership (universal/group/user), version tracking for packaged foods whose real nutrition drifts over time, custom per-food units (e.g. "medium orange"), and decaying recency-weighted usage tracking for fast repeat-meal logging
  - Reconciliation model finalized: `fingerprint` (content-hash dedup) plus `api_uid` (native-ID priority over fingerprint, needed since editing a food's logged time changes its fingerprint but not its API id) plus a `mixed` ingestion-source value for genuine cross-source conflicts (time/quantity disagreements specifically, not nutrients)
  - New reusable reference doc, `doc/wiki/Database-Design-Patterns.md` — every pattern above written generically for reuse in future projects, not tied to NutriPal's own tables
  - Checkpoint `sql/schema.sql` rewritten in full (all lookups, multi-user tables, `foods_db` family, and the original 8 health-data tables with the cross-cutting patterns layered on) plus `sql/sample_data.sql` (4 days of sample meals) — **not yet re-reviewed table-by-table for `steps_readings`/`heart_rate_readings`/`weight_readings`/`exercise_sessions`/`sleep_sessions`/`sleep_stages`, expect further changes**
  - Added `APP_TIMEZONE` to `.env.example` for future local-day-bucketing queries

### Known bugs (not yet fixed)
- Takeout nutrition rows have no energy/calorie field — `energy_kcal` is estimated from macros for Takeout-sourced food entries and flagged `is_energy_estimated`

### Planned (not yet implemented)
- Finish the table-by-table schema review for `steps_readings`, `heart_rate_readings`, `weight_readings`, `exercise_sessions`, `sleep_sessions`/`sleep_stages`
- Design the `food_log_entries` ↔ `foods_db` linkage (which catalog food, what quantity) — the unit half is resolved, this part isn't
- Meal planning — logging an intended future meal, distinct from a consumed entry (Google Health has no such capability; surfaced during this schema review)
- Create the actual MySQL database and run `sql/schema.sql` (not done yet — needs confirmation before touching the local database, per project convention)
- Build `scripts/import-takeout.php` to parse an extracted Takeout export and load it into the schema
- Build the live-API-to-database sync (currently the fetch scripts only write debug JSON, not the DB)
- React frontend

## V0.0.9 — 2026-09-05 12:00
### Changes
- Expanded requested OAuth scope (`src/GoogleOAuth.php`) beyond nutrition-only to also cover `activity_and_fitness.readonly`, `health_metrics_and_measurements.readonly`, and `sleep.readonly` — decided to survey what's available across activity, heart rate/vitals, sleep, and weight/height before continuing further food-only work
- Added `scripts/fetch-metrics-test.php`, an exploratory script that probes 18 candidate data types (steps, exercise, heart rate, sleep, weight, etc.) and reports which ones actually have data in this account, saving raw responses to `storage/debug-metrics/` (gitignored)
- Documented the scope decision and survey approach in `doc/wiki/Data-Sync.md`
- Ran the survey: real data found for steps, distance, active-minutes, active-zone-minutes, exercise, active-energy-burned, heart-rate, heart-rate-variability, daily-resting-heart-rate, sleep, weight, height (plus sparse data for oxygen-saturation and body-fat); no data for vo2-max/blood-glucose; `floors` and `total-calories` aren't queryable via the `list` method at all (only `reconcile`/`rollup`/`dailyRollup` — different API shape, deferred)

### Planned (not yet implemented)
- Next build target: **steps + exercise** (activity data, toward the activity/food/weight correlation goal)
- Design MySQL schema based on the observed response shape(s)
- Integrate fetch(es) into the actual app (currently standalone scripts) and persist to the database
- React frontend

## V0.0.8 — 2026-08-10 20:00
### Changes
- Added `scripts/fetch-nutrition-test.php`, an exploratory CLI script that fetches real `nutritionLog` data points from the Google Health API for the last N days (default 10)
- Discovered the `filter` query param is rejected for the `nutritionLog` data type (unlike the documented generic interval-filter pattern) — worked around by paginating the unfiltered, newest-first list and filtering client-side by `civilStartTime`
- Confirmed real data end-to-end: 116 entries over the last 10 days, sourced from Fitbit (`dataSource.platform: "FITBIT"`), with 22 distinct nutrient types per entry — documented full response shape in `doc/wiki/Data-Sync.md`
- Noted a data-quality observation: 4 of the last 10 days had zero logged entries — needs a spot-check against the source app, not assumed to be a sync bug

### Planned (not yet implemented)
- Design MySQL schema based on the observed response shape
- Integrate the fetch into the actual app (currently a standalone script) and persist to the database
- React frontend

## V0.0.7 — 2026-08-10 19:00
### Changes
- Added `start-services.bat`/`.ps1` and `stop-services.bat`/`.ps1` to manage the local PHP dev server (port 8080) — `.bat` wrappers run PowerShell with `-ExecutionPolicy Bypass` for that invocation only, matching the pattern used in the other local web projects, so no system-wide execution policy change is needed. Never touches XAMPP/MySQL. Verified both start and stop work correctly.

## V0.0.6 — 2026-08-10 18:00
### Changes
- Created a **Web application**-type Google OAuth client (redirect URI `http://localhost:8080/auth-callback.php`) to replace the unusable Desktop-app client; recorded in `doc/credentials/google-health.md`
- Wired real credentials into local `.env` (gitignored)
- Ran the full OAuth flow end-to-end against real Google login: consent screen, callback, and token exchange all verified working; `storage/google-tokens.json` confirmed populated with `access_token`, `refresh_token`, and the correct `nutrition.readonly` scope

### Planned (not yet implemented)
- Design MySQL schema and swap `TokenStore`'s JSON file for a database-backed store
- Fetch and store actual nutrition data using the obtained access token
- React frontend

## V0.0.5 — 2026-08-10 17:00
### Changes
- Added first PHP application code: `public/` (front-end entry points), `src/` (`GoogleOAuth`, `TokenStore`, `Env`)
- Implemented the Google Health OAuth flow: `auth-login.php` redirects to Google's consent screen with the `googlehealth.nutrition.readonly` scope (`access_type=offline`, `prompt=consent` to get a refresh token); `auth-callback.php` verifies CSRF state, exchanges the auth code for tokens, and stores them
- Token storage is a temporary local JSON file (`storage/google-tokens.json`, gitignored) until the MySQL schema is designed
- Added `.env.example` / `.env` support via a small dependency-free `Env` loader (no Composer install needed for this)
- Verified locally with PHP's built-in server (`php -S`): homepage loads without config, auth routes fail with a clear error when unconfigured, and the generated Google auth URL matches Google's documented format exactly

### Known bugs (not yet fixed)
- Stored Google Health OAuth credentials (`doc/credentials/google-health.md`) are a **Desktop app** client; a **Web application**-type client must be created in Google Cloud Console (with the real redirect URI) before this flow can be tested end-to-end with real credentials

### Planned (not yet implemented)
- Design MySQL schema and swap `TokenStore`'s JSON file for a database-backed store
- Fetch and store actual nutrition data using the obtained access token
- React frontend

## V0.0.4 — 2026-08-10 16:00
### Changes
- Scoped first milestone: Google Health food data sync only (calories/nutrients), activity and weight sync deferred
- Added `doc/wiki/Data-Sync.md` documenting sync strategy: routine incremental sync reconciles (upserts) the last 7 days on every run to catch backfilled/edited entries, plus a separate manual full-resync option for anything older

### Known bugs (not yet fixed)
- Stored Google Health OAuth credentials (`doc/credentials/google-health.md`) are a **Desktop app** client; NutriPal is a PHP web app, so a **Web application**-type client with proper redirect URIs needs to be created before implementing the OAuth flow

### Planned (not yet implemented)
- Scaffold the PHP + MySQL + React project structure
- Google Health OAuth flow (web application client) and food-data sync implementation
- Local MySQL schema for food log entries

## V0.0.3 — 2026-08-10 15:00
### Changes
- Decided tech stack: PHP + MySQL backend (JSON API) developed locally on XAMPP, React SPA frontend, targeting Bluehost shared hosting for eventual deployment (auth and env-based secrets designed in from the start, deployment itself deferred)
- Added `doc/wiki/Architecture.md` documenting the stack decision and rationale
- Expanded scope in `README.md` / `doc/wiki/Home.md`: added custom meal creation and fast repeat-meal logging (e.g. near-identical daily breakfast with minor tweaks) to the feature list

### Planned (not yet implemented)
- Scope and build the first slice of functionality
- All application code (currently nothing exists beyond docs/scaffolding)

## V0.0.2 — 2026-08-10 14:00
### Changes
- Added root `README.md`
- Scoped the rebuild in `README.md` / `doc/wiki/Home.md`: NutriPal will be a web app for viewing/analyzing Google Health (formerly Fitbit) data from the desktop, with enhanced macro/micronutrient analysis and activity (running, workouts) vs. weight/food correlation. Building incrementally rather than all at once.

### Planned (not yet implemented)
- Decide tech stack for the new build
- All application code (currently nothing exists beyond docs/scaffolding)

## V0.0.1 — 2026-08-10 13:00
### Changes
- Fixed `.github/workflows/main.yml` (Auto Update Wiki): the wiki-repo push URL was malformed (`@://github.com` instead of `@github.com/`, and `{{ github.repository }}` missing its `$` so it was never interpolated), causing the push step to fail on every run
- Added explicit `permissions: contents: write` to the workflow so `GITHUB_TOKEN` can push to the wiki repo regardless of repo/org default token permissions

### Known bugs (not yet fixed)
- The workflow still requires the GitHub wiki to be manually initialized (Settings → Features → Wiki → create a first page) before its "Checkout Wiki Repo" step can succeed — not yet confirmed done for this repo

## V0.0.0 — 2026-08-10 12:00
### Changes
- Initialized local git repository for NutriPal
- Added `.gitignore` excluding `doc/archive/` (reference material stays local-only, never committed)
- Added `doc/credentials/` for credential reference notes (stays local-only, never committed — see `.gitignore`)
- Added `doc/wiki/` with initial `Home.md`
- Added this `CHANGELOG.md`

### Planned (not yet implemented)
- Decide and scope the actual NutriPal app going forward (an earlier prototype exists in `doc/archive/` as reference material for this rebuild)
