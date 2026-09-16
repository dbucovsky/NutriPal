# GitHub Issues/Project Migration — DRAFT for review

This is a proposed list of every feature/fix/chore worth tracking as a GitHub
Issue in the [NutriPal project board](https://github.com/users/dbucovsky/projects/2),
extracted from `CHANGELOG.md` (V0.0.0 → V0.14.1), oldest first — matching the
order they'd be created/backdated in GitHub.

**How to review this:** each line is one proposed issue. `(type)` is the
suggested label. Nothing has been created in GitHub yet — this is purely a
review draft. Once you've edited/approved it, tell me and I'll create the
actual issues (backdated `created`/`closed` timestamps aren't settable via
the normal GitHub UI or API on real issues — see the note at the bottom on
how we can still get creation dates to line up).

A checkbox is unchecked by default; check off ones you want removed, or edit
titles/text directly, then hand it back.

---

## V0.0.0 — 2026-08-10 12:00
- [ ] **Initialize NutriPal git repository and project scaffolding** _(chore)_ — `.gitignore` (excludes local-only `doc/archive/`, `doc/credentials/`), initial `doc/wiki/Home.md`, `CHANGELOG.md`.

## V0.0.1 — 2026-08-10 13:00
- [ ] **Fix broken wiki auto-sync GitHub Actions workflow** _(fix)_ — Malformed push URL and un-interpolated `${{ github.repository }}` caused every wiki-sync run to fail; added explicit `contents: write` permission.

## V0.0.2 — 2026-08-10 14:00
- [ ] **Add README and scope the NutriPal rebuild** _(chore)_ — Google Health data viewer/analyzer with macro/activity/weight correlation, built incrementally.

## V0.0.3 — 2026-08-10 15:00
- [ ] **Decide tech stack: PHP/MySQL backend + React SPA, targeting Bluehost** _(chore)_ — Documented in `doc/wiki/Architecture.md`; expanded scope to custom meals + fast repeat-meal logging.

## V0.0.4 — 2026-08-10 16:00
- [ ] **Scope first milestone: Google Health food-data sync only** _(chore)_ — Documented incremental (7-day) + manual full-resync strategy in `doc/wiki/Data-Sync.md`.

## V0.0.5 — 2026-08-10 17:00
- [ ] **Implement Google Health OAuth flow (login/callback, token storage)** _(feature)_ — `auth-login.php`/`auth-callback.php`, temporary JSON token store, dependency-free `.env` loader.

## V0.0.6 — 2026-08-10 18:00
- [ ] **Create Web-application OAuth client and complete first live Google login** _(feature)_ — Replaced the unusable Desktop-app client; verified full consent→callback→token exchange against real Google login.

## V0.0.7 — 2026-08-10 19:00
- [ ] **Add local dev server start/stop scripts** _(chore)_ — `start-services`/`stop-services` `.bat`/`.ps1` for the PHP dev server.

## V0.0.8 — 2026-08-10 20:00
- [ ] **Explore live Google Health nutrition-log API** _(chore)_ — `fetch-nutrition-test.php`; discovered `filter` param rejected for `nutritionLog`, worked around via client-side filtering; documented response shape.

## V0.0.9 — 2026-09-05 12:00
- [ ] **Expand OAuth scope and survey available Google Health data types** _(chore)_ — `fetch-metrics-test.php` surveyed 18 candidate data types; found real data for steps/exercise/heart-rate/HRV/resting-HR/sleep/weight/height.

## V0.0.10 — 2026-09-06 14:00
- [ ] **Decide to support Google Takeout as a second ingestion source** _(chore)_ — Surveyed Takeout export format across 6 categories.
- [ ] **Design core schema patterns: lookup tables, audit history, SRC/FIX/MOD nutrient correction, multi-user readiness, `foods_db` catalog** _(feature)_ — First full `sql/schema.sql`/`sql/sample_data.sql` checkpoint; new `doc/wiki/Database-Design-Patterns.md`.

## V0.0.11 — 2026-09-06 15:00
- [ ] **Design `food_log_entries` ↔ `foods_db` linkage** _(feature)_ — Nullable `food_id` FK; `last_serving_amount`/`last_serving_unit_id` on `foods_db_last_used`.
- [ ] **Split schema into `nutripal` + `nutripal_hist` databases** _(chore)_ — Independent backup/archive cadence for audit history; documented the Bluehost `theshaf2_` prefix deploy caveat.

## V0.0.12 — 2026-09-06 16:00
- [ ] **Verify schema end-to-end against a throwaway database** _(chore)_ — Triggers, FK enforcement, cross-schema history insert.
- [ ] **Fix missing `DEFAULT CURRENT_TIMESTAMP` on `_hist` table timestamp columns** _(fix)_ — Would have blocked schema creation entirely under this MariaDB config on first real use.

## V0.0.13 — 2026-09-07 22:00
- [ ] **Complete table-by-table schema review for remaining health-data tables** _(feature)_ — steps, heart rate, measurements, exercise, sleep/sleep stages, grounded in real API/Takeout data.
- [ ] **Discover and model heart-rate-variability, daily-resting-heart-rate, recording-method, and activity-type concepts** _(feature)_ — New tables/lookups found via real data, not originally modeled.
- [ ] **Merge weight/height into a generic `measurements` table** _(feature)_ — Extensible to future body metrics (blood pressure, body fat %) with no new tables.
- [ ] **Fix sleep-score column type** _(fix)_ — `TINYINT UNSIGNED` couldn't hold real float values or the `-1` "not computed" sentinel.
- [ ] **Add missing dedup mechanism for `sleep_stages`** _(fix)_ — API-sourced stages had no dedup mechanism at all.
- [ ] **Remove redundant `exercise_sessions.device_name` column** _(chore)_.
- [ ] **Fix free-text `exercise_sessions.distance_unit`** _(fix)_ — Converted to FK-backed `distance_unit_id`.
- [ ] **Link `food_log_entries` to `foods_db` and cache last-used serving** _(feature)_.
- [ ] **Correct stale Takeout export documentation** _(docs)_ — Corrected file-split assumptions; discovered a legacy Fitbit sleep export and other unreviewed sleep-adjacent files.

## V0.0.14 — 2026-09-08 10:00
- [ ] **Create real `nutripal`/`nutripal_hist` databases and lookup-seed script** _(chore)_ — `sql/init_lookups.sql`, `src/Database.php`, DB env vars.
- [ ] **Build and run the Takeout importer against a real ~3-year export (~12.1M rows)** _(feature)_ — `scripts/import-takeout.php`; fixed missing meal-type/sleep-stage lookups and an `N/A`-nutrition-sentinel casting bug.
- [ ] **Decide to drop Google Takeout as an active source in favor of Health Connect + the live API** _(chore)_.
- [ ] **Redesign `food_log_entries`/`foods_db` to a strict reference + versioning model** _(feature)_ — Dropped SRC/FIX/MOD and `fingerprint`; moved provenance fields onto the log table.
- [ ] **Rewrite `sql/schema.sql` for the redesigned model and verify via a throwaway database** _(chore)_.
- [ ] **Build the Health Connect importer (78-table SQLite export)** _(feature)_ — `scripts/import-health-connect.php`; fixed a `fetch()` false-vs-null bug and a SQLSTATE-class-vs-code bug that was silently zeroing out `food_log_entries`.
- [ ] **Fix the "quantity problem" for Health Connect nutrition data** _(fix)_ — Ratio-based version matching + a placeholder "reported serving" custom unit, replacing broken tolerance-based matching (was producing 41 duplicate "Yellow Onion" versions).
- [ ] **Full real-data Health Connect import as schema validation** _(chore)_ — 12.1M+ rows across every category, zero errors.

## V0.0.15 — 2026-09-08 12:00
- [ ] **Cross-check Health Connect data against the live Google Health API** _(chore)_ — `fetch-recent-compare.php`; confirmed day-bucketing needs local-civil-date alignment; found one genuine weight-reading discrepancy.
- [ ] **Discover the live API's nutrition-log data already has real serving units (no "quantity problem")** _(chore)_ — Recorded as a project memory shaping the eventual placeholder-unit reconciliation fix.

## V0.0.16 — 2026-09-08 14:00
- [ ] **Build the live Google Health API sync script** _(feature)_ — `scripts/sync-google-health.php`, all 9 categories, incremental (7-day) + `--full`/`--days=N` modes, per-category dedup strategy.
- [ ] **Add real gram-accurate serving units for API-sourced nutrition entries** _(feature)_.
- [ ] **Fix `exercise_sessions.distance` overflow/unit-mismatch bug** _(fix)_ — Standardized distance to meters at ingest; MySQL was silently clamping large millimeter values to `999999.9999`.
- [ ] **Fix case-insensitive data-source-name collision crash** _(fix)_ — `"FITBIT"` vs `"Fitbit"` collided at the DB level despite differing in the in-memory cache.
- [ ] **Verify sync idempotency against real account data** _(chore)_ — Three consecutive runs, zero spurious updates.

## V0.0.17 — 2026-09-08 15:00
- [ ] **Rewrite `sql/sample_data.sql` for the redesigned schema** _(docs)_ — Verified by loading into a throwaway database.

## V0.0.18 — 2026-09-08 15:30
- [ ] **Fix stale `doc/wiki/Home.md` status section** _(docs)_ — Still said "no app code exists yet."

## V0.0.19 — 2026-09-08 16:00
- [ ] **Fix stale `Database-Design-Patterns.md`** _(docs)_ — Still described the replaced fingerprint/SRC-FIX-MOD approach; added a "Versioning" pattern section.

## V0.0.20 — 2026-09-08 16:30
- [ ] **Fix missing `brand_name` on synced foods** _(fix)_ — Live API does expose a conditional `brand` field for packaged foods; sync was never reading it.

## V0.0.21 — 2026-09-08 16:45
- [ ] **Fix stale `README.md`** _(docs)_ — Still said "no application code exists yet."

## V0.1.0 — 2026-09-08 17:30
- [ ] **Build the first frontend screen: Food log** _(feature)_ — Vite + React scaffold, day view with meal grouping, real serving labels, `food-log.php` API.
- [ ] **Add placeholder (no-security) login** _(feature)_ — `login.php`, `Login.jsx`, localStorage session.
- [ ] **Fix missing `APP_TIMEZONE` in local `.env`** _(fix)_ — Local-day bucketing was silently falling back to UTC.

## V0.1.1 — 2026-09-08 18:15
- [ ] **Add Heart Rate, Sleep, and Exercise pages** _(feature)_ — New endpoints + shared `src/LocalDay.php`; tab switcher in `App.jsx`.
- [ ] **Add shared date-nav component** _(feature)_ — `DateNav.jsx`, `dateUtils.js`.

## V0.1.2 — 2026-09-08 18:45
- [ ] **Overlay sleep/exercise periods on the Heart Rate chart** _(feature)_ — Shaded background bands via `chartjs-plugin-annotation`; switched the chart x-axis to a linear minutes-since-midnight scale.

## V0.1.3 — 2026-09-08 19:15
- [ ] **Lift date state up to `App.jsx` (shared across tabs)** _(feature)_.
- [ ] **Add a real native date picker** _(feature)_ — Replaced prev/next-only arrows.
- [ ] **Fix sleep stages grouped instead of shown chronologically** _(fix)_ — `GROUP BY stage_type` was collapsing a real night's stage sequence into 4 blocks.

## V0.1.4 — 2026-09-08 23:30
- [ ] **Add API request/response logging for the sync script** _(feature)_ — `storage/api-logs/<run_id>/`, `manifest.json`; auth headers deliberately excluded.
- [ ] **Add `--replay=<run_id>` mode** _(feature)_ — Re-runs ingestion against recorded logs instead of the network.
- [ ] **Add `--debug` trace flag** _(feature)_.

## V0.1.5 — 2026-09-09 04:00
- [ ] **Add Sync tab UI (live/replay/import controls)** _(feature)_ — `run-sync.php`, `sync-runs.php`, `import-hc.php`; path-based (not upload-based) Health Connect import.
- [ ] **Fix duplicated heart-rate readings on repeat Health Connect import** _(fix)_ — Missing per-sample id made `UNIQUE(user_id, api_uid)` a no-op; 5.7M rows found exactly 2x duplicated; added real `UNIQUE(user_id, reading_time)`.
- [ ] **Fix sleep stages silently dropped (not deduped) on re-import** _(fix)_.
- [ ] **Fix `--full` sync crash from the new heart-rate uniqueness constraint** _(fix)_ — Switched to `INSERT IGNORE`.
- [ ] **Add a richer replay-run picker (window, duration, timestamp)** _(feature)_.
- [ ] **Add rough sync progress feedback (elapsed timer + last-run estimate)** _(feature)_ — Worked around the PHP dev server's single-threaded polling limitation.
- [ ] **Fix the same duplication bug in `steps_readings` and `heart_rate_variability_readings`** _(fix)_ — Found after an unexplained `--full` sync duplicated ~138k steps rows.

## V0.1.6 — 2026-09-09 16:00
- [ ] **Fix cross-source duplication for `sleep_sessions`, `exercise_sessions`, and `measurements`** _(fix)_ — New natural-key constraints + cross-source-aware upsert logic (`upsertByNaturalKey()`).
- [ ] **Fix `sleep_stages` insert crash from natural-key drift** _(fix)_ — Switched to `INSERT IGNORE`.

## V0.1.7 — 2026-09-09 19:30
- [ ] **Fix cross-source dedup silently dropping complementary exercise data** _(fix)_ — Skip-on-match was discarding calories/distance/steps/avg-HR that only one source had; now merges.
- [ ] **Map Health Connect numeric exercise-type codes to readable names** _(fix)_ — Covers 1,992 of 2,014 real sessions.

## V0.1.8 — 2026-09-09 20:00
- [ ] **Map remaining Health Connect exercise-type codes (58, 11)** _(fix)_ — Closes out the `HC_<code>` label gap entirely.

## V0.1.9 — 2026-09-09 21:45
- [ ] **Fix `food_log_entries` cross-source duplication (the last unresolved category)** _(fix)_ — Root cause: placeholder-unit vs. real-gram foods never converged to the same `food_id`; added `reconcilePlaceholderIntoReal()`.
- [ ] **Fix nutrition sync ignoring the entry's own reported serving unit** _(fix)_ — Was defaulting to a nonexistent field, causing major gram-conversion errors (e.g. milk logged ~8x under-scaled).
- [ ] **Fix brand-matching gap blocking branded/unbranded reconciliation** _(fix)_.
- [ ] **Add cross-source natural-key upsert for `food_log_entries`** _(feature)_.

## V0.1.10 — 2026-09-09 22:15
- [ ] **Fix technical/unreadable serving-unit labels in the food log UI** _(fix)_ — e.g. "2.84 api_951_gram" → "2.84 gram".

## V0.2.0 — 2026-09-09 23:30
- [ ] **Add prev/next date-nav arrows stepping by the current view's period** _(feature)_.
- [ ] **Add multi-day views (Day/Week/Month/Year/Custom) for Food, Sleep, Exercise** _(feature)_.
- [ ] **Add collapsible per-day (and per-meal) sections** _(feature)_ — `MultiDay.jsx`.
- [ ] **Add new Weight page** _(feature)_.
- [ ] **Standardize sleep duration display as H:MM everywhere** _(feature)_.
- [ ] **Show each sleep stage segment's own start timestamp** _(feature)_.
- [ ] **Add REM/Deep sleep quality badges** _(feature)_.

## V0.3.0 — 2026-09-09 23:50
- [ ] **Add a Weight trend line chart** _(feature)_.

## V0.4.0 — 2026-09-10 00:40
- [ ] **Add Day/Week/Month/Year/Custom views to Heart Rate** _(feature)_.
- [ ] **Show aggregated details on every collapsible day/meal summary line** _(feature)_ — Also fixed a `<summary>` flex-layout regression that hid the native disclosure triangle.
- [ ] **Fix severe Heart Rate Year-view query performance (~14.5s)** _(fix)_ — A JOIN-based attempt made it worse (2+ min); replaced with a UNION ALL of per-day aggregate subqueries (~11s).

## V0.5.0 — 2026-09-10 01:15
- [ ] **Add new Steps page** _(feature)_.
- [ ] **Work around steps cross-source double/triple-counting** _(fix)_ — Disclosed heuristic: use whichever single data source reported the most steps that day.

## V0.6.0 — 2026-09-10 02:15
- [ ] **Add hierarchical Year→Quarter→Month→Week→Day collapsing across all multi-day pages** _(feature)_.
- [ ] **Add a per-session heart-rate popup chart for exercise sessions** _(feature)_ — `heart-rate-range.php`; also added to the Heart Rate page's own exercise-period overlays.
- [ ] **Add a fixed-width tabular macro grid for Food (kcal/P/C/F)** _(feature)_.
- [ ] **Add a per-day macro breakdown pie chart** _(feature)_.

## V0.7.0 — 2026-09-10 03:00
- [ ] **Add a top-ribbon dropdown menu (Log out/Settings/Help/Sync/About)** _(feature)_ — Replaces the standalone Sync tab and Log out button.
- [ ] **Add a one-click Quick Sync icon** _(feature)_.
- [ ] **Add an About popup showing the real current version** _(feature)_ — `version.php`, parsed from `CHANGELOG.md`.

## V0.8.0 — 2026-09-10 05:30
- [ ] **Food tab overhaul: dedicated tree renderer, snack sub-buckets, quick-collapse toolbar** _(feature)_ — Early/Morning/Afternoon/Late-Night snack splitting, real week-of-year numbers, color-coded macro thresholds.
- [ ] **Fix Food Year-view rendering performance** _(fix)_ — Collapsed `<details>` was still mounting every child into the DOM.
- [ ] **Fix macro-grid text wrapping on new top-level summary lines** _(fix)_.

## V0.9.0 — 2026-09-10 07:15
- [ ] **Heart Rate tab: dedicated tree renderer with real group averages and drill-down bar charts** _(feature)_.
- [ ] **Fix fixed-column-grid text-wrapping bug (shared CSS fix)** _(fix)_.

## V0.10.0 — 2026-09-10 08:30
- [ ] **Sleep tab: same hierarchy treatment as Food/Heart Rate** _(feature)_.
- [ ] **Extract shared `RangeTree.jsx`/`QuickToolbar.jsx` components** _(chore)_ — De-duplicates Food/Heart Rate/Sleep tree & toolbar code.
- [ ] **Move per-stage-segment detail into hover tooltips** _(feature)_ — Removes a long 20-40-line list under each sleep session.
- [ ] **Move REM/Deep quality badge onto totals/averages lines** _(feature)_.

## V0.11.0 — 2026-09-10 22:30
- [ ] **Exercise tab: same hierarchy treatment, with 5-zone HR-training coloring** _(feature)_.
- [ ] **Add a real Settings panel (birth date, gender, Max HR)** _(feature)_ — Max HR stored as full history, not a mutable field; guards against nonsensical birth dates.
- [ ] **Rename "Food" tab to "Nutrition"** _(chore)_.
- [ ] **Fix meal ordering (chronological, not core-meals-first)** _(fix)_.
- [ ] **Fix indentation bug on nested day/meal sections** _(fix)_.
- [ ] **Default all hierarchy views to fully collapsed** _(chore)_.
- [ ] **Add an on-demand "Show chart for this day" button for Heart Rate Month/Year/long-Custom views** _(feature)_.

## V0.12.0 — 2026-09-10 22:30
- [ ] **Add a third Max HR source: observed from real exercise sessions** _(feature)_ — Rolling-median sustained-peak bpm over a trailing 3-week window.
- [ ] **Make Max HR source a user preference instead of an automatic priority order** _(feature)_.
- [ ] **Add HR-zone background bands to per-session bpm-curve popups** _(feature)_.
- [ ] **Fix Exercise zone badges using today's Max HR instead of the date-in-effect value** _(fix)_.
- [ ] **Fix observed Max HR trusting a single raw sensor spike as "the peak"** _(fix)_ — Switched to rolling-median peak detection.
- [ ] **Add a Help submenu with a dedicated FAQ page** _(feature)_.

## V0.13.0 — 2026-09-11 00:00
- [ ] **Steps: trust Fitbit as preferred source, fall back to Phone only on demonstrable tracking failure** _(feature)_ — Replaces "pick whichever source reported most" with a per-10-minute-window rule.
- [ ] **Steps tab: same hierarchy treatment as other tabs, plus a per-day hourly chart** _(feature)_.
- [ ] **Add a configurable daily step goal with 3-tier badges** _(feature)_.
- [ ] **Show missing days as real 0-step entries instead of silently skipping them** _(fix)_.
- [ ] **Move the Fitbit/Phone reconciliation explanation into a new FAQ entry** _(docs)_.
- [ ] **Group FAQ into collapsible per-tab sections** _(feature)_.
- [ ] **Weight tab: same hierarchy treatment as other tabs** _(feature)_.
- [ ] **Delete unused `MultiDay.jsx`** _(chore)_ — Superseded by per-tab tree renderers.

## V0.14.0 — 2026-09-11 14:15
- [ ] **Track login attempts and last-sync-completion in the database** _(feature)_.
- [ ] **Add a `--quick` sync mode anchored on last-sync-completed timestamp** _(feature)_ — Replaces the old flat "always last 7 days" Quick Sync behavior; wider 7-day margin on first sync after login.
- [ ] **Fix `--replay` of a `--quick` run to restore its exact original windows** _(fix)_.

## V0.14.1 — 2026-09-11 16:30
- [ ] **Fix nutrition sync silently corrupting displayed kcal on ratio-matched foods** _(fix)_ — Was reusing a food's current default unit instead of its own "reported serving" unit.
- [ ] **Fix food-version candidate matching picking the first internally-consistent version instead of the best-fitting one** _(fix)_.
- [ ] **Full historical nutrition rebuild applying both fixes above** _(chore)_ — Drop/recreate sync-derived tables, re-import + replay all 31 recorded sync runs.
- [ ] **Fix nutrition sync ignoring the entry's own reported unit name (major, separate bug)** _(fix)_ — Hardcoded `'serving'` default caused chicken/honey/cottage-cheese/etc. to fall through to the ratio-based fallback path entirely.
- [ ] **Fix `--replay` mode exhausting PHP's memory limit on large recorded runs** _(fix)_ — `ReplayReader` now streams line-by-line instead of loading a whole `.jsonl` file into memory.
- [ ] **Fix Google food catalog's "gramme" (British/French) spelling not being recognized** _(fix)_.
- [ ] **Fix a day with no dinner yet mislabeling every afternoon/evening snack as late-night** _(fix)_.
- [ ] **Add frontend (Vite) dev-server startup/shutdown to start-services/stop-services scripts** _(chore)_ — `localhost:8080` alone only ever showed the bare backend bootstrap page.
- [ ] **Detect expired/revoked Google OAuth token and offer a one-click reconnect in the Sync UI** _(feature)_ — Replaces a raw PHP fatal-error dump with a plain-language message + reconnect link.

---

## Open / backlog issues (not yet resolved as of V0.14.1)

These were raised somewhere in the history above but are still open today —
best-effort traced by reading every "Known bugs"/"Known limitations"/"Planned"
section and checking whether a later version actually closed it. Flag any of
these I've mis-tracked.

- [ ] **Build a UI to review/correct placeholder "reported serving" units per-food** _(feature)_ — First raised V0.0.14 (2026-09-08); restated as recently as V0.14.1's known limitations. Would let a user fix eggs→"1 egg", cottage cheese→"1 cup", etc. directly, and would have caught the V0.14.1 kcal-corruption bug sooner.
- [ ] **Build canonical `lut_activity_type` mapping across Health Connect and live-API vocabularies** _(feature)_ — Raised V0.0.10/V0.0.14; explicitly still an open item as of V0.1.7 ("a real, larger effort... not attempted here").
- [ ] **Reconcile steps cross-source duplication properly (not just pick-a-winner heuristic)** _(bug)_ — Raised V0.5.0; V0.13.0 improved the heuristic (Fitbit-preferred) but explicitly says "still a disclosed heuristic, not a full reconciliation."
- [ ] **Add a precomputed daily-rollup table for Heart Rate Year-view performance** _(chore)_ — Raised V0.4.0 as the real fix beyond the ~11s UNION-ALL workaround; not built.
- [ ] **Fix "Expand all" Year-view performance across Food/Heart Rate/Sleep** _(bug)_ — Raised V0.8.0/V0.9.0/V0.10.0; each page's collapsed-by-default rendering is fast, only the explicit full-expand action is heavy; no fix landed for any of the three.
- [ ] **Support real multi-user sync (script hardcodes `$userId = 2`)** _(chore)_ — Raised V0.14.0; `login_attempts`/`last_sync_completed_at` are already per-user, but the sync script itself isn't parameterized yet.
- [ ] **Build a "recipe" template feature** _(feature)_ — Raised V0.0.14; food log entries still stay ingredient-level only.
- [ ] **Build meal planning (logging an intended future meal)** _(feature)_ — Raised V0.0.10/V0.0.11/V0.0.13; not built.
- [ ] **Fix Feb-29 birth-date edge case in Max HR age calculation** _(bug, minor)_ — Raised V0.11.0; rolls to Mar 1 in a non-leap year.
- [ ] **Map "Aerobics" to an exact `lut_activity_type` row** _(bug, minor)_ — Raised V0.12.0; currently falls under the closest-match "Exercise Class".
- [ ] **Investigate 172 residual cross-source `food_log_entries` pairs with no real-gram data on either side** _(bug)_ — Raised V0.1.9; left unreconciled rather than guessed.
- [ ] **Investigate 14 `food_log_entries` rows sharing the same natural key more than once** _(bug, low priority)_ — Raised V0.1.9; may be genuine same-instant double-logging, not a bug.
- [ ] **Build production build/deploy pipeline (Vite `dist/` → Bluehost)** _(chore)_ — Raised V0.14.1 (this session).
- [ ] **(Won't fix / accepted limitation) Liquid foods with no gram/gramme conversion default to "reported serving"** _(limitation)_ — Raised V0.14.1; fixing would require assuming a density, deliberately rejected as unsafe for oils/syrups.
- [ ] **(Won't fix / accepted limitation) English/French unit-name mismatch within a single food's catalog entry (oz vs. once)** _(limitation)_ — Raised V0.14.1; one confirmed case isn't enough to safely build a language-alias table.

Items I traced as **already resolved** by a later version and so **excluded**
above (listed here so you can double-check my reasoning): stale
`sql/sample_data.sql` (fixed V0.0.17), cross-source duplication for sleep
sessions/exercise sessions/weight (fixed V0.1.6), `food_log_entries`
cross-source duplication (fixed V0.1.9), Health-Connect exercise sessions
missing calories/distance/steps/avg-HR (mitigated via cross-source merge in
V0.1.7 — still `NULL` for a HC-only session with no live-API counterpart,
which arguably belongs back on the open list; your call), the
`daily_resting_heart_rate` multiple-per-day question (effectively answered
by V0.0.16's natural-key upsert), and the unexplained one-off `--full` sync
duplication incident from V0.1.5 (mitigated by the uniqueness constraints
added in the same version, even though the trigger was never root-caused).

---

## Next steps once you've reviewed this

1. **Trim/edit** the list above (delete rows, merge/split, fix titles).
2. **Create the GitHub issues.** Caveat: GitHub's API does not allow setting
   an issue's `created_at`/`closed_at` to an arbitrary past date on a normal
   personal repo (that's only possible via GitHub's bulk *migrations* API,
   which needs an organization, not a personal account). So "backdated" in
   practice means one of:
   - Create every issue for real today, close the completed ones today, and
     put the real historical date in the issue **title or body** (e.g. "shipped
     in V0.3.0, 2026-09-09") instead of the system timestamp — simplest, and
     what I'd recommend.
   - Or, only if you want the timestamps themselves to look historical: I can
     script it via `git commit --date`-style trick isn't applicable to issues,
     but a repo owner *can* backdate by temporarily changing your local
     system clock before each `gh issue create` call — this is hacky, easy to
     get wrong, and not something I'd do without you explicitly asking for it.
   Let me know which you want before I create anything.
3. Once created, I'll add each issue to the
   [project board](https://github.com/users/dbucovsky/projects/2) and set
   status (Done for shipped items, Backlog/Todo for the open list).
4. Then I'll go back through `CHANGELOG.md` and `README.md` in one new commit
   and reference each entry's issue number (e.g. "Fixed: ... (#42)"), without
   rewriting any past commits — only the current file content changes.
