# Changelog

## V0.1.6 — 2026-09-09 16:00
### Changes
- **Fixed cross-source duplication for `sleep_sessions`, `exercise_sessions`, and `measurements` (weight/height).** Health Connect and the live API each assign their own `api_uid` to the same real-world event, so `UNIQUE(user_id, api_uid)` — a real, working guard against same-source re-import — never caught the same session/reading arriving from *both* sources. Confirmed via real data before touching anything: 660/710 HC sleep sessions, 1980/2015 HC exercise sessions, and 513/521 HC weight readings each matched a live-API row on `start_time`/`reading_time` alone (exercise sessions matched exactly on `end_time` too; sleep sessions' `end_time` can drift up to ~1 minute between sources, so only `start_time` is safe to key on; measurement *values* differ slightly by source — HC rounds to 100g, the live API keeps single-gram precision — so `value` deliberately isn't part of the key either).
- Added real natural-key constraints: `UNIQUE(user_id, start_time)` on `sleep_sessions` and `exercise_sessions`, `UNIQUE(user_id, measurement_type_id, reading_time)` on `measurements`. `sync-google-health.php`'s generic `upsertByNaturalKey()` gained an optional cross-source check — if the primary `(user_id, api_uid)` lookup misses but the alternate (natural-key) lookup hits, the row already exists under the other source's `api_uid`; skip rather than insert (would duplicate) or update (would silently overwrite that source's provenance and, for measurements, its more-precise value, for no benefit). `import-health-connect.php`'s sleep-session dedup lookup switched from `api_uid` to `start_time` for the same reason — the actual colliding row on a cross-source hit has a *different* `api_uid`, so looking it up by `api_uid` would miss it entirely.
- **Fixed a crash the new `sleep_stages` interaction surfaced**: `syncSleep()`'s stage insert used a plain `INSERT` guarded only by an in-memory `(start_time, end_time)` check — but `uq_sleep_stages_natural` (added in V0.1.5) keys on `(session, stage_type, start_time)`, not `end_time`, so a stage whose `end_time` drifts slightly between sources slipped past the in-memory check and crashed on the real constraint. Changed to `INSERT IGNORE` with `rowCount()` deciding inserted-vs-duplicate, dropping the now-redundant in-memory check entirely.
- Verified against the real database: rebuilt from the corrected schema, re-imported the Health Connect export, then ran a real `--full` live sync — `SLEEP_SESSIONS: inserted=552, skipped_cross_source=660`, `EXERCISE: inserted=291, skipped_cross_source=1979`, `WEIGHT: inserted=6, skipped_cross_source=513`, matching the pre-fix analysis almost exactly. Confirmed zero internal duplication on all three tables via direct query (`COUNT(*)` equals `COUNT(DISTINCT ...)` on each natural key), and confirmed a second HC re-import stays fully idempotent (every row `skipped_duplicate`, DB counts unchanged).

### Known bugs (not yet fixed)
- **`food_log_entries` cross-source duplication is unresolved and structurally harder than the three fixed above.** Checked before starting: 13,094 food-log pairs match on `(user_id, start_time)` alone, but only 122 also match on `food_id` — the same real meal usually resolves to a *different* `food_id` between sources (Health Connect's placeholder-serving-unit version vs. the live API's real-gram version), so a naive natural-key dedup can't just ignore `food_id` the way it does for sleep/exercise/measurements. A real fix needs the already-tracked "retroactively reconcile Health-Connect placeholder units against real-gram live-API data" work first, so the same real food resolves to the same `food_id` from either source. Deferred as a separate task.

## V0.1.4 — 2026-09-08 23:30
### Changes
- **`scripts/sync-google-health.php` now logs every live API request/response** it makes to `storage/api-logs/<run_id>/<endpoint>.jsonl` (on by default; `--no-log` opts out), plus a `manifest.json` recording that run's `--full`/`--days` window. All two HTTP call sites (`streamDataPoints()`'s pagination, `fetchFoodServings()`'s food-resource lookups) now go through one shared `apiCall()` function, which is also the only place the `Authorization` header ever touches memory — it's deliberately never written to the log (verified by grepping a real run's logged output for any token material: none found).
- **New `--replay=<run_id>` mode**: re-runs the exact same parsing/ingestion code against a previously-recorded run's logs instead of the network, via a new `ReplayReader` that hands back recorded responses in original order (falling back to a synthetic empty page once exhausted, which `streamDataPoints()`'s existing "no more points" check already treats as end-of-pagination — no special-casing needed). No OAuth token refresh happens in replay mode; the original run's `--full`/`--days` window auto-restores from its manifest. Verified against a real run: replay completed in 0.3s vs. the original 13.2s live run, with every category correctly reporting "already exists" and zero new rows written.
- **New `--debug` flag**: traces per-record processing decisions to the human-readable log via a new `debugLog()` helper — food match type/brand/version for nutrition, session/action for sleep/exercise/measurements/daily-resting-heart-rate, and per-*page* (not per-row) counts for the three high-volume insert-missing categories (steps/heart-rate/HRV), since a full day's worth of per-reading trace lines wouldn't be practical to read.
- Added `/storage/api-logs/` to `.gitignore` — same sensitivity as the existing `storage/import-logs/` entry (real personal health data verbatim).

## V0.1.5 — 2026-09-09 04:00
### Changes
- **New Sync tab in the UI** to trigger `sync-google-health.php` (live, with `--full`/`--days`/`--debug` controls, or `--replay=<run_id>` picked from a dropdown populated from `storage/api-logs/`) and `import-health-connect.php`, both run synchronously (the request blocks until the script exits, then shows its captured output). New endpoints `public/api/run-sync.php`, `public/api/sync-runs.php`, `public/api/import-hc.php`. The Health Connect import takes a **path already on disk**, not a browser file upload — an upload was tried first and abandoned after a real ~500MB export took over 20 minutes for PHP's built-in dev server (`php -S`, used by `start-services.ps1`) to merely receive the multipart body, a known inefficiency of that SAPI for large uploads; a path is also how the existing CLI script already works. `start-services.ps1` now starts the dev server with raised `upload_max_filesize`/`post_max_size`/unlimited execution time regardless (harmless to keep, no longer load-bearing for this feature).
- **Fixed a real bug found via this new UI: re-running the Health Connect importer against the same export duplicated every heart-rate reading.** HC's per-sample heart-rate rows (`heart_rate_record_series_table`) carry no per-sample id — only the parent session does — so `api_uid` was always `NULL` and the table's `UNIQUE(user_id, api_uid)` constraint (a no-op against NULLs) never caught the re-insert. Confirmed against the real database: 5,712,042 rows where only 2,856,973 were distinct, exactly 2×. Fixed with a real `UNIQUE(user_id, reading_time)` constraint (`sql/schema.sql`), since one reading per user+timestamp is the actual real-world identity here — already the assumption the live sync's own in-memory dedup makes, just never enforced at the DB level.
- **Fixed a related bug in the same code path: sleep stages for an already-imported session were silently dropped, not deduplicated, on re-import.** The session-insert's duplicate-key catch never recorded the existing session's id, so every stage belonging to a session already in the database found no parent to attach to and was discarded as `skipped_error`. Naively fixing that lookup would have started duplicating stages instead (`sleep_stages` had the identical inert-`api_uid` problem as heart rate) — fixed both together: the session lookup now resolves the existing session's id on a duplicate, and a new `UNIQUE(user_id, sleep_session_id, stage_type_id, start_time)` constraint gives stages a real natural key.
- **Fixed a crash this surfaced in `sync-google-health.php`**: a `--full` sync deliberately skips its in-memory timestamp preload (full-history dedup would mean holding millions of timestamps in memory), so it relied entirely on a plain `INSERT` never colliding with anything — which the new `heart_rate_readings` constraint immediately broke the first time live-API and Health Connect data overlapped on the same timestamp. Changed to `INSERT IGNORE` with `rowCount()` deciding inserted-vs-skipped, matching the pattern already used elsewhere in this script.
- Rebuilt the database from the corrected schema and fully re-imported (Health Connect export + a real `--full` live sync) to clean up the duplicated rows; verified via direct queries that `heart_rate_readings` and `sleep_stages` now have zero internal duplicates, and via a second real re-import that re-running no longer reproduces either bug.
- **Richer "replay a prior run" picker**: each entry now shows when it ran, its window (e.g. "Last 7d (covers 2026-09-02 to 2026-09-09)" or "Full history"), and its actual duration — read straight from that run's own human-readable log (`storage/import-logs/sync-google-health-<run_id>.log`, matched against its `complete in Xs` line) rather than the bare run id it showed before.
- **Rough progress feedback for all three Sync actions** (live sync, replay, HC import): an elapsed-time counter plus a "last similar run took ~Xs" estimate fetched once when the action starts. Originally designed as a live-polled log tail, but PHP's built-in dev server (`php -S`) is single-threaded — proved directly that a request sent to a progress endpoint while an import was running just queued for the entire ~3 minutes and only returned once the import finished, so any polling-based design is structurally starved out locally. Simplified to a one-time estimate fetched *before* the blocking request fires, plus a client-side-only elapsed timer; the progress bar caps at 95% and just sits there past the estimate rather than claiming false completion.
- **Fixed the same class of bug in `steps_readings` and proactively in `heart_rate_variability_readings`.** Found when an unexplained `--full` live sync (started 2026-09-09 01:54, cause undetermined — best guess is a stray duplicate request among several stuck connections queued on the dev server while debugging the browser automation tool, but not confirmed) duplicated ~138,000 steps rows before being interrupted: `--full` mode's dedup preload is skipped by design, and `steps_readings` had no DB-level guard for live-API rows (which never get a real `api_uid`), same root cause as the heart-rate bug above. Added `UNIQUE(user_id, reading_time)` to both tables (mirroring the heart_rate_readings fix) and rebuilt/re-imported again; this also incidentally closes the steps cross-source duplication noted below, since one canonical reading per user+timestamp is now enforced regardless of source.

### Known bugs (not yet fixed)
- Cross-source duplication for **sleep sessions, exercise sessions, weight/height, and food log entries** is still unresolved — Health Connect and the live API each have their own id space for the same real-world event, so `UNIQUE(user_id, api_uid)` can't recognize the same session/entry arriving from both sources. Narrowed this session: steps and heart-rate readings are no longer affected, since their new natural-key constraints (`UNIQUE(user_id, reading_time)`) catch duplicates regardless of source.
- The unexplained `--full` sync mentioned above was never root-caused. Watch for a repeat; if it recurs, capture the dev server's request pattern at the time rather than restarting it immediately.

## V0.1.3 — 2026-09-08 19:15
### Changes
- **Shared date across tabs**: the date is now lifted up to `App.jsx` and rendered once above the tab switcher, instead of each page (Food/Heart Rate/Sleep/Exercise) keeping its own independent date state — switching tabs now keeps the same day selected rather than each page silently resetting to today.
- **Real date picker instead of prev/next arrows**: `DateNav.jsx` now shows a button formatted as "Weekday DD-MMM-YYYY" (e.g. "Tuesday 08-Sep-2026") that opens the browser's native date picker (`input.showPicker()`) when clicked, backed by a visually-hidden real `<input type="date">` so arbitrary dates can be entered directly, not just stepped one day at a time.
- **Fixed a real bug: sleep stages were grouped by type instead of shown in chronological order.** `sleep.php`'s stage query used `GROUP BY stage_type` with `SUM()`, which merged every LIGHT segment (or DEEP, REM, etc.) across the whole night into one total — losing the actual sequence of sleep cycles. A real night's sleep normally cycles through stages many times (confirmed against real data: one session had 49 individual segments merged down to just 4 stage blocks). Fixed to return segments in chronological order (`ORDER BY start_time`, no grouping) for the stage bar, with per-type totals computed separately in PHP for the legend. Verified: the same real session now renders as a genuine hypnogram-style sequence instead of four solid blocks.
- Removed `dateUtils.js`'s now-unused `shiftDate()` (no longer needed without prev/next arrows), replaced with `formatDisplayDate()`.

## V0.1.2 — 2026-09-08 18:45
### Changes
- The Heart Rate chart now overlays sleep (blue) and exercise (orange) periods as shaded background bands directly on the bpm timeline, so correlations (a heart-rate spike during a walk, the overnight low during sleep) are visible at a glance — verified against real data: both exercise bands lined up exactly with the two heart-rate spikes on a real day, and the sleep band lined up with the overnight low.
- Required switching the chart's x-axis from category labels to a linear "minutes since local midnight" scale (0–1440) so the bpm line and the overlay boxes share one coordinate system (`chartjs-plugin-annotation`, a new small dependency).
- `public/api/heart-rate.php` now also returns `exercise_periods`/`sleep_periods`, clipped to the current day's [0, 1440] window (a sleep session that started the evening before gets clipped to start at 0) using an *overlap* query — does the session touch this day's window at all — which is deliberately looser than `exercise.php`/`sleep.php`'s own single-page day-assignment rules, since a chart overlay should show anything touching the visible window, not just sessions "assigned" to this exact day.

## V0.1.1 — 2026-09-08 18:15
### Changes
- Added three more pages: **Heart Rate** (resting/avg/min-max bpm + avg HRV stats, plus a day-shaped bpm line chart bucketed into 10-minute averages server-side so the browser never has to chart tens of thousands of raw readings), **Sleep** (session duration, start/end times, and a proportional stage-breakdown bar with a legend), and **Exercise** (a day's sessions with duration/calories/distance/steps/avg heart rate). App now has a simple tab switcher (Food / Heart Rate / Sleep / Exercise) in `App.jsx`.
- New PHP endpoints `public/api/heart-rate.php`, `sleep.php`, `exercise.php`, alongside a new shared `src/LocalDay.php` extracted from `food-log.php`'s local-day-bucketing logic (now used identically by all four endpoints instead of being repeated). Sleep uses a different bucketing rule than the other three — a session is shown on the day it *ended*, not started, since sessions usually span midnight.
- Added `chart.js`/`react-chartjs-2` to `frontend/` — the first frontend dependency beyond React itself.
- New shared frontend pieces: `frontend/src/components/DateNav.jsx` and `frontend/src/dateUtils.js` (date-shifting math anchored at UTC noon to avoid DST off-by-ones, plus converting the API's UTC datetime strings to the viewer's local time for display), extracted from `FoodLog.jsx` since all four pages need the same date-navigation behavior.
- Verified all three new endpoints against real data and in a real browser (each page, several real dates, empty-state days).

### Known, disclosed limitations
- All three new pages surface the same already-disclosed Health-Connect/live-API duplication issue as the food log does — e.g. a night's sleep or a walk shows up twice (once per source) on days covered by both. Confirms this is a real, pervasive, cross-category symptom now visible in every page, not just food — raises the priority of an actual reconciliation fix.

## V0.1.0 — 2026-09-08 17:30
### Changes
- **Started the frontend** — the first real application screen exists. New `frontend/` (Vite + React, plain JavaScript): a day's food log with meal grouping (Breakfast/Lunch/Dinner/Snack/Anytime), real-world serving labels, and derived macros per entry plus a daily total. Date navigation (prev/next day) included.
- New minimal JSON API, one file per endpoint under `public/api/` (matching the existing one-file-per-concern style, no router/framework introduced): `food-log.php` (the screen's data) and `login.php` (see below). Verified directly against the real database, including the day-boundary edge case: an entry at UTC `2026-09-06 03:55` (local `2026-09-05 23:55`, `APP_TIMEZONE=America/New_York`) correctly lands only on `2026-09-05`, not `2026-09-06` — the naive-UTC-bucketing mistake already found and avoided earlier this session (see `doc/wiki/Data-Sync.md`).
- Added a **placeholder login** (explicitly no password, session, or security of any kind) — `public/api/login.php` looks up a real user by email, `frontend/src/components/Login.jsx` + `App.jsx` hold the result in React state persisted to `localStorage`. Exists purely to get the frontend/backend round-trip pattern established (including a POST, not just GETs) before more screens get built on a hardcoded user.
- Added the missing `APP_TIMEZONE` to the real local `.env` (present in `.env.example` since V0.0.10 but never actually set) — without it, local-day bucketing was silently falling back to UTC.
- Verified end-to-end in a real browser (not just curl): log in with the real seeded email, browse several real days of food (including ones with duplicate Health-Connect/API-sourced entries for the same food — the already-disclosed cross-source duplication limitation is now visibly obvious in the UI, e.g. a day's total showing roughly double a realistic value), refresh to confirm login persists, log out and back in.
- `doc/wiki/Architecture.md` gets a new "Frontend (dev setup)" section (how to run it, the `/api` proxy) and a correction: the PHP backend runs locally via `php -S`, not Apache — XAMPP is only used for MySQL locally.

### Known, disclosed limitations
- The cross-source duplication issue (documented since V0.0.16) is now directly visible to a user looking at a real day's food log, not just a database-level concern — worth prioritizing the actual reconciliation fix sooner now that it has a visible symptom.
- Login has zero real security — anyone can "log in" as any real user by typing their email, and every API endpoint trusts whatever `user_id` it's given with no authorization check. Fine for single-developer local use only.

## V0.0.21 — 2026-09-08 16:45
### Changes
- Fixed `README.md`, which had the same "no application code exists yet" staleness as `doc/wiki/Home.md` did (already fixed in V0.0.18).

## V0.0.20 — 2026-09-08 16:30
### Changes
- **Fixed a real bug: `foods_db.brand_name` was NULL for every food**, spotted by the user noticing it looked wrong. My first check was incomplete — I confirmed Health Connect genuinely has no brand column, then checked exactly one live-API `food` resource, found no `brand` field, and wrongly concluded the API doesn't expose it at all. Checking several more (branded/packaged items specifically) showed a real `brand` field does exist — it's just conditionally present, only for actual packaged/branded foods, not generic ones — confirmed against real values ("Lay's", "Food Lion", "BelGioioso", "Quest", "Mission", "Great Value", etc.). `scripts/sync-google-health.php` was already fetching the `food` resource for gram conversion but never reading this field.
- Fixed `fetchFoodServings()` to always surface `brand` when the food resource fetch succeeds, decoupled from whether a usable gram-conversion entry exists (previously the whole result collapsed to `null` if there was no `"gram"` serving entry, silently discarding brand info too). `findOrCreateFoodReal()`/`findOrCreateFoodFallback()` now match and store `brand_name` (via MySQL's `<=>` null-safe equality, since two foods sharing a name but differing only in brand — or one branded, one generic — are genuinely different catalog entries).
- Re-ran the sync against the real account: 50 of 689 catalog foods now have a real brand; re-ran a second time immediately to confirm full idempotency (0 created/updated, only reused/skipped).
- **Known limitation, not fixed**: `foods_db` rows created before this fix keep their incorrect `brand_name = NULL` — they aren't retroactively corrected (deletion isn't possible in this schema by design; a new, correctly-branded version was created instead going forward, matching how versioning already handles a genuine data difference). Old food_log_entries referencing the pre-fix rows still point at the less-complete version.

## V0.0.19 — 2026-09-08 16:00
### Changes
- Fixed `doc/wiki/Database-Design-Patterns.md`, which still documented fingerprint-based dedup and the `SRC`/`FIX`/`MOD` correction pattern as NutriPal's current approach — both were fully replaced this session (`api_uid`-only identity, versioning). Kept both original techniques as legitimate, still-generically-useful patterns (this doc is meant to be reusable across other projects), but added a "real-world postscript" to each explaining what NutriPal actually settled on instead and why, plus a new "Versioning" pattern section (previously undocumented here) with guidance on when to pick layered correction vs. versioning.

## V0.0.18 — 2026-09-08 15:30
### Changes
- Fixed `doc/wiki/Home.md`, which still said "development is being restarted from scratch" and "no app code exists yet" — badly stale given the finished schema, both importers, and the live sync. Rewrote the Status section to reflect reality and flag the actual next milestone (there's still no application/UI at all — that's the real gap now, not the database layer).

## V0.0.17 — 2026-09-08 15:00
### Changes
- Rewrote `sql/sample_data.sql`, which still reflected the pre-redesign schema (`food_log_nutrients`, `SRC`/`FIX`/`MOD`, `food_name`/`brand_name`/`energy_kcal` directly on `food_log_entries`). Now uses the current strict `food_id` + `serving_amount` reference model: 10 catalog `foods_db` entries plus one genuine version fork (a real recipe change to "Oatmeal with Banana," not just a different quantity), each with a named real-world custom unit (`foods_db_custom_units`) and a representative `foods_db_nutrients` subset — including a hand-entered `LEUCINE` value, demonstrating what a manually-tracked micronutrient looks like now that versioning replaced the `SRC`/`FIX`/`MOD` system. No longer re-seeds lookups already covered by `sql/init_lookups.sql` (would collide on duplicate keys) — only adds the two `lut_data_source` rows that file deliberately leaves empty.
- Verified by actually loading `sql/schema.sql` + `sql/init_lookups.sql` + `sql/sample_data.sql` in sequence into a throwaway database (`nutripal_sampletest`/`nutripal_sampletest_hist`) and querying the joined result before dropping it — not just reviewed for syntax.

## V0.0.16 — 2026-09-08 14:00
### Changes
- Built `scripts/sync-google-health.php`, the live Google Health API sync — the last major "not yet implemented" item. Covers all 9 categories (nutrition, steps, heart rate, HRV, daily resting heart rate, sleep, weight, height, exercise); `daily_resting_heart_rate` gets real data for the first time. Two modes: default incremental (last 7 days, matching `doc/wiki/Data-Sync.md`'s original design) or `--full`/`--days=N`.
- Two dedup strategies, chosen per category based on what the live API actually provides (confirmed against real responses, not assumed): `nutrition-log`/`sleep`/`exercise`/`weight`/`height` have a stable per-point ID → real upsert-if-changed via `api_uid`; `daily-resting-heart-rate` upserts via its existing `(user_id, reading_date)` natural key; `steps`/`heart-rate`/`heart-rate-variability` have **no** stable ID at all (confirmed: no `name` field on those dataPoints) and the schema's `BEFORE DELETE` trigger rules out a delete-and-reinsert reconcile, so these three use insert-missing dedup against existing `reading_time` values instead — disclosed as a real, deliberate scope reduction from "reconcile," not a silent gap.
- **Nutrition now gets real gram-accurate serving units for API-sourced foods**, closing the gap this session's Health Connect quantity-problem fix had to placeholder around: each entry's `food` resource reference is fetched (cached per run) and its `servings[]` list used to derive true grams for whatever unit was actually logged (verified end-to-end: "1 tortilla" resolved to exactly the ~51g computed by hand during the earlier comparison pass; "1 medium apple" → 167g, "1 oz" → 28g, "1 egg" → 50g — all real, not placeholders). Falls back to the same ratio-based placeholder-unit approach as `import-health-connect.php` when a food has no gram entry or the logged unit can't be matched.
- **Found and fixed a real schema precision bug via this sync**, not previously caught because Health Connect's exercise data has no distance column to populate at all: `exercise_sessions.distance` `DECIMAL(10,4)` overflows on ordinary walking distances once mixed with millimeter-scale values (a 6km walk = 6,148,000mm, exceeding the column's 6-integer-digit budget) — MySQL silently clamped every value to `999999.9999`, which also broke idempotency (the clamped stored value never matched the real incoming value, so every re-sync issued a pointless update). Root cause was really a unit mismatch — Takeout's miles and the API's millimeters share one column at wildly different scales. Fixed by standardizing `distance` to **meters** for every source at ingest time (added a `meter` row to `unit_conversions`) rather than widening the column — confirmed `DECIMAL(14,0)` and `DECIMAL(14,4)` cost the identical 7 bytes of storage (MySQL's DECIMAL packs by total digit count, not by where the decimal point falls), so widening would have bought nothing and still lost Takeout's fractional-mile precision.
- Found and fixed a second, smaller real bug: `lut_data_source.name` uses a case-insensitive collation, so the live API's `"FITBIT"` (from `dataSource.platform`) and Health Connect's already-imported `"Fitbit"` (an app display name) collided as duplicates at the DB level even though the in-memory PHP cache treated them as different strings — `findOrCreateDataSource()`/`findOrCreateActivityType()` now catch that specific duplicate-key error and re-resolve the existing row instead of crashing.
- Verified idempotency directly: ran the sync three times in a row against the same window and confirmed the third run reported `skipped` (no real change) for every single row across every category, with zero spurious updates, before running the real default 7-day sync against the live account.

### Known, disclosed limitations (not solved this pass)
- **Cross-source duplication risk between Health Connect and the live API is not resolved.** Health Connect's `api_uid` (its own local `uuid`) and this sync's `api_uid` (the live API's cloud dataPoint id) are different ID spaces for the same real-world sleep session / exercise session / weight reading / food log entry — the `UNIQUE(user_id, api_uid)` constraint can't detect they're the same event. Same class of problem as the already-documented "upsert priority across sources" open item, just newly live. No automated mitigation exists yet; picking a sync window that starts after the last Health Connect export's own coverage avoids it in practice for now.
- The real-gram custom units this sync creates are not retroactively used to correct Health-Connect-created placeholder units for what might be the same real food (comparing a true per-100g value against an HC placeholder scale is real, separate work) — tracked in the `google_health_api_food_data_quality` / `planned_custom_unit_correction_ui` memories, not attempted here.
- `--full` mode's logic was reviewed but not exercised against the real account's entire history this pass (would mostly re-cover what Health Connect's bulk import already has, and take a long time against years of heart-rate data) — only the default incremental path and small explicit `--days` windows were actually run.
- `lut_activity_type` mapping stays a plain find-or-create keyed on the API's raw `exerciseType` string (`API_WALKING` etc.), same non-canonical state as the Health Connect importer.

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
