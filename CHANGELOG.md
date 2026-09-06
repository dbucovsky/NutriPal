# Changelog

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
