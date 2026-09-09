# Data Sync Strategy

## First milestone scope

Food data only to start (calories and other nutrients available via the Google Health API's nutrition scope). Activity and weight sync are deferred to later milestones.

## Why sync strategy matters

Food log entries can be edited or backfilled for past dates after the fact — someone might log breakfast today but go back and correct yesterday's lunch. A naive "only fetch what's new since last sync" approach would silently miss those edits.

## Approach

- **Incremental sync (routine):** every regular sync re-fetches and reconciles (upserts, not blind inserts) the last **7 days**, not just brand-new entries, so edits to recently-past days get picked up automatically.
- **Full resync (manual/on-demand):** a separate, explicitly-triggered option to resync the entire available history beyond the 7-day window, for cases where older data was edited outside that range or a backfill/fix is needed.

## OAuth implementation (done, verified end-to-end)

`public/auth-login.php` and `public/auth-callback.php` implement the Google Health OAuth flow (`GoogleOAuth` / `TokenStore` / `Env` in `src/`). Scope used: `https://www.googleapis.com/auth/googlehealth.nutrition.readonly` (read-only, food/nutrition data only — matches the food-only first milestone). Requests `access_type=offline` + `prompt=consent` to obtain a refresh token. Tokens are currently stored in `storage/google-tokens.json` (gitignored) as a placeholder until the MySQL-backed store replaces it.

Endpoints confirmed against Google's current docs (developers.google.com/health):
- Auth: `https://accounts.google.com/o/oauth2/v2/auth`
- Token: `https://oauth2.googleapis.com/token`

## Real API response shape (observed, 2026-08-10)

Fetched live data via `scripts/fetch-nutrition-test.php` (last 10 days, 116 entries). Findings:

- **Endpoint:** `GET https://health.googleapis.com/v4/users/me/dataTypes/nutrition-log/dataPoints`
- **No server-side date filtering for this data type.** The `filter` query param (documented generically for interval data types via `{type}.interval.civil_start_time`) is rejected for `nutritionLog` specifically ("does not match any data type") — tried both `nutrition-log.*` and `nutritionLog.*`, both fail. Response is paginated (`pageSize`, `pageToken`), ordered newest-first. Working approach: paginate and filter client-side by `nutritionLog.interval.civilStartTime`, stopping once entries fall outside the window.
- **Entry shape per data point:**
  - `dataSource.recordingMethod` / `dataSource.platform` (e.g. `"FITBIT"` — confirms this is synced Fitbit data, not newly Google-native)
  - `nutritionLog.interval`: `startTime`/`endTime` (UTC) + `civilStartTime`/`civilEndTime` (local date/time breakdown: year/month/day, hours/minutes)
  - `nutritionLog.energy.kcal`, `energyFromFat.kcal`, `totalCarbohydrate.grams`, `totalFat.grams`
  - `nutritionLog.nutrients[]`: array of `{nutrient: <ENUM>, quantity: {grams}}` — **22 distinct nutrient types observed**: CALCIUM, CHOLESTEROL, DIETARY_FIBER, IRON, PROTEIN, SATURATED_FAT, SODIUM, SUGAR, POTASSIUM, VITAMIN_A, VITAMIN_C, COPPER, IODINE, MAGNESIUM, NIACIN, PHOSPHORUS, RIBOFLAVIN, THIAMIN, VITAMIN_B6, ZINC, PANTOTHENIC_ACID, TRANS_FAT
  - `nutritionLog.mealType` (e.g. `ANYTIME`, `DINNER`), `nutritionLog.serving.amount` (+ optional `foodMeasurementUnitDisplayName`)
  - `nutritionLog.food` (reference to a `food` data point ID) + `nutritionLog.foodDisplayName`
- **Data quality observation:** of the last 10 days, 4 days (Aug 4, 6, 7, 8) had zero entries while others had 15-30 — likely just days without logged food, but worth spot-checking against the source app before assuming sync is complete.
- This confirms the nutrient set is per-entry (not a fixed daily total), which fits the "additional micronutrients" goal well — most of what we'd want is already here rather than needing a separate data source.

## Scope expansion: activity, heart rate/vitals, sleep, weight/height (2026-09-05)

Before building more on food, decided to add read-only access to additional categories and survey what data actually exists in the account before committing to which to build out first. Google Health uses one OAuth scope per category, so each can be added independently:

- `activity_and_fitness.readonly` — steps, distance, exercise sessions, active minutes, active zone minutes, floors, active energy burned, total calories
- `health_metrics_and_measurements.readonly` — heart rate, HRV, resting heart rate, VO2 max, oxygen saturation (SpO2), blood glucose, body fat, **weight, height**
- `sleep.readonly` — sleep sessions

Not requested: ECG, irregular rhythm notifications, GPS/location during exercise (niche, deferred), and all write scopes.

`src/GoogleOAuth.php`'s default scope now requests all four read-only scopes together. **Existing stored tokens predate this change and only carry the nutrition scope** — re-running `auth-login.php` (full re-consent) is required before the new scopes are usable.

`scripts/fetch-metrics-test.php` probes 18 candidate data types (one HTTP request each, no date filtering) and reports, per type, whether the account has any data at all — raw responses saved to `storage/debug-metrics/<type>.json` (gitignored). This is a survey step only, to inform what to prioritize next; it doesn't parse or persist anything.

### Survey results (observed, 2026-09-05)

Has real data (most-recent ~50 points each, unfiltered):
- **Activity:** steps, distance, active-minutes, active-zone-minutes, exercise (25 sessions), active-energy-burned
- **Vitals:** heart-rate, heart-rate-variability, daily-resting-heart-rate, oxygen-saturation (4 points — sparse), body-fat (5 points — sparse)
- **Sleep:** sleep (12 sessions)
- **Body measurements:** weight (50 points), height (7 points)

No data in this account: `vo2-max`, `blood-glucose` (expected — not tracked by this device/setup).

**Not queryable via `list` at all:** `floors` and `total-calories` return HTTP 400 — the API says these two only support `reconcile`, `rollup`, and `dailyRollup` actions, not a raw dataPoints list. They'd need a different endpoint/approach (daily aggregate rollup) if wanted later; skipped for now.

**Takeaway:** steps, distance, exercise, heart rate, sleep, and weight all have solid real data and are viable to build out next. Oxygen saturation and body fat are populated but sparse. VO2 max and blood glucose aren't tracked at all currently.

## Sync implementation (done, verified against the real account, 2026-09-08)

`scripts/sync-google-health.php` implements the incremental/full-resync design above, against the schema finalized in `sql/schema.sql` (see `doc/wiki/Database-Schema.md`) — all 9 categories the schema supports, not just food. Usage: no flags (default, last 7 days), `--days=N`, or `--full`.

**Two dedup strategies**, decided by what the live API actually returns (checked directly, not assumed):
- `nutrition-log`, `sleep`, `exercise`, `weight`, `height` — each dataPoint's `name` field ends in a stable numeric ID, so these get a real upsert: look up by `(user_id, api_uid)`, insert if missing, update only if a real column value actually changed (avoids writing pointless history snapshots on a routine re-sync of unchanged data).
- `daily-resting-heart-rate` — no stable per-point ID, but the schema already has a real natural key (`UNIQUE(user_id, reading_date)`) — same upsert-if-changed approach, keyed on that instead.
- `steps`, `heart-rate`, `heart-rate-variability` — confirmed these dataPoints have **no** `name`/ID field at all, and the schema's `BEFORE DELETE` trigger rules out a delete-and-reinsert reconcile. Dedup here is insert-missing against existing `reading_time` values, not a true reconcile — accepted since this is passively-sampled continuous sensor data that isn't realistically edited after the fact, unlike user-editable food/sleep/exercise/weight. This is a deliberate, disclosed scope reduction from the "reconcile" language above for these three types specifically.

**Nutrition gets real gram-accurate serving units**, closing the gap the Health Connect importer's quantity-problem fix had to placeholder around (see `doc/wiki/Database-Schema.md`'s "quantity problem" section): each `nutrition-log` entry's `food` reference is fetched (`GET dataTypes/food/dataPoints/{id}`, cached per run) for its `servings[]` list, and true grams for whatever unit was actually logged are derived using the list's `"gram"` entry as a pivot (`gramsPerUnit(u) = multiplier(u) / multiplier(gram)`). Verified against real data: "1 tortilla" → ~51g (matching a hand-computed check from the earlier comparison pass), "1 medium apple" → 167g, "1 oz" → 28g, "1 egg" → 50g. Falls back to the Health Connect importer's ratio-based placeholder-unit approach when a food has no gram entry or the logged unit isn't listed.

