# Changelog

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