**Two real bugs found by actually running this against the account, not just reviewing the code:**
- `exercise_sessions.distance` `DECIMAL(10,4)` overflowed on ordinary walking distances once populated with real millimeter-scale values from the API (a 6km walk = 6,148,000mm, 7 digits, exceeding the column's 6-integer-digit budget) — MySQL silently clamped every value to `999999.9999`, which also broke idempotency (the clamped value never matched the real incoming value, so every re-sync issued a pointless update forever). Root cause was really a unit mismatch: this column also holds Takeout's miles at a wildly different scale. Fixed by standardizing `distance` to **meters** at ingest for every source (new `unit_conversions` row) rather than widening the column — confirmed via MySQL's DECIMAL storage formula that `DECIMAL(14,0)` and `DECIMAL(14,4)` cost the identical 7 bytes (storage is driven by total digit count, not decimal placement), so widening alone would have bought nothing and still cost Takeout's fractional-mile precision.
- `lut_data_source.name` uses a case-insensitive collation (MySQL default), so the live API's `"FITBIT"` (from `dataSource.platform`) collided with Health Connect's already-imported `"Fitbit"` (an app display name) as duplicates at the DB level, even though the in-memory PHP cache treated them as different strings and attempted a fresh insert. Fixed by catching that specific duplicate-key error and re-resolving the existing row.

**Verified idempotent**: ran the sync three times in a row against the same 2-day window; the third run reported no real change for every row in every category before running the real default 7-day sync.

## Request/response logging and replay (done, verified, 2026-09-08)

Every live run of `scripts/sync-google-health.php` records the raw request/response for every API call it makes to `storage/api-logs/<run_id>/<endpoint>.jsonl` (`run_id` matches the timestamp already used for that run's `storage/import-logs/*.log` file), plus a `manifest.json` capturing the run's `--full`/`--days` window. On by default — `--no-log` opts out, since a `--full` resync over years of heart-rate data can log hundreds of MB. The `Authorization` header is deliberately never written to these logs (verified by grepping a real run's output for any token material — none found); everything else, including full response bodies, is recorded verbatim.

`--replay=<run_id>` re-runs the exact same parsing/ingestion code against a previously-recorded run instead of the network: no OAuth token refresh happens at all, and the original run's `--full`/`--days` window is restored automatically from its `manifest.json`. Verified against a real run: replaying completed in 0.3s versus the original 13.2s live run (confirming zero network calls), and every category correctly reported "already exists, no change" — the DB ended up in the identical state without hitting Google again. This is what makes re-testing a parsing fix, or auditing exactly what a run received, cheap and reproducible — and it sidesteps the fact that the live API's rolling window means re-querying later might not even return the same data any more.

`--debug` additionally traces per-record processing decisions to the human-readable log (matched food/brand and real-gram-vs-fallback match for nutrition, session/action for sleep/exercise/measurements/daily-resting-heart-rate) — per-*page*, not per-row, for the three high-volume insert-missing categories (steps/heart-rate/HRV), since tracing every individual reading wouldn't be practical to read. Off by default.

## Triggering from the UI (done, verified, 2026-09-08)

The Sync tab (`frontend/src/components/Sync.jsx`) runs both this script and the Health Connect importer synchronously from the browser — the request blocks until the invoked script exits, then the page shows its captured stdout. Backed by three endpoints: `public/api/run-sync.php` (live sync, with full/days/debug controls, or `--replay=<run_id>`), `public/api/sync-runs.php` (lists `storage/api-logs/` run ids with manifests for the replay dropdown), and `public/api/import-hc.php`. Both script-invoking endpoints build the CLI command with `escapeshellarg()` on every dynamic argument and run it via `PHP_BINARY ... 2>&1`.

The Health Connect import endpoint takes a **path already on disk** (`{"path": "..."}`), not a browser file upload. An upload was the original design, but a real ~500MB export took over 20 minutes for PHP's built-in dev server (`php -S`, what `start-services.ps1` runs) to even finish receiving the multipart body — a known inefficiency of that SAPI for large uploads, not something worth working around. A path sidesteps the transfer entirely and matches how the CLI script already works.

The replay dropdown (`public/api/sync-runs.php`) shows each run's actual start time, covered window (e.g. "Last 7d (covers 2026-09-02 to 2026-09-09)", or "Full history"), and duration — read from that run's own human-readable log rather than showing a bare run id.

Progress feedback for all three actions (live sync, replay, HC import) is a client-side elapsed-time counter plus a one-time "last similar run took ~Xs" estimate (`public/api/sync-progress.php`), fetched once right before the blocking request fires. This was originally designed as a live-polled log tail, but PHP's built-in dev server is single-threaded — proved directly that a request sent to the progress endpoint while an import was running queued for the entire run and only returned once it finished, so any design polling it *during* the blocking request is structurally impossible locally. A real live tail would need a second dedicated server process; not worth that permanent complexity for this.

## Two more real bugs, found via this UI (fixed, 2026-09-08/09)

Testing the new import UI against the real Health Connect export a second time (simulating a user re-importing the same file) surfaced two bugs neither of which were about the UI itself:

- **Heart-rate duplication.** HC's per-sample heart-rate rows (`heart_rate_record_series_table`) have no per-sample id — only the parent session does — so `import-health-connect.php` never set `api_uid` for them, leaving it `NULL` always. `heart_rate_readings`' `UNIQUE(user_id, api_uid)` constraint is a no-op against NULLs, so `INSERT IGNORE` re-inserted every reading on the second run. Confirmed against the real database: 5,712,042 rows where only 2,856,973 were distinct — exactly 2×. Fixed with a real `UNIQUE(user_id, reading_time)` constraint, matching the identity the live sync's own in-memory dedup already assumed.
- **Sleep stages silently dropped, not deduplicated, on re-import.** The sleep-session insert's duplicate-key catch never recorded the already-existing session's id, so on a re-import every stage belonging to a session the DB already had found no parent to attach to and was discarded as `skipped_error` rather than being checked for a duplicate. Fixing that lookup alone would have started duplicating stages instead — `sleep_stages` had the identical inert-`api_uid` problem as heart rate — so both were fixed together: the lookup now resolves the existing session's real id, and a new `UNIQUE(user_id, sleep_session_id, stage_type_id, start_time)` constraint gives stages a working natural key.
- Adding the `heart_rate_readings` constraint immediately exposed a third issue: `sync-google-health.php`'s `--full` mode deliberately skips its in-memory timestamp preload (holding millions of timestamps in PHP memory for full-history dedup isn't practical), so it relied on a plain `INSERT` never colliding with anything — which broke the moment a `--full` run's live-API heart-rate data overlapped a timestamp Health Connect had already inserted. Changed to `INSERT IGNORE` with `rowCount()` deciding inserted-vs-skipped.

Fixed by rebuilding the database from the corrected schema and fully re-importing (HC export + a real `--full` live sync); verified via direct queries that both tables have zero internal duplicates, and via a second real re-import of the same file that re-running no longer reproduces either bug.

## A fourth bug, and an unexplained incident (fixed / unresolved, 2026-09-09)

While restarting the dev server to clear a backlog of stuck connections (from debugging the browser automation tool, unrelated to the app itself), an unexplained `--full` live sync was found running — started 2026-09-09 01:54, cause never determined (best guess: a stray duplicate request among the stuck connections, not confirmed). It had completed nutrition/sleep/exercise/weight/height/daily-resting-heart-rate and was partway through steps when killed. Direct queries afterward showed `heart_rate_readings`/`sleep_stages` still clean (protected by the constraints above), but `steps_readings` had gained ~138,000 duplicate rows (874,603 total vs. 537,008 distinct) from the portion that ran before being killed — same root cause as the heart-rate bug: `--full` mode skips its dedup preload, and `steps_readings` had no DB-level guard for live-API-sourced rows. Fixed the same way: added `UNIQUE(user_id, reading_time)` to `steps_readings`, and proactively to `heart_rate_variability_readings` too (identical latent gap, not yet observed duplicating). Rebuilt/re-imported again; verified all four tables (`heart_rate_readings`, `sleep_stages`, `steps_readings`, `heart_rate_variability_readings`) have zero internal duplicates via direct query, and a real live sync afterward stayed clean.

This also incidentally resolves cross-source duplication for steps and heart rate specifically (see "Open items" below) — one canonical reading per user+timestamp is now enforced at the DB level regardless of which source wrote it.

## Open items

- **Cross-source duplication between Health Connect and the live API is not resolved for sleep sessions, exercise sessions, weight/height, or food log entries.** Health Connect's `api_uid` (its own local `uuid`) and the live API's `api_uid` (its cloud dataPoint id) are different ID spaces for the same real-world event — `UNIQUE(user_id, api_uid)` can't detect a session/entry already exists from the other source. Steps and heart-rate readings are no longer affected (see above). No automated mitigation yet for the remaining categories; the practical guidance until real reconciliation is designed is to pick a sync window that starts after the last Health Connect export's own coverage.
- The unexplained `--full` sync from 2026-09-09 01:54 was never root-caused. If it recurs, capture the dev server's active connections/request pattern before restarting it, rather than just clearing the backlog.
- Real-gram custom units created by the live-API sync are not retroactively used to correct Health-Connect-created placeholder units for what might be the same real food — tracked as future work, not attempted here.
- `--full` mode has now been exercised against the real account's entire history multiple times (~39-60 minutes per run, ~3.4M rows across steps/heart-rate/HRV) — no further bugs found beyond the fixes above.
- `lut_activity_type` mapping stays a plain find-or-create keyed on each source's raw activity code — no canonical cross-source mapping yet.
- Google Health API request/sync rate limits were never explicitly checked — no throttling has been hit in testing so far, but this hasn't been run at a truly high frequency either.
- A **Web application**-type OAuth client exists and is verified working (see `doc/credentials/google-health.md`); a production redirect URI for Bluehost will need to be added once deployment happens.
