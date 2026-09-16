# Changelog

## V0.14.1 — 2026-09-11 16:30
### Changes
- **Fix nutrition sync silently corrupting displayed kcal on ratio-matched foods** (#128)
  - `findOrCreateFoodFallback()`'s existing-match branch computed a `serving_amount` that's only valid against a unit whose `equivalent_amount` is exactly 100 (the "reported serving" convention every fallback-created food gets) - but it reused whichever unit that food already defaulted to, which could be a **real** unit (e.g. an "oz"-established chicken breast defaults to `equivalent_amount=28`) left over from an earlier real-gram match. Reported case: today's breakfast showed 412 kcal short of Google's correct 415 - chicken (160 kcal) displayed as ~45, honey (20 kcal) similarly squashed. Fixed by always pointing the ratio-matched entry at that food's own `reported serving` unit (found-or-created via the existing `getOrCreateCustomUnit()` helper) instead of its current default.
- **Fix food-version candidate matching picking the first internally-consistent version instead of the best-fitting one** (#129)
  - The same function checks each existing version of a food (newest first) and used to stop at the first whose energy/protein/carb/fat ratios agreed with each other within 15% - but two versions can both pass that check while one is a clearly worse fit (confirmed real case: "Fat Free Cottage Cheese, Small Curd" v2 has no stored fat value, so its energy ratio disagreeing with protein/carb by ~13% still slipped under the 15% band checked against only 3 values; v1 agreed to within ~5%). Now evaluates every version and keeps the one with the tightest internal agreement.
- **Full historical nutrition rebuild applying both fixes above** (#130)
  - A first pass (44 entries, all of user 2's live-API nutrition rows differing from Google's own recorded values by >10%) reused each row's existing `serving_amount` and only swapped the unit, which correctly fixed 40 rows but made 2 "Tomato, Red, Ripe, Raw" rows dramatically worse (a pre-existing, unrelated `serving_amount` corruption - traced to an old real-gram/placeholder-reconciliation event - got multiplied by the same 100x unit correction) and left 2 "Fat Free Cottage Cheese" rows still ~13-14% off (the version-selection bug above). A second pass instead fully recomputes both the matched food version *and* `serving_amount` from Google's own recorded macros for every currently-mismatched row, rather than reusing stored values.
  - Applied both fixes above to *all* historical data, not just the previously-flagged 44 rows (the unit-label bug affects far more entries than the original kcal-mismatch audit alone would have caught, since a fallback-matched entry can still land within the 10% tolerance by coincidence). Following this project's established drop-and-rebuild ritual, but scoped to only the sync-derived tables this time (`foods_db`, `food_log_entries`, and every `*_readings`/`sessions`/`measurements` table) rather than the whole schema - a true `DROP DATABASE` would also have erased `login_attempts`, `faq_entries`, and user settings that didn't exist the last time this ritual ran and aren't recoverable from the Health Connect export or sync replay. Since every one of those tables enforces delete-at-the-DB-level blocking (`trg_<table>_bd`, same as everywhere else in this schema), "reset" meant `DROP TABLE`/recreate from the live schema's own DDL (captured via `mysqldump --no-data --triggers` per table, in FK-dependency order) rather than `DELETE`/`TRUNCATE` - a full `mysqldump` backup of both databases was taken first regardless. Rebuilt via: reimport the Health Connect export, then `--replay` every one of the 31 recorded live-sync runs in their original chronological order (network-independent, and each run's real transient API hiccups from that day - several genuine HTTP 500/503/401 responses - replay faithfully rather than needing to be worked around). Re-running the full audit afterward against all 4,504 live-API entries with a matching raw log record: zero flagged.
- **Fix nutrition sync ignoring the entry's own reported unit name (major, separate bug)** (#131)
  - `$unitLabel` was hardcoded to default to the literal string `'serving'`, resolved to something real only via a `foodMeasurementUnit` dataPoint *reference* lookup - but most real entries also carry a plain `foodMeasurementUnitDisplayName` (confirmed real examples: "tsp", "cup", "oz", "medium", "tbsp") that was never even looked at. Reported case: a banana logged as "1 medium" displayed as "1 serving" (scaled to the food's generic serving weight, not a medium banana's); chicken/honey/cottage cheese/almondmilk/BBQ sauce logged in oz/tsp/tbsp/cup fell through to the ratio-based fallback path entirely, because none of those foods even have a "serving" entry in their own gram-conversion table - the real one they were actually reported in was sitting right there in the API response. Fixed by preferring the entry's own reported display name, falling back to the reference-based lookup only when no plain name is given (confirmed still needed for some entries, e.g. "Tomato, Red, Ripe, Raw").
- **Fix `--replay` mode exhausting PHP's memory limit on large recorded runs** (#132)
  - `ReplayReader` loaded an entire recorded `.jsonl` file into memory via `file()` before replaying it, and never freed earlier categories' data within the same run - a single `--full` run's `heart-rate.jsonl` reached 885MB on this account, and a replay needs several categories' logs in memory at once. Rewritten to stream one line at a time from an open file handle instead.
- **Fix Google food catalog's "gramme" (British/French) spelling not being recognized** (#133)
  - `fetchFoodServings()`'s gram-pivot detection only recognized the literal string `"gram"`, so any food whose catalog entry used "gramme" instead (confirmed real case: "Fat Free Cottage Cheese") had no way to resolve *any* of its real units and fell through to the ratio-based fallback path even though a perfectly good conversion was sitting right there. Fixed by accepting both spellings. Applied to history with a targeted re-fix (not another full rebuild, given the cost of the last one) that found every fallback-matched entry whose food now resolves via real-gram matching thanks to this fix and re-derived just those rows: 23 entries across "White Rice", "Pinto Beans", "Grilled Chicken", and "Tomato Ketchup, No Sugar Added".
- **Fix a day with no dinner yet mislabeling every afternoon/evening snack as late-night** (#134)
  - The snack-bucketing cascade compared a non-core-meal entry's timestamp against that day's own Breakfast/Lunch/Dinner reference times, but its final `else` unconditionally meant `LATE_NIGHT_SNACK` whenever no dinner reference existed for the day at all (the ordinary case before dinner has been logged yet) - reported case: lunch at 17:58, a 18:20 snack showed as "Late Night Snack" instead of "Afternoon Snack". The same missing-dinner-reference gap also meant a dinner logged just after midnight (still bucketed into that local day under this app's midnight-to-midnight boundary, but timestamped before that day's breakfast/lunch) would have broken the cascade the same way. Fixed by only treating a dinner reference as valid for the cascade when it's actually later in the day than breakfast/lunch, defaulting to `AFTERNOON_SNACK` rather than `LATE_NIGHT_SNACK` whenever there's no valid one to compare against.
- **Add frontend (Vite) dev-server startup/shutdown to start-services/stop-services scripts** (#135)
  - Previously only started the PHP backend (port 8080), leaving the real React app (`frontend/`, Vite on port 5173) unstarted - visiting `localhost:8080` alone only ever showed the bare backend bootstrap page. Start now also launches `npm run dev` in `frontend/` (skipped if port 5173 is already listening); stop now also kills whatever's on port 5173.
- **Detect expired/revoked Google OAuth token and offer a one-click reconnect in the Sync UI** (#136)
  - `scripts/sync-google-health.php` refreshing an expired/revoked Google refresh token (`invalid_grant` from Google - expected periodically while the OAuth consent screen is in Testing status, which auto-expires refresh tokens after ~7 days) previously crashed with an uncaught exception. `src/GoogleOAuth.php` now throws a dedicated `GoogleAuthExpiredException` for this specific case; the sync script catches it and exits with a distinct code (3); `public/api/run-sync.php` surfaces that as `authExpired: true`; the Sync page and the Quick Sync button both now show a plain-language explanation and a **Reconnect Google Health** link straight to `/auth-login.php` (proxied through Vite's dev server) instead of the stack trace.

### Planned (not yet implemented)
- **Build production build/deploy pipeline (Vite `dist/` → Bluehost)** (#149)
  - Local dev runs the React app unbuilt via `vite dev` (frontend/, port 5173, proxying `/api` to the PHP backend on :8080 - see `start-services.ps1`); Bluehost shared hosting won't run that dev server, so production needs `npm run build` (in `frontend/`) and the resulting `frontend/dist/` output deployed alongside the PHP backend instead.

### Known limitations (not addressed this pass)
- The two placeholder `foods_db` rows the Tomato entries used to point at (a stale real-gram match and an inconsistent earlier version) are now permanently unreferenced but can't be deleted (`trg_foods_db_bd` forbids it, like every table in this schema) - harmless, matches this codebase's existing precedent for orphaned placeholder rows.
- **Build a UI to review/correct placeholder "reported serving" units per-food** (#137)
  - Previously discussed, not yet built - would have caught this class of bug sooner than a from-scratch API-log audit.
- **(Won't fix / accepted limitation) Liquid foods with no gram/gramme conversion default to "reported serving"** (#150)
  - Confirmed real examples: "Tomato Basil Sauce", "Original Unsweetened Almondmilk", "Marinade, Teriyaki". Their Google food resource only offers volume-based conversions (ml/fl oz/cup, or nothing at all) with no gram pivot - resolving these would require assuming a density (e.g. 1mL ≈ 1g), which the user deliberately chose not to do, since it would be wrong for oils/syrups/thick liquids. Kcal display is already correct either way.
- **(Won't fix / accepted limitation) English/French unit-name mismatch within a single food's catalog entry (oz vs. once)** (#151)
  - Real case: a "Fat Free Cottage Cheese" entry reports its unit as "oz", but that food's own serving list only defines the French "once"/"onces liquides" for the same physical unit - the English label the entry itself uses isn't present to match against. Fixing this would need a language-alias table (oz↔once, tsp↔cuillère à café, etc.); deliberately not built, since one confirmed case doesn't reveal how many others like it exist in the catalog, and a wrong alias would be worse than the honest fallback already in place.

## V0.14.0 — 2026-09-11 14:15
### Changes
- **Track login attempts and last-sync-completion in the database** (#125)
  - `login_attempts` records every login attempt (success and failure, matched user if any) - append-only, like `max_heart_rate_history`, since nothing here is ever corrected in place. `users.last_sync_completed_at` is set after every successful **live** sync (not `--replay`, which doesn't fetch anything new).
- **Add a `--quick` sync mode anchored on last-sync-completed timestamp** (#126)
  - Now what the Quick Sync button actually runs (`mode: 'quick'`), replacing the old flat "last 7 days, every single click" behavior. Windows are anchored on `users.last_sync_completed_at` instead of "now": nutrition and weight get a 4-day lookback (people log meals/weigh-ins after the fact more often than they miss a day of passively-sensed data), everything else (sleep, exercise, steps, heart rate, HRV, resting HR) gets 4 hours. The **first** quick sync after a login instead gets a 7-day margin on both, in case the app sat closed for a while - detected by comparing `last_sync_completed_at` against the user's most recent successful `login_attempts` row, not a separate "already synced this session" flag, since that fact falls straight out of the two timestamps this same change already tracks. New `src/SyncSchedule.php` computes both windows and records completion. The full Sync page's own default/`--days=N`/`--full`/`--replay` controls are completely unchanged - only the lightning-bolt Quick Sync button uses `--quick`.
  - Verified against real data: a first quick sync (no `last_sync_completed_at` yet) correctly windowed both categories to "now − 7 days" and pulled in real new readings (2,601 heart-rate, 47 HRV, 15 nutrition entries, 1 sleep session, 7 steps rows); a second quick sync run immediately after correctly narrowed to "last sync − 4 days" for nutrition/weight and "last sync − 4 hours" for everything else.
- **Fix `--replay` of a `--quick` run to restore its exact original windows** (#127)
  - Now restores its exact original resolved windows from the run's own `manifest.json`, rather than recomputing from today's (since-advanced) `last_sync_completed_at` - keeps replay's whole point (exact reproducibility) intact under the new mode.

### Known limitations (not addressed this pass)
- **Support real multi-user sync (script hardcodes `$userId = 2`)** (#142)
  - `login_attempts`/`last_sync_completed_at` are per-`user_id`, but the sync script itself still hardcodes `$userId = 2` (this app is still single-user) - ready for multi-user, not exercised by it yet.

## V0.13.0 — 2026-09-11 00:00
### Changes
- **Steps: trust Fitbit as preferred source, fall back to Phone only on demonstrable tracking failure** (#117)
  - Previously picked whichever single data source reported the most steps for the whole day and discarded every other source's steps entirely. An interim per-10-minute-window "whichever source reported more, right now" design was tried and rejected before shipping - confirmed against real data that it "nitpicked" ordinary sensor-to-sensor noise (Health Connect edging out the watch by a few hundred steps in one hour, from two devices that were both actively and correctly tracking) rather than catching genuine tracking gaps. The shipped design instead treats the wrist wearable (`Fitbit`/`Charge 5` - the same physical device, labeled differently by the historical Health-Connect import vs. the live API) as preferred for every 10-minute window, and only substitutes Phone's count for that window when Fitbit's is very low (under 100 steps) **and** Phone's is at least 3x higher - i.e. the watch demonstrably wasn't tracking (not worn, or a shopping cart suppressing wrist swing), not just slightly less sensitive. `source` is `Fitbit` when every window agreed, `Phone` when Fitbit contributed nothing usable all day, `Mixed` when some windows fell back and others didn't. Verified against real data: 2026-09-09 (the exact day that exposed the interim design's nitpicking) now resolves to a clean `Fitbit`, matching the original whole-day total exactly; 2026-09-01, where the watch genuinely went dark for several hours that evening, correctly recovers ~6,500 real steps Phone caught instead.
  - Still a disclosed heuristic, not a full reconciliation (a proper natural-key cross-source merge, like `sleep_sessions`/`exercise_sessions`/`measurements`/`food_log_entries` got, is still undone) - see Known limitations.
- **Steps tab: same hierarchy treatment as other tabs, plus a per-day hourly chart** (#118)
  - Collapsible Year/Quarter/Month/Week/Day sections via `RangeTree`/`QuickToolbar`, group-level averages instead of a bare label, and a click-to-open bar breakdown by day (Week/Month/Quarter) or by month (Year) - no more separate `MultiDay.jsx`-based flat list.
  - New per-day steps chart (hourly bars, using the same Fitbit/Phone-reconciled figure as the day total) - shown automatically for Day/Week views, with a "Show chart for this day" button for Month/Year, exactly matching Heart Rate's own on-demand-chart pattern (and the same `MAX_SERIES_DAYS` threshold).
- **Add a configurable daily step goal with 3-tier badges** (#119)
  - `users.steps_goal` (Settings, defaults to 10,000 until changed) drives a 3-tier badge on every day and group average: below goal is Bad, at or above is Good, double the goal or more is Great. Group summaries (Week/Month/Quarter/Year/the top-of-range header) also report how many days in that group met the goal and how many were Great.
- **Show missing days as real 0-step entries instead of silently skipping them** (#120)
  - A day with no `steps_readings` at all becomes `{steps: 0, source: null}` (shown as "None"), so a missed-sync day correctly drags down an average and counts against the goal instead of vanishing from it. This only applies through today: a day that hasn't happened yet is left out of the response entirely, never fabricated as a zero.
- **Move the Fitbit/Phone reconciliation explanation into a new FAQ entry** (#121)
  - The page-note paragraph is gone from the Steps tab; the same explanation (now expanded, with the exact 100-step/3x thresholds spelled out) lives at Help → FAQ instead.
- **Group FAQ into collapsible per-tab sections** (#122)
  - General (top, currently empty - reserved for whole-app questions), one section per tab in the same order the tab bar itself uses (Nutrition/Heart Rate/Sleep/Exercise/Weight/Steps), Settings (currently empty), and Contact & Support (bottom) - a new `lut_faq_section` lookup table whose seeded id order *is* the section display order. Every answer now collapses behind its question by default (a `<details>`, same convention as the rest of the app) instead of all being shown open at once.
  - New FAQ entry: "How do I report a bug, request a feature, or get support?" - points to 5K-IoT, `support@5k-iot.com`.
- **Weight tab: same hierarchy treatment as other tabs** (#123)
  - Collapsible Year/Quarter/Month/Week/Day sections via `RangeTree`/`QuickToolbar`, group-level averages instead of a bare label, and a click-to-open bar breakdown by day (Week/Month/Quarter) or by month (Year). The existing continuous trend line (unchanged) stays above the hierarchy rather than being replaced by it - weight is a trend, not a per-day quantity, so the one thing that didn't make sense to fork was the chart itself. A day's own average is the mean of that day's readings (most days have exactly one); a day with more than one reading also shows the count and its min-max range.
- **Delete unused `MultiDay.jsx`** (#124)
  - The original flat day-grouping component every tab used before getting its own `RangeTree`/`QuickToolbar` (or, for Food, its own fork) treatment. Weight was its last remaining user; nothing renders it anymore.

### Known limitations (not addressed this pass)
- **Reconcile steps cross-source duplication properly (not just pick-a-winner heuristic)** (#139)
  - The Fitbit/Phone classification is name-based (`Fitbit`, `Charge 5` = wearable; everything else, including Fitbit's own phone-fallback feature `MobileTrack` = Phone) - a future new device name would silently fall into "Phone" until added to the wearable list.

## V0.12.0 — 2026-09-10 22:30
### Changes
- **Add a third Max HR source: observed from real exercise sessions** (#111)
  - Alongside the existing age estimate and manual override. For every running/treadmill/aerobics-type session (explicitly not walks or generic workouts — matched against `lut_activity_type.name`: `Running`, `Running (Treadmill)`, `API_RUNNING`, `API_TREADMILL`, `Exercise Class`), the session's own peak bpm (from `heart_rate_readings`, over its exact time window) divided by 0.95 — a hard training effort rarely reaches literal 100% of true max — is stored on that session's own new `exercise_sessions.observed_max_hr_estimate` column. The "current" observed value is the **max** of these over the trailing 3 weeks, not just the latest session, so one recent hard effort sets the ceiling rather than whatever happened to be most recent.
  - Deliberately computed lazily on read, not "live" at sync/insert time — the original plan, checked before building: `scripts/sync-google-health.php` inserts `exercise_sessions` *before* `heart_rate_readings` in every run (including `--full`), so a session's matching heart-rate data usually doesn't exist yet at the moment it's inserted; `import-health-connect.php` happens to insert heart rate first, so the two scripts actively disagree on order. Every request that needs the observed value instead does a light backfill first (only sessions in the 3-week window still missing an estimate, self-limiting as they age out of that window) — the same lazy-on-read pattern this app's age-estimate and Heart Rate/Exercise's own session-join already used.
- **Make Max HR source a user preference instead of an automatic priority order** (#112)
  - `lut_max_hr_source` (Settings) — all three sources are always computed and shown, switching is instant, and nothing is lost by switching away from one (the "reset to computed" button from the previous pass is gone; it doesn't make sense once the three sources stop overwriting each other).
- **Add HR-zone background bands to per-session bpm-curve popups** (#113)
  - The popup bpm-curve charts for an individual exercise session (both the chart-icon button on the Exercise tab and clicking a shaded exercise band on the Heart Rate day chart) now show 5 horizontal background bands, one per HR zone, with the bpm line itself in one plain neutral color drawn on top. (A first attempt colored the *line* per-segment by zone instead - dropped because it made adjacent zone colors hard to tell apart as a thin line, and Zone 2's green collided with the line's own default green.) The Z1-Z5 legend under the chart now also states each zone's actual bpm range **for that chart's own Max HR** (a zone means a different bpm window per person/date). Deliberately **not** applied to the Heart Rate tab's own whole-day chart, which stays a single plain color throughout. Shares its zone thresholds/colors (`frontend/src/hrZones.js`) with the Exercise tab's own zone badges, so the two stay consistent; `heart-rate.php` now also resolves a per-day Max HR (only for days with an exercise period, since that's its only consumer there) the same historically-accurate way `exercise.php` does.
- **Fix Exercise zone badges using today's Max HR instead of the date-in-effect value** (#114)
  - Previously `exercise.php` fetched one Max HR for the whole response and applied it to every session/day/group regardless of date, so a 5-month-old run was colored against today's estimate — most noticeable with "observed" selected, since that's a rolling 21-day figure that visibly drifts. Age is now resolved directly from the `220 − age` formula as of each date (no stored row needed, since it's a pure function of birth date); manual uses whichever `max_heart_rate_history` override was in effect on that date; observed is recomputed as a true trailing-21-day max ending on that date, via a widened backfill of `exercise_sessions.observed_max_hr_estimate` covering the requested range (not just the last 21 days from today). Group-level (Week/Month/Quarter/Year) badges average each contributing day's own dated Max HR the same way the avg-HR figure itself is already averaged. The *source* preference (age/observed/manual) itself isn't historized — there's no record of when it was last changed — so every date is classified using today's selected source, just with that source's own value as of that date.
- **Fix observed Max HR trusting a single raw sensor spike as "the peak"** (#115)
  - It previously took a plain `MAX(bpm)` over a session's heart-rate readings, which meant one sensor glitch (a lone reading spiking far above everything around it - a real, observed failure mode of optical wrist HR sensors) could set the whole estimate. `MaxHeartRate::sustainedPeakBpm()` now takes the highest rolling-*median* bpm over any 120-second window in the session instead - a median is robust to exactly one outlier inside its window, but a genuinely sustained hard effort (many consecutive elevated readings, not just one) still comes through essentially unchanged. Verified against a real session: a synthetic single-reading spike to 250 bpm amid a genuine ~172-174 bpm plateau now resolves to 173, not 250; a real, clean 25-minute treadmill run with a genuinely sustained ~179 bpm effort resolves to 176, barely different from its raw max. All previously-computed `exercise_sessions.observed_max_hr_estimate` values were reset to `NULL` locally so they recompute under the corrected logic on next read.
- **Add a Help submenu with a dedicated FAQ page** (#116)
  - The menu's Help item now expands to "Help" (the existing popup, unchanged) and "FAQ", which opens `/faq.html` in its own new tab rather than a popup - FAQ content is meant to be its own bookmarkable/shareable page. Content comes from a new `faq_entries` table (one row per question; `question`/`answer` are Markdown, rendered client-side via `marked` rather than trusting stored HTML - simpler to hand-author directly in the DB too), read through a new read-only `public/api/faq.php`. Since the app has no router library, the FAQ page is a second Vite entry point (`frontend/faq.html` / `frontend/src/faq-main.jsx`), not a client-side route. First entry seeded: "How are the heart-rate zones calculated?" (the Max HR/zone formula explained earlier this version).

### Known limitations (not addressed this pass)
- **Map "Aerobics" to an exact `lut_activity_type` row** (#146)
  - `Exercise Class` is used as the closest real match. A future source reporting running/treadmill activity under a name not in the matched list won't count toward the observed estimate until added.

## V0.11.0 — 2026-09-10 22:30
### Changes
- **Exercise tab: same hierarchy treatment, with 5-zone HR-training coloring** (#104)
  - Week/Month/Quarter/Year headers now show real averages (duration, calories, avg heart rate) instead of just a bare label, each clickable to open a bar chart broken down by day (Week/Month/Quarter) or by month (Year). Same quick-collapse toolbar, same real week-of-year numbers, same shared `RangeTree.jsx`/`QuickToolbar.jsx` plumbing (no new tree/toolbar code needed). Per-session entries stay exactly as they were (a day realistically has 1-3 sessions, not the dozens Sleep's stage list had, so there was no "too long" problem to fix here).
  - Classic 5-zone heart-rate-training coloring (50-60/60-70/70-80/80-90/90-100% of Max HR → Very Light/Aerobic/Moderate/Hard/Maximum, a blue-to-red badge) on every avg-HR figure — per session, per day, and on the new group averages.
- **Add a real Settings panel (birth date, gender, Max HR)** (#105)
  - Replacing "there's nothing user-configurable in NutriPal yet" — birth date and gender on the user's profile, plus the Max HR the zone coloring above depends on. Max HR is estimated from age (220 − age) once a birth date is set, and is **stored as a full history** (`max_heart_rate_history`, one row per change), not a single mutable number, per its own nature: every birthday recompute or manual override is a new fact, never a correction of an old one. There's no cron job (this app doesn't have one) — `src/MaxHeartRate.php` checks lazily on every read whether a birthday has passed since the last non-overridden value and inserts a fresh computed row on the spot if so; a manual override (with its own "reset to computed" undo) is never silently replaced by that automatic recompute. Guards against a nonsensical birth date (future-dated, or implying an age over 130) rather than silently computing/storing a garbage negative Max HR — found and fixed during testing, where an invalid test date got clamped to a stored `0 bpm` by MySQL's non-strict-mode `SMALLINT UNSIGNED` handling before the guard was added.
  - Schema: `users` gains `birth_date`/`gender_id` (new `lut_gender` lookup); new `max_heart_rate_history` table — deliberately **without** the `_hist` audit-companion + trigger pattern every other live table in this schema gets, since that pattern exists to preserve a row's *pre-update* state and nothing here is ever updated in place (matches this project's own "Versioning" convention over its "audit trail" one, per `Database-Design-Patterns.md`). Still gets a `BEFORE DELETE` blocker trigger for consistency with the schema's "nothing is ever destroyed" rule elsewhere.
- **Rename "Food" tab to "Nutrition"** (#106)
  - Internal file/function names like `FoodLog.jsx`/`food-log.php` are unchanged, since they're not user-facing.
- **Fix meal ordering (chronological, not core-meals-first)** (#107)
  - A day's meals now list chronologically (Early Snack, Breakfast, Morning Snack, Lunch, Afternoon Snack, Dinner, Late Night Snack) instead of all core meals first, then all snacks.
- **Fix indentation bug on nested day/meal sections** (#108)
  - On Nutrition/Heart Rate/Sleep (and, since it's the same shared CSS class, Exercise/Weight/Steps too): Day was rendering flush with its parent Week instead of nested one level in, and a Food meal was flush with its parent Day — `.day-section`/`.meal-section` were missing from the shared `margin-left` rule that Year/Quarter/Month/Week already had.
- **Default all hierarchy views to fully collapsed** (#109)
  - Nutrition/Heart Rate/Sleep/Exercise — first load and "Reset" now match the toolbar's own "Collapse all" exactly, rather than a separate week/day-open-by-default heuristic that could drift out of sync with it.
- **Add an on-demand "Show chart for this day" button for Heart Rate Month/Year/long-Custom views** (#110)
  - No longer just say the chart is hidden — the button fetches and shows that one day's chart on demand (a plain `view=day` request, confirmed via the network tab to fetch only that single day, not the whole range).

### Known limitations (not addressed this pass)
- **Fix Feb-29 birth-date edge case in Max HR age calculation** (#145)
  - Rolls to Mar 1 in a non-leap current year when computing "this year's birthday" (`DateTimeImmutable::setDate` behavior) — affects one specific day, once every ~4 years, for leap-birthday users only.

## V0.10.0 — 2026-09-10 08:30
### Changes
- **Sleep tab: same hierarchy treatment as Food/Heart Rate** (#100)
  - Week/Month/Quarter/Year headers now show real averages (total sleep, REM, Deep — each with the existing REM/Deep quality badge) instead of just a bare label, each clickable to open a bar chart broken down by day (Week/Month/Quarter) or by month (Year). Same quick-collapse toolbar (expand all / collapse all / collapse-to-level / reset), same real week-of-year numbers.
- **Extract shared `RangeTree.jsx`/`QuickToolbar.jsx` components** (#101)
  - Instead of forking a third near-identical copy: extracted `RangeTree.jsx` (the day-only-leaf hierarchy — controlled open state, lazy child rendering, week-number labels) out of Heart Rate's own tree file, now shared by both Heart Rate and Sleep; extracted `QuickToolbar.jsx` (the expand/collapse/reset toolbar body, which was byte-identical between Food and Heart Rate aside from their level lists) into one component taking a `levels` prop, now shared by Food, Heart Rate, and Sleep. No behavior change for Food or Heart Rate — verified both still work exactly as before.
- **Move per-stage-segment detail into hover tooltips** (#102)
  - Removed the long per-stage-segment list under each sleep session's bar (it listed every stage transition through the night — often 20-40 lines for one session) — the bar and its REM/Deep/Light/Awake totals legend stay exactly as before; the region type, start time, end time, and duration for each segment now live in that segment's own hover tooltip instead (`sleep.php` now includes each stage's `end_time`, previously fetched but not returned).
- **Move REM/Deep quality badge onto totals/averages lines** (#103)
  - Off the per-session graph legend and onto the totals/averages lines (day summary, and the new Week/Month/Quarter/Year averages above) — the graph legend under each session's bar now shows plain totals only, so the color-coded call-out reads as "how are you doing overall" rather than being repeated on every individual session.

### Known limitations (not addressed this pass)
- **Fix "Expand all" Year-view performance across Food/Heart Rate/Sleep** (#141)
  - Fully expanding a full Year view via the toolbar's "Expand all" is dramatically heavier for Sleep than the same action on Food or Heart Rate (already-logged as heavy in V0.8.0/V0.9.0) — a real night's stage data is much more fine-grained (tens of segments per session, each needing two formatted timestamps for its tooltip) than either of those pages' per-day content, and mounting a full year of it at once measured well over a minute and briefly made the tab unresponsive during testing. Collapsed-by-default rendering (every other view and action) stays fast; only the explicit full-Year-expand action is this heavy.

## V0.9.0 — 2026-09-10 07:15
### Changes
- **Heart Rate tab: dedicated tree renderer with real group averages and drill-down bar charts** (#98)
  - Forking a dedicated `HeartRateTree.jsx` renderer for this page (day-only leaf, no meal-equivalent sub-level — `MultiDay.jsx` stays unchanged for Sleep/Exercise/Weight/Steps).
  - Week/Month/Quarter/Year headers now show real averages (avg bpm, resting bpm, avg HRV) instead of just a bare label — closes the known limitation logged back in V0.6.0. Each average is clickable, opening a bar chart broken down by day (Week/Month/Quarter) or by month (Year) — a bar chart fits a continuous metric like bpm better than Food's pie (which suits a part-of-whole composition like calories).
  - Same quick-collapse toolbar as Food (expand all / collapse all / collapse-to-year/quarter/month/week/day / reset), with inapplicable levels graying out automatically.
  - Week headers show the real Sunday-aligned week-of-year number, same as Food, including the year-boundary "Week 52/1" style — confirmed against real data at the 2025/2026 boundary.
  - The day-level chart no longer lists each exercise session in a `<ul>` below it — hovering a shaded exercise band now shows its activity name directly on the chart, and clicking it opens that exact session's own bpm-curve popup (the same drill-down the list's icon used to offer).
  - Applied the lazy-child-rendering fix from day one this time (a closed `<details>` only hides content via CSS, it doesn't unmount it — this is exactly what froze Food's Year view before that fix): confirmed Heart Rate's own Year view loads instantly with everything collapsed by default.
- **Fix fixed-column-grid text-wrapping bug (shared CSS fix)** (#99)
  - A value like "70.6 bpm" was wrapping inside its column because `.macro-cell-value` never had `white-space: nowrap` — this was silently working for Food's numbers by coincidence of length, not a real fix — now fixed at the shared CSS rule, benefiting both pages.

### Known limitations (not addressed this pass)
- **Fix "Expand all" Year-view performance across Food/Heart Rate/Sleep** (#141)
  - Fully expanding a full Year view via the toolbar's "Expand all" mounts every day at once and takes real time (tens of seconds) — same tradeoff already logged for Food in V0.8.0; collapsed-by-default rendering (the common case) stays fast.

## V0.8.0 — 2026-09-10 05:30
### Changes
- Swapped the top-ribbon order: the menu button now comes first, with the quick-sync icon to its right.
- Reordered the menu's own items to Sync, Settings, Log out, Help, About.
- **Food tab overhaul: dedicated tree renderer, snack sub-buckets, quick-collapse toolbar** (#95)
  - Forking a dedicated `FoodTree.jsx` hierarchy renderer for this page (`MultiDay.jsx` stays unchanged, still serving Sleep/Exercise/Weight/Heart Rate/Steps).
  - Totals no longer show on a separate footer line — they live only on each day's own summary line (with working links), and a single-day view still shows that day's totals in their own line above the meals for consistency.
  - Meal summary lines are now clickable too, opening the same per-food pie popup scoped to just that meal.
  - Macro labels renamed `P`/`C`/`F` → `Prot`/`Carb`/`Fat`.
  - New quick-action toolbar between the tabs and the data: expand all / collapse all / collapse-to-year/quarter/month/week/day/meal (short letter badges with tooltips) / reset to default — buttons for a level with no matching node in the current view (e.g. Y/Q/M on a Week view) gray out automatically.
  - Non-core meal entries (previously all dumped in one "Anytime" bucket) now split into Early/Morning/Afternoon/Late Night Snack, computed **dynamically per day** by comparing each entry's own timestamp against that specific day's real Breakfast/Lunch/Dinner times (not the source's own fixed-clock-window label), cascading past any missing reference meal.
  - Week view (standalone or nested under Month/Year) now shows the real week-of-year number ("Week 36"), Sunday-aligned to match this app's own week start — not ISO 8601. A week straddling a year boundary shows both years ("Week 52/1").
  - Week/Month/Quarter/Year now show the **average** of their contained days, not a sum, with the group's own clickable summary line opening a pie chart of its children's totals (Week/Month/Quarter slice by day, Year slices by month). Quarter gets this same treatment as an extra nesting level inside Year. This top-of-range summary line was missing initially for the view's own granularity (buildTree's "skip a single-group level" rule was silently eating it, the same reason Day view needed its own special case) — added a synthetic top header for Week/Month/Year views so "Week 37:", "September 2026:", "2026:" etc. always show, not just when nested inside a coarser view.
  - **Color coding** on every meal/day/week/month/quarter/year summary (never individual food entries): calories yellow/red past meal (750/1200) or day-and-up (1800/2100) thresholds; protein green past 30g (meal) / 140g (day-and-up); carbs and fat flagged (yellow/red) against protein/calorie ratios, only above 200 kcal.
- **Fix Food Year-view rendering performance** (#96)
  - Found while verifying the Year view: the tree renderer was mounting every nested day/meal/entry into the DOM regardless of collapsed state (a native `<details>` only hides content via CSS, it doesn't unmount it), so a full year of data froze the tab solid. Fixed by only rendering a node's children when it's actually open — collapsed branches now cost nothing until expanded.
- **Fix macro-grid text wrapping on new top-level summary lines** (#97)
  - Text was overflowing/wrapping inside its fixed-width columns (missing the smaller summary font size the nested headers already used).

### Known limitations (not addressed this pass)
- "Log in" is not a reachable menu state — see V0.7.0's note below, still true, not addressed here either.
- **Fix "Expand all" Year-view performance across Food/Heart Rate/Sleep** (#141)
  - Fully expanding a Year view via the toolbar's "Expand all" mounts the whole year's data at once and can be slow — collapsed-by-default rendering (the common case) is fast; only the explicit full-expand action is heavy.

## V0.7.0 — 2026-09-10 03:00
### Changes
- **Add a top-ribbon dropdown menu (Log out/Settings/Help/Sync/About)** (#92)
  - Replacing the standalone Log out button — a hamburger button on the left opens Log out / Settings / Help / Sync / About. Sync is no longer a tab; it now opens the existing `Sync` component inside the shared `Popup` modal, unchanged otherwise.
  - Settings/Help are minimal, honest popups (reusing `Popup.jsx`) — Settings plainly states there's nothing user-configurable yet rather than faking a form; Help is a short static list of what each tab/control does.
- **Add a one-click Quick Sync icon** (#93)
  - Next to the menu — one click runs the exact same default incremental live sync (`runSync({ mode: 'live' })`, no `--days`/`--full` override) the Sync page's own "Live sync" button runs by default. There's no true "time of last successful sync" tracked in this app — confirmed in `scripts/sync-google-health.php`'s own docblock, the established incremental mode is a fixed 7-day lookback window — so that already-built mode, with its existing dedup/cross-source rules, *is* "since last sync" here today. Spins and disables itself while in flight, shows a transient "Synced" / error message that clears after a few seconds; the full progress panel/output log is still one click away via the menu's Sync popup for anyone who wants the detail.
- **Add an About popup showing the real current version** (#94)
  - New `public/api/version.php` backs it, parsed from the top of `CHANGELOG.md` rather than a hardcoded string that would silently go stale on the next bump.

### Known limitations (not addressed this pass)
- "Log in" is not a reachable menu state — the app already full-screens the `Login` component whenever there's no current user, so the ribbon (and this menu) never renders while logged out. Not a new gap, just not fixed here.

## V0.6.0 — 2026-09-10 02:15
### Changes
- **Add hierarchical Year→Quarter→Month→Week→Day collapsing across all multi-day pages** (#88)
  - Multi-day views now group days into weeks, weeks into months, months into quarters, and quarters into years (`MultiDay.jsx`) instead of one flat list of day-sections — a Year view now shows 3-4 collapsed quarters instead of up to 365 day-sections. Any level that would only produce a single group for the requested range is skipped entirely, so Day/Week views stay pixel-identical to before. Applies automatically to every page that already used `MultiDay` (Food, Sleep, Exercise, Weight, Heart Rate, Steps).
- **Add a per-session heart-rate popup chart for exercise sessions** (#89)
  - A small chart-icon button next to each session opens a line chart of real bpm over elapsed minutes (0 → session duration), fetched on demand from a new `public/api/heart-rate-range.php` endpoint (raw readings for one exact time window, not a calendar-day view). The same icon+popup now also appears on the Heart Rate page itself, under each day's chart, next to the exercise periods it already overlays there as shaded bands — `heart-rate.php`'s `exercise_periods` now also carries each period's real `id`/`start_time`/`end_time` (previously only the day-chart's clipped 0-1440 minute values), needed to query and identify the right window.
  - New shared `Popup.jsx` (minimal modal) and `SessionHrPopup.jsx` (icon + on-demand fetch + line chart) components, reused across Exercise, Heart Rate, and (via a separate pie-specific popup) Food.
- **Add a fixed-width tabular macro grid for Food (kcal/P/C/F)** (#90)
  - `MacroRow`, a 7-column CSS grid: kcal-value | "P" | value | "C" | value | "F" | value, instead of inline text, so the numbers line up down the page — reused for per-entry rows, meal summaries, day summaries, and the footer totals, all sharing the same column template.
- **Add a per-day macro breakdown pie chart** (#91)
  - Clicking a day's kcal/protein/carb/fat total pops open a pie chart of that macro's contribution per food logged that day (grouped by name+brand, so a food logged twice in a day is one slice). Wired onto both the footer totals and the collapsed day-summary line — the latter needed explicit `stopPropagation()`/`preventDefault()` since it's nested inside a native `<summary>`, otherwise opening the popup would also toggle the day section closed.

### Known limitations (not addressed this pass)
- Group-level headers (year/quarter/month) show only a label, not aggregated stats — only day-level summaries show totals. Adding aggregates at every level would need real per-page work not requested here.

## V0.5.0 — 2026-09-10 01:15
### Changes
- **Add new Steps page** (#86)
  - `public/api/steps.php`, `frontend/src/components/Steps.jsx`, with a daily bar chart, plus Day/Week/Month/Year/Custom views like the other pages.
- **Work around steps cross-source double/triple-counting** (#87)
  - Found and worked around a real, previously-documented-but-unfixed bug before shipping this: `steps_readings` has an already-known open cross-source duplication problem (see `doc/wiki/Database-Schema.md`'s Open Items) — Health Connect's bulk import and the live Google Health API sync each independently report steps for overlapping real time windows at different timestamps, so summing every row for a day double- or triple-counts. Confirmed directly: 2026-09-09 has one live-API stream reporting 16,830 steps and another reporting 6,380 for the same day.
  - Asked before building rather than shipping inflated numbers. A first heuristic (prefer the live API's own sources whenever present, fall back to Health Connect only when the API had nothing that day) was disproven by real data — 2026-09-07's live-API source reported only 1,381 steps while a same-day Health-Connect-imported source reported 16,419, clearly the fuller day. Replaced with a simpler, honester rule: per day, use whichever single `data_source_id` reported the most steps, regardless of which pipeline it came from. The chosen source (and every other source's total that day, for transparency) is shown in the UI — this is a disclosed heuristic, not a real fix.

### Known limitations (not addressed this pass)
- **Reconcile steps cross-source duplication properly (not just pick-a-winner heuristic)** (#139)
  - Worked around (pick the day's highest-reporting source) but not actually reconciled the way food_log_entries/sleep/exercise/measurements were earlier — a real fix would need the same kind of natural-key cross-source merge work, not just picking a winner and discarding the rest.

## V0.4.0 — 2026-09-10 00:40
### Changes
- **Add Day/Week/Month/Year/Custom views to Heart Rate** (#83)
  - Matching Food/Sleep/Exercise/Weight. `heart-rate.php` groups its per-day summary/series/overlay data into the same `days[]` shape the other range-aware endpoints already use; the frontend wraps it in the same `MultiDay` collapsible-per-day component.
- **Show aggregated details on every collapsible day/meal summary line** (#84)
  - `MultiDay` gained a `renderSummary(day)` prop rendered directly in the always-visible `<summary>` line — Food shows daily/meal macro totals, Sleep shows total duration plus REM/Deep quality, Exercise shows session count/duration/calories, Weight shows the day's reading or range, Heart Rate shows avg/resting bpm. Fixed a regression this caused along the way: giving `<summary>` a flex layout (to place the aggregate on the right) silently removes the browser's native disclosure triangle entirely, not just repositions it — restored by hand via a rotating `::before` arrow keyed off the parent `<details>`'s `[open]` attribute.
- **Fix severe Heart Rate Year-view query performance (~14.5s)** (#85)
  - Computing Heart Rate's Year view the naive way (one summary/series query per calendar day) took ~14.5s end to end - not from any single query being slow, but from ~1,800+ sequential round trips. A first fix attempt (batching all days into one query via a day-boundary-derived-table JOIN) was actively worse - confirmed directly, it made MySQL evaluate every raw reading against every day's bounds with no usable index, hanging for 2+ minutes before being killed via `KILL` on the running thread. Replaced with a UNION ALL of independent per-day aggregate subqueries (each keeps its own simple indexed range, just merged into one round trip) - correct, and cut a full year down to ~11s. The remaining cost is genuine: exact MIN/MAX/AVG/COUNT over several million raw readings can't be answered from an index alone. The per-day bpm-curve chart itself is skipped for ranges over 10 days (Month/Year, and any long Custom range) rather than computed and hidden — those views render every day collapsed by default anyway, so the chart is never seen without expanding a day first; the UI says so explicitly rather than showing a misleading "no readings."

### Known limitations (not addressed this pass)
- **Add a precomputed daily-rollup table for Heart Rate Year-view performance** (#140)
  - Heart Rate's Year view still takes real time to load (~10s) since it computes exact aggregates over the full raw dataset live on every request. A precomputed daily-rollup table, refreshed at sync time, would fix this properly but is a bigger schema/sync change than this pass's scope.

## V0.3.0 — 2026-09-09 23:50
### Changes
- **Add a Weight trend line chart** (#82)
  - Not just a per-day list. Reuses `chart.js`/`react-chartjs-2` (already a dependency for the Heart Rate chart) — a linear x-axis over each reading's real timestamp (epoch ms) with a tick/tooltip callback formatting it back to a date, since there's no time-scale adapter installed yet. Only rendered when a range has 2+ readings (a single point isn't a trend); the per-day list stays underneath regardless, since exact values/timestamps are still useful next to the chart.

## V0.2.0 — 2026-09-09 23:30
### Changes
- **Add prev/next date-nav arrows stepping by the current view's period** (#75)
  - A day in Day view, a week in Week view, a whole month in Month view, a year in Year view — added `LocalDay::resolveRange()`/`stepDateByView()` alongside the existing single-day helpers rather than replacing them, so Heart Rate/Sync (still day-only) are unaffected.
- **Add multi-day views (Day/Week/Month/Year/Custom) for Food, Sleep, Exercise** (#76)
  - And the new Weight page. `food-log.php`, `sleep.php`, `exercise.php` all gained `view`/`end_date` params and now return a `days[]` array grouped by local calendar day instead of one flat day; `LocalDay::resolveRange()` computes the UTC window for a Sunday-Saturday week / calendar month / calendar year / arbitrary custom range in one indexed query rather than looping per day. `view=day` still returns a one-day `days[]` array, so the frontend has a single code path for every view and Day view stays pixel-identical to before.
- **Add collapsible per-day (and per-meal) sections** (#77)
  - `frontend/src/components/MultiDay.jsx`, native `<details>/<summary>`, no new dependency — open by default for short ranges (≤7 days), collapsed by default for month/year so a year view doesn't open hundreds of sections at once. Food additionally nests collapsible per-meal sections inside each day.
- **Add new Weight page** (#78)
  - `public/api/weight.php`, `frontend/src/components/Weight.jsx` — the `measurements`/`lut_measurement_type` tables already had everything needed from the sync work; converts stored grams to pounds server-side using `unit_conversions.factor_to_base` (no hardcoded conversion constant) rather than trusting a fixed factor that could drift from the DB's own units.
- **Standardize sleep duration display as H:MM everywhere** (#79)
  - `formatHoursMinutes()`, replacing the old "1h 15m" session style and the stage-totals legend's bare-minutes ("46m") — applied everywhere a sleep duration is shown, per request.
- **Show each sleep stage segment's own start timestamp** (#80)
  - `sleep.php`'s stage query already selected `start_time` per segment but the response discarded it, keeping only the duration; now included and rendered in a new chronological per-segment list under the existing stage bar.
- **Add REM/Deep sleep quality badges** (#81)
  - On the stage-totals legend, using the user's own target bands: <1:00 bad, 1:00–1:15 adequate, 1:15–1:30 ok, >1:30 good.

### Known limitations (not addressed this pass)
- Weight page has no charting/trend line yet — multi-day views list readings per day, same as Sleep/Exercise, no graph. (Fixed next version, #82.)
- A day with zero entries in a multi-day range is simply omitted from `days[]` (matches the existing single-day "no X logged" convention) rather than shown as an explicit empty section — so a week view can't currently highlight "you didn't log food on Tuesday" at a glance.

## V0.1.10 — 2026-09-09 22:15
### Changes
- **Fix technical/unreadable serving-unit labels in the food log UI** (#74)
  - Reported directly from the real UI: entries showed things like "2.84 api_951_gram" or "1 hc_reported_serving_266" instead of a readable quantity. Root cause: `public/api/food-log.php` selected `lut_serving_unit.label` for display — that column is an internal technical key (embeds the food id and source prefix) never meant to be shown to a user; the real human-readable name was already stored elsewhere (`unit_conversions.name` for standard units, `foods_db_custom_units.unit_name` for per-food custom ones) but wasn't being selected.
  - Changed the query to select `COALESCE(uc.name, fdcu.unit_name) AS serving_unit_label` instead. No frontend change needed — `FoodLog.jsx` already just renders `serving_amount` + `serving_unit_label` as given.
  - Verified in the real UI on 2026-08-28: entries now read "2.84 gram", "1 reported serving", "300.06 gram", etc. — a clear unit name paired with the existing quantity, instead of the raw technical label.

## V0.1.9 — 2026-09-09 21:45
### Changes
- **Fix `food_log_entries` cross-source duplication (the last unresolved category)** (#70)
  - The last of the four cross-source categories left open after V0.1.6/V0.1.7. Unlike sleep/exercise/measurements, the same real meal logged by both sources routinely resolved to *two different `food_id`s*, not just two rows with the same timestamp, so a plain natural-key dedup couldn't fix it.
  - Root cause found and fixed: `foods_db` rows created by `findOrCreateFoodReal()` (live API, real gram data) store genuine per-100g macros; rows created by `findOrCreateFoodFallback()`/HC's `findOrCreateFood()` store the *raw absolute macros for whatever was reported*, with a placeholder custom unit (`equivalent_amount = 100`, nominal, not real grams) — a deliberate, disclosed placeholder from the original food-log redesign, never actually corrected until now. `findOrCreateFoodReal()` now also scans for a ratio-consistent placeholder candidate (same 15%-of-median consistency check `findOrCreateFoodFallback()` already trusts) and, when found, migrates every `food_log_entries` row off the placeholder onto the real-gram food via a new `reconcilePlaceholderIntoReal()` — re-expressing `serving_amount` in real grams so the displayed total is unchanged, verified algebraically against `public/api/food-log.php`'s own display formula. The placeholder row itself is left permanently orphaned (`trg_foods_db_bd` forbids `DELETE` on `foods_db`, matching every other table in this schema).
  - Verified against the real database and UI: rebuilt, re-imported, replayed the live sync. `NUTRITION: {"rows_seen":6745,"real_gram_match":4814,"fallback_placeholder_match":1931,"foods_db_versions_created":1094,"foods_db_versions_reused":5651,"inserted":4338,"skipped_cross_source":2407}` — 146+ placeholder→real-gram reconciliations fired with zero crashes. Direct query: cross-source `(name, brand_name)`-matching pairs with different `food_id` dropped from a four-figure baseline to 172 residual (foods with no real-gram data ever observed on either side — expected, can't be reconciled without it). Confirmed in the real UI on 2026-08-28: every previously-duplicated line item (ground beef, cottage cheese, coffee, almondmilk, tuna, onion, ravioli, whey protein, and more) now shows exactly once, with the day's total correctly dropping from a doubled 3837.49 kcal to a real 1918.77 kcal.
- **Fix nutrition sync ignoring the entry's own reported serving unit** (#71)
  - `syncNutrition()` computed `$unitLabel` from `serving.foodMeasurementUnitDisplayName` — a field that **does not exist** on any real nutrition-log entry (confirmed against real recorded API responses). Every entry silently fell back to the literal string `'serving'`, so any food actually reported in a different unit (fl oz, cup, tbsp, ...) got gram-converted using the food's own generic "1 serving" size instead of the unit that was really used. Confirmed real impact: "2% Reduced Fat Milk" logged as 3 fl oz (real ~92g) was treated as 3 whole "servings" (~720g using milk's own serving definition), producing a stored per-100g value ~8x too low. Fixed by resolving the *reference* `serving.foodMeasurementUnit` against the food resource's own `servings[]` array (already fetched, already has the URI→display-name mapping) instead of a field that was never there.
- **Fix brand-matching gap blocking branded/unbranded reconciliation** (#72)
  - Health Connect never captures a brand at all, so its always-NULL-brand row for a branded product could never even be considered a match candidate against the live API's branded version of the same food. Confirmed real case: "Vanilla Flavored Whey Protein Powder" — one row branded "PREMIER PROTEIN" from the API, one unbranded from Health Connect, identical macros, kept apart purely by an exact-brand-match filter. Loosened the candidate lookup in `findOrCreateFoodReal()`, `findOrCreateFoodFallback()`, and Health Connect's own `findOrCreateFood()` (which previously hardcoded `brand_name IS NULL`, unable to match into an already-branded row at all) to accept either side being `NULL`; the existing macro-consistency checks are what actually guard against conflating two genuinely different branded products. Added `enrichBrandIfMissing()` so the surviving row also picks up the real brand the first time it's known — using the "combined, enhanced version" rather than whichever happened to be created first.
- **Add cross-source natural-key upsert for `food_log_entries`** (#73)
  - Now that `food_id` reliably converges across sources, `syncNutrition()`'s own upsert gained a `(user_id, start_time, food_id)` cross-source check (the same `upsertByNaturalKey()` mechanism used for sleep/exercise/measurements). `serving_amount`/`serving_unit_id`/`meal_type_id` are excluded from conflict detection — the two sources can correctly express the same real intake in different units or categorize a meal differently without that being flagged as a disagreement.

### Known bugs (not yet fixed)
- **Investigate 172 residual cross-source `food_log_entries` pairs with no real-gram data on either side** (#147)
  - Foods where at least one side never had usable real-gram serving data to reconcile against, so the placeholder can't be confirmed as the same food with confidence. Left as-is rather than guessed.
- **Investigate 14 `food_log_entries` rows sharing the same natural key more than once** (#148)
  - Still share `(user_id, start_time, food_id)` more than once — not yet individually investigated; could be genuine same-instant double-logging (e.g. two real servings at the same minute) rather than a bug.

## V0.1.8 — 2026-09-09 20:00
### Changes
- **Map remaining Health Connect exercise-type codes (58, 11)** (#69)
  - `58`→Other Workout (256 sessions — the single most common unmapped code, larger than several already-mapped ones), `11`→Exercise Class (6 sessions). Verified against Android's `ExerciseSessionType` documentation the same way as the first seven, not guessed. Every real exercise session in this account now shows a readable name — no `HC_<code>` labels left.

## V0.1.7 — 2026-09-09 19:30
### Changes
- **Fix cross-source dedup silently dropping complementary exercise data** (#67)
  - Health Connect's exercise sessions never carry calories/distance/steps/average-heart-rate at all (a known Health Connect limitation, already documented) — so when the live sync found a session HC had already recorded and just skipped it, those fields stayed permanently `NULL` even though the live API's own copy of the same session had real values for them. Caught directly by inspecting a real day's exercise entries after the V0.1.6 fix and finding HC-sourced sessions still showing no calories/distance/steps.
  - `upsertByNaturalKey()`'s cross-source branch now merges instead of skipping: any field that's `NULL` on the existing row and non-`NULL` on the incoming one gets filled in via `UPDATE`. A field where both sides have a genuine, differing non-`NULL` value is a real conflict — filled in anyway, but also flips `ingestion_source_id` to the `mixed` sentinel (reserved for exactly this since the schema was first drafted, now actually exercised).
  - Getting the conflict/fill split right took three calibration passes against real data, each catching a different false positive:
    - `data_source_id`/`recording_method_id`/`ingestion_source_id` are *expected* to differ by source — excluded from comparison entirely (first attempt flagged 100% of cross-source exercise matches as "conflicts" purely because of this).
    - A session's `end_time` can drift up to ~1 minute between sources (stage-boundary rounding, already known from the V0.1.6 work) — added a 5-minute datetime tolerance so this doesn't count as a conflict.
    - A plain numeric tolerance was too tight for weight's rounding difference (HC to the nearest 100g, the live API to the gram) — widened to 1% relative (floor 0.0005 for near-zero values), confirmed against the real ~100g deltas found earlier without masking a genuinely different calorie/distance/duration value.
    - `activity_type_id` and `activity_name` are excluded for a different reason: `activity_type_id` is a plain find-or-create keyed on each source's own raw activity code (`HC_`/`API_`-prefixed), so it's *guaranteed* to differ for the same real activity — not a per-instance disagreement. `activity_name` hit the identical problem one level up (confirmed real case: Health Connect's own title vs. the live API's "Treadmill run").
  - Note: the live API's own `exerciseType` values (confirmed real examples: `WALKING`, `OUTDOOR_BIKE`, `STAIRCLIMBER`, `WORKOUT`) are a *different* vocabulary from Health Connect's numeric codes, not just a differently-formatted version of the same one — unifying both into one canonical `lut_activity_type` space (so the same real activity always resolves to the same row regardless of source) is a real, larger effort, already tracked as an open item (#138), not attempted here.
  - Verified against the real database: rebuilt, re-imported, replayed the same live sync (`--replay`, network-independent) — `EXERCISE: inserted=25, merged_cross_source=1570, merged_conflict=305`, `SLEEP_SESSIONS: inserted=552, merged_cross_source=646, merged_conflict=14`, `WEIGHT: inserted=6, skipped_cross_source=513` (no false conflicts this time). Confirmed in the real UI, on the exact real day this was found on: every exercise session for that day now shows calories/distance/steps/heart-rate, and Health Connect-only sessions display "Walking"/"Running (Treadmill)" instead of raw codes.
- **Map Health Connect numeric exercise-type codes to readable names** (#68)
  - Health Connect's `exercise_type` is a numeric platform constant, not a name — the importer just prefixed it (`HC_53`), which is what the UI actually displayed whenever a session had no `title` of its own (common) since it falls back to the activity-type name. Verified the real numeric values against Android's `ExerciseSessionType` documentation one at a time rather than guessing (a wrong label would be worse than the honest `HC_<code>` fallback) and added a translation table for the codes that actually appear in this account's real data: `53`→Walking, `34`→Running (Treadmill), `33`→Running, `60`→Elliptical, `49`→Swimming (Pool), `59`→Stair Climbing (Machine), `4`→Biking — covering 1,992 of 2,014 real exercise sessions. Two rarer codes (`58`, `11`) stay as an honest `HC_<code>` fallback rather than a guessed name.

## V0.1.6 — 2026-09-09 16:00
### Changes
- **Fix cross-source duplication for `sleep_sessions`, `exercise_sessions`, and `measurements`** (#65)
  - Health Connect and the live API each assign their own `api_uid` to the same real-world event, so `UNIQUE(user_id, api_uid)` — a real, working guard against same-source re-import — never caught the same session/reading arriving from *both* sources. Confirmed via real data before touching anything: 660/710 HC sleep sessions, 1980/2015 HC exercise sessions, and 513/521 HC weight readings each matched a live-API row on `start_time`/`reading_time` alone (exercise sessions matched exactly on `end_time` too; sleep sessions' `end_time` can drift up to ~1 minute between sources, so only `start_time` is safe to key on; measurement *values* differ slightly by source — HC rounds to 100g, the live API keeps single-gram precision — so `value` deliberately isn't part of the key either).
  - Added real natural-key constraints: `UNIQUE(user_id, start_time)` on `sleep_sessions` and `exercise_sessions`, `UNIQUE(user_id, measurement_type_id, reading_time)` on `measurements`. `sync-google-health.php`'s generic `upsertByNaturalKey()` gained an optional cross-source check — if the primary `(user_id, api_uid)` lookup misses but the alternate (natural-key) lookup hits, the row already exists under the other source's `api_uid`; skip rather than insert (would duplicate) or update (would silently overwrite that source's provenance and, for measurements, its more-precise value, for no benefit). `import-health-connect.php`'s sleep-session dedup lookup switched from `api_uid` to `start_time` for the same reason — the actual colliding row on a cross-source hit has a *different* `api_uid`, so looking it up by `api_uid` would miss it entirely.
  - Verified against the real database: rebuilt from the corrected schema, re-imported the Health Connect export, then ran a real `--full` live sync — `SLEEP_SESSIONS: inserted=552, skipped_cross_source=660`, `EXERCISE: inserted=291, skipped_cross_source=1979`, `WEIGHT: inserted=6, skipped_cross_source=513`, matching the pre-fix analysis almost exactly. Confirmed zero internal duplication on all three tables via direct query (`COUNT(*)` equals `COUNT(DISTINCT ...)` on each natural key), and confirmed a second HC re-import stays fully idempotent (every row `skipped_duplicate`, DB counts unchanged).
- **Fix `sleep_stages` insert crash from natural-key drift** (#66)
  - `syncSleep()`'s stage insert used a plain `INSERT` guarded only by an in-memory `(start_time, end_time)` check — but `uq_sleep_stages_natural` (added in V0.1.5) keys on `(session, stage_type, start_time)`, not `end_time`, so a stage whose `end_time` drifts slightly between sources slipped past the in-memory check and crashed on the real constraint. Changed to `INSERT IGNORE` with `rowCount()` deciding inserted-vs-duplicate, dropping the now-redundant in-memory check entirely.

### Known bugs (not yet fixed)
- **Fix `food_log_entries` cross-source duplication (the last unresolved category)** (#70)
  - Unresolved and structurally harder than the three fixed above. Checked before starting: 13,094 food-log pairs match on `(user_id, start_time)` alone, but only 122 also match on `food_id` — the same real meal usually resolves to a *different* `food_id` between sources (Health Connect's placeholder-serving-unit version vs. the live API's real-gram version), so a naive natural-key dedup can't just ignore `food_id` the way it does for sleep/exercise/measurements. A real fix needs the already-tracked "retroactively reconcile Health-Connect placeholder units against real-gram live-API data" work first, so the same real food resolves to the same `food_id` from either source. Deferred as a separate task. (Fixed in V0.1.9, #70.)

## V0.1.4 — 2026-09-08 23:30
### Changes
- **Add API request/response logging for the sync script** (#55)
  - `scripts/sync-google-health.php` now logs every live API request/response it makes to `storage/api-logs/<run_id>/<endpoint>.jsonl` (on by default; `--no-log` opts out), plus a `manifest.json` recording that run's `--full`/`--days` window. All two HTTP call sites (`streamDataPoints()`'s pagination, `fetchFoodServings()`'s food-resource lookups) now go through one shared `apiCall()` function, which is also the only place the `Authorization` header ever touches memory — it's deliberately never written to the log (verified by grepping a real run's logged output for any token material: none found).
  - Added `/storage/api-logs/` to `.gitignore` — same sensitivity as the existing `storage/import-logs/` entry (real personal health data verbatim).
- **Add `--replay=<run_id>` mode** (#56)
  - Re-runs the exact same parsing/ingestion code against a previously-recorded run's logs instead of the network, via a new `ReplayReader` that hands back recorded responses in original order (falling back to a synthetic empty page once exhausted, which `streamDataPoints()`'s existing "no more points" check already treats as end-of-pagination — no special-casing needed). No OAuth token refresh happens in replay mode; the original run's `--full`/`--days` window auto-restores from its manifest. Verified against a real run: replay completed in 0.3s vs. the original 13.2s live run, with every category correctly reporting "already exists" and zero new rows written.
- **Add `--debug` trace flag** (#57)
  - Traces per-record processing decisions to the human-readable log via a new `debugLog()` helper — food match type/brand/version for nutrition, session/action for sleep/exercise/measurements/daily-resting-heart-rate, and per-*page* (not per-row) counts for the three high-volume insert-missing categories (steps/heart-rate/HRV), since a full day's worth of per-reading trace lines wouldn't be practical to read.

## V0.1.5 — 2026-09-09 04:00
### Changes
- **Add Sync tab UI (live/replay/import controls)** (#58)
  - Triggers `sync-google-health.php` (live, with `--full`/`--days`/`--debug` controls, or `--replay=<run_id>` picked from a dropdown populated from `storage/api-logs/`) and `import-health-connect.php`, both run synchronously (the request blocks until the script exits, then shows its captured output). New endpoints `public/api/run-sync.php`, `public/api/sync-runs.php`, `public/api/import-hc.php`. The Health Connect import takes a **path already on disk**, not a browser file upload — an upload was tried first and abandoned after a real ~500MB export took over 20 minutes for PHP's built-in dev server (`php -S`, used by `start-services.ps1`) to merely receive the multipart body, a known inefficiency of that SAPI for large uploads; a path is also how the existing CLI script already works. `start-services.ps1` now starts the dev server with raised `upload_max_filesize`/`post_max_size`/unlimited execution time regardless (harmless to keep, no longer load-bearing for this feature).
- **Fix duplicated heart-rate readings on repeat Health Connect import** (#59)
  - HC's per-sample heart-rate rows (`heart_rate_record_series_table`) carry no per-sample id — only the parent session does — so `api_uid` was always `NULL` and the table's `UNIQUE(user_id, api_uid)` constraint (a no-op against NULLs) never caught the re-insert. Confirmed against the real database: 5,712,042 rows where only 2,856,973 were distinct, exactly 2×. Fixed with a real `UNIQUE(user_id, reading_time)` constraint (`sql/schema.sql`), since one reading per user+timestamp is the actual real-world identity here — already the assumption the live sync's own in-memory dedup makes, just never enforced at the DB level.
- **Fix sleep stages silently dropped (not deduped) on re-import** (#60)
  - The session-insert's duplicate-key catch never recorded the existing session's id, so every stage belonging to a session already in the database found no parent to attach to and was discarded as `skipped_error`. Naively fixing that lookup would have started duplicating stages instead (`sleep_stages` had the identical inert-`api_uid` problem as heart rate) — fixed both together: the session lookup now resolves the existing session's id on a duplicate, and a new `UNIQUE(user_id, sleep_session_id, stage_type_id, start_time)` constraint gives stages a real natural key.
- **Fix `--full` sync crash from the new heart-rate uniqueness constraint** (#61)
  - A `--full` sync deliberately skips its in-memory timestamp preload (full-history dedup would mean holding millions of timestamps in memory), so it relied entirely on a plain `INSERT` never colliding with anything — which the new `heart_rate_readings` constraint immediately broke the first time live-API and Health Connect data overlapped on the same timestamp. Changed to `INSERT IGNORE` with `rowCount()` deciding inserted-vs-skipped, matching the pattern already used elsewhere in this script.
  - Rebuilt the database from the corrected schema and fully re-imported (Health Connect export + a real `--full` live sync) to clean up the duplicated rows; verified via direct queries that `heart_rate_readings` and `sleep_stages` now have zero internal duplicates, and via a second real re-import that re-running no longer reproduces either bug.
- **Add a richer replay-run picker (window, duration, timestamp)** (#62)
  - Each entry now shows when it ran, its window (e.g. "Last 7d (covers 2026-09-02 to 2026-09-09)" or "Full history"), and its actual duration — read straight from that run's own human-readable log (`storage/import-logs/sync-google-health-<run_id>.log`, matched against its `complete in Xs` line) rather than the bare run id it showed before.
- **Add rough sync progress feedback (elapsed timer + last-run estimate)** (#63)
  - For all three Sync actions (live sync, replay, HC import): an elapsed-time counter plus a "last similar run took ~Xs" estimate fetched once when the action starts. Originally designed as a live-polled log tail, but PHP's built-in dev server (`php -S`) is single-threaded — proved directly that a request sent to a progress endpoint while an import was running just queued for the entire ~3 minutes and only returned once the import finished, so any polling-based design is structurally starved out locally. Simplified to a one-time estimate fetched *before* the blocking request fires, plus a client-side-only elapsed timer; the progress bar caps at 95% and just sits there past the estimate rather than claiming false completion.
- **Fix the same duplication bug in `steps_readings` and `heart_rate_variability_readings`** (#64)
  - Found when an unexplained `--full` live sync (started 2026-09-09 01:54, cause undetermined — best guess is a stray duplicate request among several stuck connections queued on the dev server while debugging the browser automation tool, but not confirmed) duplicated ~138,000 steps rows before being interrupted: `--full` mode's dedup preload is skipped by design, and `steps_readings` had no DB-level guard for live-API rows (which never get a real `api_uid`), same root cause as the heart-rate bug above. Added `UNIQUE(user_id, reading_time)` to both tables (mirroring the heart_rate_readings fix) and rebuilt/re-imported again; this also incidentally closes the steps cross-source duplication noted below, since one canonical reading per user+timestamp is now enforced regardless of source.

### Known bugs (not yet fixed)
- Cross-source duplication for **sleep sessions, exercise sessions, weight/height** (#65, fixed V0.1.6) **and food log entries** (#70, fixed V0.1.9) is still unresolved — Health Connect and the live API each have their own id space for the same real-world event, so `UNIQUE(user_id, api_uid)` can't recognize the same session/entry arriving from both sources. Narrowed this session: steps and heart-rate readings are no longer affected, since their new natural-key constraints (`UNIQUE(user_id, reading_time)`) catch duplicates regardless of source.
- The unexplained `--full` sync mentioned above was never root-caused. Watch for a repeat; if it recurs, capture the dev server's request pattern at the time rather than restarting it immediately.

## V0.1.3 — 2026-09-08 19:15
### Changes
- **Lift date state up to `App.jsx` (shared across tabs)** (#52)
  - The date is now rendered once above the tab switcher, instead of each page (Food/Heart Rate/Sleep/Exercise) keeping its own independent date state — switching tabs now keeps the same day selected rather than each page silently resetting to today.
- **Add a real native date picker** (#53)
  - `DateNav.jsx` now shows a button formatted as "Weekday DD-MMM-YYYY" (e.g. "Tuesday 08-Sep-2026") that opens the browser's native date picker (`input.showPicker()`) when clicked, backed by a visually-hidden real `<input type="date">` so arbitrary dates can be entered directly, not just stepped one day at a time.
  - Removed `dateUtils.js`'s now-unused `shiftDate()` (no longer needed without prev/next arrows), replaced with `formatDisplayDate()`.
- **Fix sleep stages grouped instead of shown chronologically** (#54)
  - `sleep.php`'s stage query used `GROUP BY stage_type` with `SUM()`, which merged every LIGHT segment (or DEEP, REM, etc.) across the whole night into one total — losing the actual sequence of sleep cycles. A real night's sleep normally cycles through stages many times (confirmed against real data: one session had 49 individual segments merged down to just 4 stage blocks). Fixed to return segments in chronological order (`ORDER BY start_time`, no grouping) for the stage bar, with per-type totals computed separately in PHP for the legend. Verified: the same real session now renders as a genuine hypnogram-style sequence instead of four solid blocks.

## V0.1.2 — 2026-09-08 18:45
### Changes
- **Overlay sleep/exercise periods on the Heart Rate chart** (#51)
  - The Heart Rate chart now overlays sleep (blue) and exercise (orange) periods as shaded background bands directly on the bpm timeline, so correlations (a heart-rate spike during a walk, the overnight low during sleep) are visible at a glance — verified against real data: both exercise bands lined up exactly with the two heart-rate spikes on a real day, and the sleep band lined up with the overnight low.
  - Required switching the chart's x-axis from category labels to a linear "minutes since local midnight" scale (0–1440) so the bpm line and the overlay boxes share one coordinate system (`chartjs-plugin-annotation`, a new small dependency).
  - `public/api/heart-rate.php` now also returns `exercise_periods`/`sleep_periods`, clipped to the current day's [0, 1440] window (a sleep session that started the evening before gets clipped to start at 0) using an *overlap* query — does the session touch this day's window at all — which is deliberately looser than `exercise.php`/`sleep.php`'s own single-page day-assignment rules, since a chart overlay should show anything touching the visible window, not just sessions "assigned" to this exact day.

## V0.1.1 — 2026-09-08 18:15
### Changes
- **Add Heart Rate, Sleep, and Exercise pages** (#49)
  - Added three more pages: **Heart Rate** (resting/avg/min-max bpm + avg HRV stats, plus a day-shaped bpm line chart bucketed into 10-minute averages server-side so the browser never has to chart tens of thousands of raw readings), **Sleep** (session duration, start/end times, and a proportional stage-breakdown bar with a legend), and **Exercise** (a day's sessions with duration/calories/distance/steps/avg heart rate). App now has a simple tab switcher (Food / Heart Rate / Sleep / Exercise) in `App.jsx`.
  - New PHP endpoints `public/api/heart-rate.php`, `sleep.php`, `exercise.php`, alongside a new shared `src/LocalDay.php` extracted from `food-log.php`'s local-day-bucketing logic (now used identically by all four endpoints instead of being repeated). Sleep uses a different bucketing rule than the other three — a session is shown on the day it *ended*, not started, since sessions usually span midnight.
  - Added `chart.js`/`react-chartjs-2` to `frontend/` — the first frontend dependency beyond React itself.
  - Verified all three new endpoints against real data and in a real browser (each page, several real dates, empty-state days).
- **Add shared date-nav component** (#50)
  - New shared frontend pieces: `frontend/src/components/DateNav.jsx` and `frontend/src/dateUtils.js` (date-shifting math anchored at UTC noon to avoid DST off-by-ones, plus converting the API's UTC datetime strings to the viewer's local time for display), extracted from `FoodLog.jsx` since all four pages need the same date-navigation behavior.

### Known, disclosed limitations
- All three new pages surface the same already-disclosed Health-Connect/live-API duplication issue as the food log does (#65, #70) — e.g. a night's sleep or a walk shows up twice (once per source) on days covered by both. Confirms this is a real, pervasive, cross-category symptom now visible in every page, not just food — raises the priority of an actual reconciliation fix.

## V0.1.0 — 2026-09-08 17:30
### Changes
- **Build the first frontend screen: Food log** (#46)
  - The first real application screen exists. New `frontend/` (Vite + React, plain JavaScript): a day's food log with meal grouping (Breakfast/Lunch/Dinner/Snack/Anytime), real-world serving labels, and derived macros per entry plus a daily total. Date navigation (prev/next day) included.
  - New minimal JSON API, one file per endpoint under `public/api/` (matching the existing one-file-per-concern style, no router/framework introduced): `food-log.php` (the screen's data) and `login.php` (see below). Verified directly against the real database, including the day-boundary edge case: an entry at UTC `2026-09-06 03:55` (local `2026-09-05 23:55`, `APP_TIMEZONE=America/New_York`) correctly lands only on `2026-09-05`, not `2026-09-06` — the naive-UTC-bucketing mistake already found and avoided earlier this session (see `doc/wiki/Data-Sync.md`).
  - Verified end-to-end in a real browser (not just curl): log in with the real seeded email, browse several real days of food (including ones with duplicate Health-Connect/API-sourced entries for the same food — the already-disclosed cross-source duplication limitation is now visibly obvious in the UI, e.g. a day's total showing roughly double a realistic value), refresh to confirm login persists, log out and back in.
  - `doc/wiki/Architecture.md` gets a new "Frontend (dev setup)" section (how to run it, the `/api` proxy) and a correction: the PHP backend runs locally via `php -S`, not Apache — XAMPP is only used for MySQL locally.
- **Add placeholder (no-security) login** (#47)
  - Explicitly no password, session, or security of any kind — `public/api/login.php` looks up a real user by email, `frontend/src/components/Login.jsx` + `App.jsx` hold the result in React state persisted to `localStorage`. Exists purely to get the frontend/backend round-trip pattern established (including a POST, not just GETs) before more screens get built on a hardcoded user.
- **Fix missing `APP_TIMEZONE` in local `.env`** (#48)
  - Present in `.env.example` since V0.0.10 but never actually set — without it, local-day bucketing was silently falling back to UTC.

### Known, disclosed limitations
- The cross-source duplication issue (documented since V0.0.16) is now directly visible to a user looking at a real day's food log, not just a database-level concern — worth prioritizing the actual reconciliation fix sooner now that it has a visible symptom (#65, #70).
- Login has zero real security — anyone can "log in" as any real user by typing their email, and every API endpoint trusts whatever `user_id` it's given with no authorization check. Fine for single-developer local use only.

## V0.0.21 — 2026-09-08 16:45
### Changes
- **Fix stale `README.md`** (#45)
  - Had the same "no application code exists yet" staleness as `doc/wiki/Home.md` did (already fixed in V0.0.18).

## V0.0.20 — 2026-09-08 16:30
### Changes
- **Fix missing `brand_name` on synced foods** (#44)
  - Spotted by the user noticing it looked wrong. My first check was incomplete — I confirmed Health Connect genuinely has no brand column, then checked exactly one live-API `food` resource, found no `brand` field, and wrongly concluded the API doesn't expose it at all. Checking several more (branded/packaged items specifically) showed a real `brand` field does exist — it's just conditionally present, only for actual packaged/branded foods, not generic ones — confirmed against real values ("Lay's", "Food Lion", "BelGioioso", "Quest", "Mission", "Great Value", etc.). `scripts/sync-google-health.php` was already fetching the `food` resource for gram conversion but never reading this field.
  - Fixed `fetchFoodServings()` to always surface `brand` when the food resource fetch succeeds, decoupled from whether a usable gram-conversion entry exists (previously the whole result collapsed to `null` if there was no `"gram"` serving entry, silently discarding brand info too). `findOrCreateFoodReal()`/`findOrCreateFoodFallback()` now match and store `brand_name` (via MySQL's `<=>` null-safe equality, since two foods sharing a name but differing only in brand — or one branded, one generic — are genuinely different catalog entries).
  - Re-ran the sync against the real account: 50 of 689 catalog foods now have a real brand; re-ran a second time immediately to confirm full idempotency (0 created/updated, only reused/skipped).
  - Known limitation, not fixed: `foods_db` rows created before this fix keep their incorrect `brand_name = NULL` — they aren't retroactively corrected (deletion isn't possible in this schema by design; a new, correctly-branded version was created instead going forward, matching how versioning already handles a genuine data difference). Old food_log_entries referencing the pre-fix rows still point at the less-complete version.

## V0.0.19 — 2026-09-08 16:00
### Changes
- **Fix stale `Database-Design-Patterns.md`** (#43)
  - Still documented fingerprint-based dedup and the `SRC`/`FIX`/`MOD` correction pattern as NutriPal's current approach — both were fully replaced this session (`api_uid`-only identity, versioning). Kept both original techniques as legitimate, still-generically-useful patterns (this doc is meant to be reusable across other projects), but added a "real-world postscript" to each explaining what NutriPal actually settled on instead and why, plus a new "Versioning" pattern section (previously undocumented here) with guidance on when to pick layered correction vs. versioning.

## V0.0.18 — 2026-09-08 15:30
### Changes
- **Fix stale `doc/wiki/Home.md` status section** (#42)
  - Still said "development is being restarted from scratch" and "no app code exists yet" — badly stale given the finished schema, both importers, and the live sync. Rewrote the Status section to reflect reality and flag the actual next milestone (there's still no application/UI at all — that's the real gap now, not the database layer).

## V0.0.17 — 2026-09-08 15:00
### Changes
- **Rewrite `sql/sample_data.sql` for the redesigned schema** (#41)
  - Still reflected the pre-redesign schema (`food_log_nutrients`, `SRC`/`FIX`/`MOD`, `food_name`/`brand_name`/`energy_kcal` directly on `food_log_entries`). Now uses the current strict `food_id` + `serving_amount` reference model: 10 catalog `foods_db` entries plus one genuine version fork (a real recipe change to "Oatmeal with Banana," not just a different quantity), each with a named real-world custom unit (`foods_db_custom_units`) and a representative `foods_db_nutrients` subset — including a hand-entered `LEUCINE` value, demonstrating what a manually-tracked micronutrient looks like now that versioning replaced the `SRC`/`FIX`/`MOD` system. No longer re-seeds lookups already covered by `sql/init_lookups.sql` (would collide on duplicate keys) — only adds the two `lut_data_source` rows that file deliberately leaves empty.
  - Verified by actually loading `sql/schema.sql` + `sql/init_lookups.sql` + `sql/sample_data.sql` in sequence into a throwaway database (`nutripal_sampletest`/`nutripal_sampletest_hist`) and querying the joined result before dropping it — not just reviewed for syntax.

## V0.0.16 — 2026-09-08 14:00
### Changes
- **Build the live Google Health API sync script** (#36)
  - The last major "not yet implemented" item. Covers all 9 categories (nutrition, steps, heart rate, HRV, daily resting heart rate, sleep, weight, height, exercise); `daily_resting_heart_rate` gets real data for the first time. Two modes: default incremental (last 7 days, matching `doc/wiki/Data-Sync.md`'s original design) or `--full`/`--days=N`.
  - Two dedup strategies, chosen per category based on what the live API actually provides (confirmed against real responses, not assumed): `nutrition-log`/`sleep`/`exercise`/`weight`/`height` have a stable per-point ID → real upsert-if-changed via `api_uid`; `daily-resting-heart-rate` upserts via its existing `(user_id, reading_date)` natural key; `steps`/`heart-rate`/`heart-rate-variability` have **no** stable ID at all (confirmed: no `name` field on those dataPoints) and the schema's `BEFORE DELETE` trigger rules out a delete-and-reinsert reconcile, so these three use insert-missing dedup against existing `reading_time` values instead — disclosed as a real, deliberate scope reduction from "reconcile," not a silent gap.
- **Add real gram-accurate serving units for API-sourced nutrition entries** (#37)
  - Closing the gap this session's Health Connect quantity-problem fix had to placeholder around: each entry's `food` resource reference is fetched (cached per run) and its `servings[]` list used to derive true grams for whatever unit was actually logged (verified end-to-end: "1 tortilla" resolved to exactly the ~51g computed by hand during the earlier comparison pass; "1 medium apple" → 167g, "1 oz" → 28g, "1 egg" → 50g — all real, not placeholders). Falls back to the same ratio-based placeholder-unit approach as `import-health-connect.php` when a food has no gram entry or the logged unit can't be matched.
- **Fix `exercise_sessions.distance` overflow/unit-mismatch bug** (#38)
  - Not previously caught because Health Connect's exercise data has no distance column to populate at all: `exercise_sessions.distance` `DECIMAL(10,4)` overflows on ordinary walking distances once mixed with millimeter-scale values (a 6km walk = 6,148,000mm, exceeding the column's 6-integer-digit budget) — MySQL silently clamped every value to `999999.9999`, which also broke idempotency (the clamped stored value never matched the real incoming value, so every re-sync issued a pointless update). Root cause was really a unit mismatch — Takeout's miles and the API's millimeters share one column at wildly different scales. Fixed by standardizing `distance` to **meters** for every source at ingest time (added a `meter` row to `unit_conversions`) rather than widening the column — confirmed `DECIMAL(14,0)` and `DECIMAL(14,4)` cost the identical 7 bytes of storage (MySQL's DECIMAL packs by total digit count, not by where the decimal point falls), so widening would have bought nothing and still lost Takeout's fractional-mile precision.
- **Fix case-insensitive data-source-name collision crash** (#39)
  - `lut_data_source.name` uses a case-insensitive collation, so the live API's `"FITBIT"` (from `dataSource.platform`) and Health Connect's already-imported `"Fitbit"` (an app display name) collided as duplicates at the DB level even though the in-memory PHP cache treated them as different strings — `findOrCreateDataSource()`/`findOrCreateActivityType()` now catch that specific duplicate-key error and re-resolve the existing row instead of crashing.
- **Verify sync idempotency against real account data** (#40)
  - Ran the sync three times in a row against the same window and confirmed the third run reported `skipped` (no real change) for every single row across every category, with zero spurious updates, before running the real default 7-day sync against the live account.

### Known, disclosed limitations (not solved this pass)
- **Cross-source duplication risk between Health Connect and the live API is not resolved.** (Fixed for sleep/exercise/weight in V0.1.6, #65; for food log entries in V0.1.9, #70.) Health Connect's `api_uid` (its own local `uuid`) and this sync's `api_uid` (the live API's cloud dataPoint id) are different ID spaces for the same real-world sleep session / exercise session / weight reading / food log entry — the `UNIQUE(user_id, api_uid)` constraint can't detect they're the same event. Same class of problem as the already-documented "upsert priority across sources" open item, just newly live. No automated mitigation exists yet; picking a sync window that starts after the last Health Connect export's own coverage avoids it in practice for now.
- The real-gram custom units this sync creates are not retroactively used to correct Health-Connect-created placeholder units for what might be the same real food (automatic reconciliation done in V0.1.9, #70; a manual review UI is still open, #137).
- `--full` mode's logic was reviewed but not exercised against the real account's entire history this pass (would mostly re-cover what Health Connect's bulk import already has, and take a long time against years of heart-rate data) — only the default incremental path and small explicit `--days` windows were actually run.
- **`lut_activity_type` mapping stays a plain find-or-create** (#138) keyed on the API's raw `exerciseType` string (`API_WALKING` etc.), same non-canonical state as the Health Connect importer.

## V0.0.15 — 2026-09-08 12:00
### Changes
- **Cross-check Health Connect data against the live Google Health API** (#34)
  - `scripts/fetch-recent-compare.php`, an exploratory script that pulls the last N days of every relevant data type from the live Google Health API and writes each to its own temp JSON file (not the database), to cross-check against what's already in the DB from the Health Connect bulk import.
  - Cross-source comparison, 10-day window: nutrition, HRV, exercise, and sleep counts matched the DB exactly per day once both sides were bucketed by the same local calendar day (the API returns local civil dates; comparing against the DB's raw UTC dates made a day look "missing" that wasn't — a bucketing artifact, not a data gap). Steps/heart-rate matched almost exactly, with the handful of day-level discrepancies consistent with the already-documented multi-device step overlap. Found one genuine (not artifact) discrepancy: a Health-Connect-sourced weight reading on one date with no corresponding entry in the live API's history for the same date.
- **Discover the live API's nutrition-log data already has real serving units (no "quantity problem")** (#35)
  - Every entry checked included a real `serving` field (amount + human unit, e.g. "2 oz") and a link to a canonical `food` resource carrying true gram-conversion multipliers per unit. Health Connect has neither. Recorded as a project memory (`google_health_api_food_data_quality`) since it changes the best fix path for the placeholder "reported serving" units once the live-API sync is built — likely no manual correction or external reference database needed for foods the API has already seen.

## V0.0.14 — 2026-09-08 10:00
### Changes
- **Create real `nutripal`/`nutripal_hist` databases and lookup-seed script** (#26)
  - Added `sql/init_lookups.sql`, a canonical reference-data initialization script (sentinels, units, and every small-closed-vocabulary lookup) distinct from the illustrative `sql/sample_data.sql`. Added `src/Database.php` (minimal PDO connection helper) and `DB_HOST`/`DB_NAME`/`DB_USER`/`DB_PASS` to `.env`/`.env.example`.
  - Added `/storage/import-logs/` and `/ref/` to `.gitignore` — both can contain real personal health data and must never be committed.
- **Build and run the Takeout importer against a real ~3-year export (~12.1M rows)** (#27)
  - `scripts/import-takeout.php`, ran end-to-end against a real ~3-year Takeout export as a full-scale schema test (~12.1 million rows, 11.5M heart-rate readings). Found and fixed three real gaps the design review missed: `lut_meal_type` missing `BEFORE_BREAKFAST`/`BEFORE_LUNCH`/`AFTER_DINNER`; `lut_sleep_stage_type` missing the older `CLASSIC`-mode vocabulary (`ASLEEP`/`RESTLESS`/`UNSPECIFIED`, 264 of 58,010 rows, backfilled via `scripts/import-takeout-supplement-sleep-stages.php`); nutrition data's literal `N/A` sentinel string (~21% of values) was silently casting to `0.0` instead of being treated as unreported.
- **Decide to drop Google Takeout as an active source in favor of Health Connect + the live API** (#28)
  - Inspected a real Android Health Connect SQLite export and, based on real category-by-category tradeoffs, decided to drop Google Takeout as an active ingestion source entirely (nutrition, sleep, steps, heart rate, weight/height, exercise) in favor of Health Connect (bulk history) + the live Google Health API (incremental sync) going forward. Takeout's importer/schema-support code is kept as a historical artifact, not deleted; `lut_ingestion_source`'s `google_takeout` row is kept for traceability of already-imported rows but documented as deprecated.
- **Redesign `food_log_entries`/`foods_db` to a strict reference + versioning model** (#29)
  - A log entry now always points at exactly one `foods_db` row plus a `serving_amount` multiplier, rather than duplicating nutrition data inline. Dropped the `SRC`/`FIX`/`MOD` nutrient-modifier system (and `lut_nutrient_value_type`) entirely — a genuine change to a food's nutrition now creates a new `foods_db` version instead of a competing override row. Moved `ingestion_source_id`/`data_source_id`/`api_uid` onto the log (provenance of an event), out of the catalog (a property of a food). Dropped `fingerprint` everywhere in favor of `api_uid` as the sole identity key, with a disclosed gap: `steps_readings`/`heart_rate_readings`/`heart_rate_variability_readings`/`sleep_stages` now have no DB-level duplicate guard at all, deferred to application logic.
- **Rewrite `sql/schema.sql` for the redesigned model and verify via a throwaway database** (#30)
  - Rewrote end to end reflecting the above (dropped `food_log_nutrients` entirely — nutrition is now always derived by joining through `food_id`; drastically simplified `sleep_sessions`, removing every score/duration column Health Connect has no concept of). Verified via a full throwaway-database test (structural audits across all 30 tables/hist tables/60 triggers, plus live insert/update/delete/trigger checks) before touching real data.
- **Build the Health Connect importer (78-table SQLite export)** (#31)
  - `scripts/import-health-connect.php`, covering nutrition, weight, height, steps, heart rate (parent + series), HRV, sleep (sessions + stages), and exercise. Found and fixed two real bugs by actually running the import and inspecting results rather than trusting a clean-looking log: `PDOStatement::fetch()` returning `false` (not `null`) on no match was silently producing wrong version numbers for brand-new foods; and all four `catch` blocks checking the whole SQLSTATE `23000` class (rather than MySQL's specific error code 1062) were mislabeling a real foreign-key failure — a missing `lut_serving_unit` seed row for `'gram'` — as "2,376 duplicates," silently zeroing out `food_log_entries` with no visible error.
- **Fix the "quantity problem" for Health Connect nutrition data** (#32)
  - Health Connect's `nutrition_record_table` reports absolute totals with no serving/mass field at all, so the original tolerance-based `foods_db` version-matching couldn't distinguish "same food at a different amount" from "a genuinely different food" — confirmed concretely when "Yellow Onion" produced 41 near-duplicate versions that were actually clean multiples of one another (the same onion at ~41 unknown quantities). Fixed with ratio-based matching (checks every existing version sharing a food's name for a single scale factor that consistently explains the incoming energy/protein/carb/fat readings) plus a per-food placeholder custom unit ("reported serving", `equivalent_amount = 100`) so a future real-world correction only ever touches one row, never historical log entries.
- **Full real-data Health Connect import as schema validation** (#33)
  - Wiped and recreated the real `nutripal`/`nutripal_hist` databases fresh and re-ran the full Health Connect import as the official test of the redesigned schema: 220,237 steps, 2,854,655 heart-rate readings, 22,036 HRV readings, 710 sleep sessions / 33,121 stages, 2,015 exercise sessions, 520 weight / 1 height reading, and 2,376 nutrition log entries resolving to 583 catalog foods (531 distinct names) — zero errors. Verified the quantity fix directly: max versions for any one food name dropped from 41 to 4, zero log entries landed with an extreme serving ratio.

### Known bugs (not yet fixed)
- `sql/sample_data.sql` is now stale/incompatible with the redesigned schema (still reflects the old `food_name`/`brand_name`/`food_log_nutrients`/`SRC`-`FIX`-`MOD` shape) — not rewritten this pass. (Fixed in V0.0.17, #41.)
- **`lut_activity_type` isn't a true canonical mapping yet** (#138) — both importers do a plain find-or-create keyed on each source's raw activity code, so the same real-world activity can produce multiple rows across sources.
- `daily_resting_heart_rate`'s multiple-readings-per-day question (whether Health Connect can report more than one per day, and how to dedup if so) was left unresolved — no `api_uid` added, structurally unchanged from V0.0.13. (Effectively answered by V0.0.16's `(user_id, reading_date)` natural-key upsert.)
- Health Connect's `exercise_session_record_table` has no calories/distance/steps/average-heart-rate columns (stored in separate generic time-series tables with no FK back to the session) — not cross-referenced; those four columns are left `NULL` for HC-sourced exercise sessions. GPS route points are not imported, only a `has_gps` flag. (Partially mitigated by V0.1.7's cross-source merge, #67, for sessions with a matching live-API copy.)

### Planned (not yet implemented)
- **UI to correct the placeholder "reported serving" custom units created by the quantity-problem fix** (#137): edit a food's unit directly, search for a specific food to adjust, and a post-sync/import review list of every food still on the placeholder unit (e.g. eggs → 1 egg, cottage cheese → 1 cup/4oz, chicken → ounces) — must keep historical log totals unchanged when a unit is corrected.
- **Real canonical mapping for `lut_activity_type`** (#138) across both Health Connect's and the live API's activity vocabularies.
- Matching catalog foods against a real reference nutrition database (e.g. USDA FoodData Central) for true gram-accurate quantities, rather than the placeholder unit. (Superseded — V0.0.16's real-gram data via Google's own API accomplished this without needing USDA.)
- Rewrite or retire `sql/sample_data.sql` to match the redesigned schema. (Done in V0.0.17, #41.)
- Resolve the `daily_resting_heart_rate` multiple-readings-per-day open question. (Effectively answered by V0.0.16.)
- **Build the "recipe" template feature** (#143) (a separate, not-yet-designed concept — food log entries stay ingredient-level and never reference a recipe directly).
- Build the live-API-to-database sync (currently only bulk importers write to the database). (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)

## V0.0.13 — 2026-09-07 22:00
### Changes
- **Complete table-by-table schema review for remaining health-data tables** (#17)
  - `steps_readings`, `heart_rate_readings`, `measurements` [weight/height/etc.], `exercise_sessions`, `sleep_sessions`/`sleep_stages`, grounded in real API responses and a direct inspection of the real Takeout export zip rather than assumptions — every change below was driven by an actual data-shape finding, verified against a live throwaway MariaDB database after each table.
  - Split the schema into two databases (`nutripal` + `nutripal_hist`, see #14) so audit history can be backed up/archived independently of live data; documented the Bluehost account-prefix deploy caveat.
  - Every change re-verified end-to-end against a throwaway MariaDB database (insert/update/delete-block/FK enforcement), never touching the real `nutripal` database.
- **Discover and model heart-rate-variability, daily-resting-heart-rate, recording-method, and activity-type concepts** (#18)
  - New tables discovered via real data, not originally modeled: `heart_rate_variability_readings` and `daily_resting_heart_rate` (distinct metrics from continuous bpm, confirmed via the live API); `lut_recording_method` (a genuinely new cross-cutting concept — *how* a reading was captured, e.g. `ACTIVELY_MEASURED`/`MANUAL`/`DERIVED` — present on every metric checked, added to steps/heart-rate/HRV/resting-HR/measurements/exercise/sleep); `lut_activity_type` (resolving Takeout's numeric Fitbit activity codes and the API's string `exerciseType` into one canonical vocabulary); `lut_sleep_type` (`CLASSIC`/`STAGES`).
- **Merge weight/height into a generic `measurements` table** (#19)
  - `weight_readings` and `height_readings` (height also newly added) merged (`measurement_type_id`/`value`/`unit_id`, per the "generic characteristic/value/unit table" pattern also documented in `doc/wiki/Database-Design-Patterns.md`) — extensible to future body metrics like blood pressure or body fat % without new tables. `unit_conversions`/`lut_dimension` extended with length/pressure/ratio dimensions to support it.
- **Fix sleep-score column type** (#20)
  - Sleep score columns (`overall_score` etc.) were `TINYINT UNSIGNED` but real Takeout values are floats and use `-1` as a "not computed" sentinel — neither fits an unsigned integer; changed to `DECIMAL(6,2)` with `-1` translated to `NULL` at ingest.
- **Add missing dedup mechanism for `sleep_stages`** (#21)
  - `sleep_stages` had no `fingerprint`/`ingestion_source_id` at all — confirmed via real data that the live API returns stage-level detail with no native ID, meaning API-sourced stages had no dedup mechanism whatsoever; fixed.
- **Remove redundant `exercise_sessions.device_name` column** (#22)
  - Duplicated `data_source_id` (confirmed both sources report exactly one "which device" concept).
- **Fix free-text `exercise_sessions.distance_unit`** (#23)
  - Converted to `distance_unit_id` (`unit_conversions`-backed) — confirmed Takeout genuinely varies distance units (miles observed) while the API always reports fixed millimeters.
- **Link `food_log_entries` to `foods_db` and cache last-used serving** (#24)
  - Added `food_log_entries.food_id` (nullable FK → `foods_db`) and `foods_db_last_used.last_serving_amount`/`last_serving_unit_id`, closing the previously-open `food_log_entries` ↔ `foods_db` linkage gap.
- **Correct stale Takeout export documentation** (#25)
  - Takeout's `UserSleeps`/`UserSleepStages`/`UserSleepScores` files are actually split into several multi-year-range CSVs, not single all-history files as previously documented; discovered a second, richer legacy Fitbit-format sleep export (`Global Export Data/sleep-*.json`) and several unreviewed sleep-adjacent files (sleep profile, a second sleep-score source, sleep temperature, respiratory rate).

### Known bugs (not yet fixed)
- **Multi-device step overlap can double-count daily step totals if summed naively** (#139) — deliberately deferred to application/aggregation logic (see `doc/wiki/Database-Schema.md` Open Items), not a schema gap.

### Planned (not yet implemented)
- **Real canonical mapping for `lut_activity_type`** (#138) across Fitbit numeric IDs and the API's string enum — real reference-data work, deferred to ingest-time implementation.
- Deciding which raw Takeout sleep format the importer will parse, and reviewing the newly-discovered sleep-adjacent Takeout files. (Moot — Takeout dropped as an active source in V0.0.14, #28.)
- Create the actual MySQL database and run `sql/schema.sql` (needs confirmation before touching the local database, per project convention). (Done in V0.0.14, #26.)
- Build `scripts/import-takeout.php` to parse an extracted Takeout export and load it into the schema. (Done in V0.0.14, #27.)
- Build the live-API-to-database sync (currently the fetch scripts only write debug JSON, not the DB). (Done in V0.0.16, #36.)
- **Meal planning — logging an intended future meal, distinct from a consumed entry** (#144)
- React frontend. (Done in V0.1.0, #46.)

## V0.0.12 — 2026-09-06 16:00
### Changes
- **Verify schema end-to-end against a throwaway database** (#15)
  - `sql/schema.sql` + `sql/sample_data.sql`, actually run: loaded into throwaway databases (`nutripal_verify`/`nutripal_verify_hist`, never touching real `nutripal`), confirmed table/trigger counts, exercised the cross-schema history trigger (update + inspect the resulting hist row), the delete-block trigger, and FK enforcement — then dropped both throwaway databases.
- **Fix missing `DEFAULT CURRENT_TIMESTAMP` on `_hist` table timestamp columns** (#16)
  - Every `_hist` table's `valid_start_ts`/`valid_end_ts`/`created_ts` columns were `TIMESTAMP NOT NULL` with no explicit `DEFAULT`. MariaDB (this XAMPP install's config: `explicit_defaults_for_timestamp=0`, `NO_ZERO_DATE` in `sql_mode`) rejects that for any `TIMESTAMP NOT NULL` column beyond the first one in a table, since it can't fall back to its usual implicit zero-date default. Fixed by adding `DEFAULT CURRENT_TIMESTAMP` to all three columns across all 25 hist tables — harmless, since the trigger always supplies real values explicitly; this only satisfies MariaDB's DDL validation. Would have blocked schema creation entirely on first real use.

## V0.0.11 — 2026-09-06 15:00
### Changes
- **Design `food_log_entries` ↔ `foods_db` linkage** (#13)
  - Added nullable `food_id` (FK → `foods_db`) to `food_log_entries`, recording which catalog version an entry was logged from without live-joining for display (nutrition stays a logging-time snapshot, so re-versioning a catalog food never rewrites past logs). The quantity side needed no new column — `serving_amount`/`serving_unit_id` already resolve to a total gram/mL amount against `foods_db`'s per-100 nutrition.
  - Added `last_serving_amount`/`last_serving_unit_id` to `foods_db_last_used`, caching the last quantity logged for a food so "log again" can prefill the same serving, not just identify the food.
  - Updated `sql/schema.sql` (both tables + their `_hist` tables and update triggers) and `doc/wiki/Database-Schema.md` accordingly; `sql/sample_data.sql` needed no change since it doesn't yet populate `foods_db`.
- **Split schema into `nutripal` + `nutripal_hist` databases** (#14)
  - `nutripal` (live data) and `nutripal_hist` (every `_hist` audit table), so history can be backed up/archived on its own cadence. Every `_hist` table and every trigger's history-insert target is now schema-qualified. Documented as a general reusable pattern in `doc/wiki/Database-Design-Patterns.md`, and flagged clearly in `sql/schema.sql`'s header that Bluehost's account-specific database-name prefix (`theshaf2_`) must be substituted for `nutripal_hist` before deploying there, since the hist schema name is baked literally into every trigger body.

### Planned (not yet implemented)
- Finish the table-by-table schema review for `steps_readings`, `heart_rate_readings`, `weight_readings`, `exercise_sessions`, `sleep_sessions`/`sleep_stages`. (Done in V0.0.13, #17.)
- **Meal planning — logging an intended future meal, distinct from a consumed entry** (#144)
- Create the actual MySQL database and run `sql/schema.sql` (needs confirmation before touching the local database, per project convention). (Done in V0.0.14, #26.)
- Build `scripts/import-takeout.php` to parse an extracted Takeout export and load it into the schema. (Done in V0.0.14, #27.)
- Build the live-API-to-database sync (currently the fetch scripts only write debug JSON, not the DB). (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)

## V0.0.10 — 2026-09-06 14:00
### Changes
- **Decide to support Google Takeout as a second ingestion source** (#11)
  - For fast new-user initialization (full history at once) and periodic completeness checks against the incremental API sync.
  - Surveyed the Takeout export format across all 6 confirmed-available categories (food, steps, exercise, heart rate, sleep, weight) — documented in `doc/wiki/Database-Schema.md` (per-month CSVs for most types, a single all-history CSV for nutrition/weight, legacy Fitbit-format JSON for exercise, and ID-bearing CSVs for sleep/sleep stages/sleep scores).
- **Design core schema patterns: lookup tables, audit history, SRC/FIX/MOD nutrient correction, multi-user readiness, `foods_db` catalog** (#12)
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
- Takeout nutrition rows have no energy/calorie field — `energy_kcal` is estimated from macros for Takeout-sourced food entries and flagged `is_energy_estimated`. (Moot — Takeout dropped as an active source in V0.0.14, #28.)

### Planned (not yet implemented)
- Finish the table-by-table schema review for `steps_readings`, `heart_rate_readings`, `weight_readings`, `exercise_sessions`, `sleep_sessions`/`sleep_stages`. (Done in V0.0.13, #17.)
- Design the `food_log_entries` ↔ `foods_db` linkage (which catalog food, what quantity) — the unit half is resolved, this part isn't. (Done in V0.0.11, #13.)
- **Meal planning — logging an intended future meal, distinct from a consumed entry** (#144) (Google Health has no such capability; surfaced during this schema review.)
- Create the actual MySQL database and run `sql/schema.sql` (not done yet — needs confirmation before touching the local database, per project convention). (Done in V0.0.14, #26.)
- Build `scripts/import-takeout.php` to parse an extracted Takeout export and load it into the schema. (Done in V0.0.14, #27.)
- Build the live-API-to-database sync (currently the fetch scripts only write debug JSON, not the DB). (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)

## V0.0.9 — 2026-09-05 12:00
### Changes
- **Expand OAuth scope and survey available Google Health data types** (#10)
  - Expanded requested OAuth scope (`src/GoogleOAuth.php`) beyond nutrition-only to also cover `activity_and_fitness.readonly`, `health_metrics_and_measurements.readonly`, and `sleep.readonly` — decided to survey what's available across activity, heart rate/vitals, sleep, and weight/height before continuing further food-only work.
  - Added `scripts/fetch-metrics-test.php`, an exploratory script that probes 18 candidate data types (steps, exercise, heart rate, sleep, weight, etc.) and reports which ones actually have data in this account, saving raw responses to `storage/debug-metrics/` (gitignored).
  - Ran the survey: real data found for steps, distance, active-minutes, active-zone-minutes, exercise, active-energy-burned, heart-rate, heart-rate-variability, daily-resting-heart-rate, sleep, weight, height (plus sparse data for oxygen-saturation and body-fat); no data for vo2-max/blood-glucose; `floors` and `total-calories` aren't queryable via the `list` method at all (only `reconcile`/`rollup`/`dailyRollup` — different API shape, deferred).

### Planned (not yet implemented)
- Next build target: **steps + exercise** (activity data, toward the activity/food/weight correlation goal).
- Design MySQL schema based on the observed response shape(s). (Done in V0.0.10, #12.)
- Integrate fetch(es) into the actual app (currently standalone scripts) and persist to the database. (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)

## V0.0.8 — 2026-08-10 20:00
### Changes
- **Explore live Google Health nutrition-log API** (#9)
  - Added `scripts/fetch-nutrition-test.php`, an exploratory CLI script that fetches real `nutritionLog` data points from the Google Health API for the last N days (default 10).
  - Discovered the `filter` query param is rejected for the `nutritionLog` data type (unlike the documented generic interval-filter pattern) — worked around by paginating the unfiltered, newest-first list and filtering client-side by `civilStartTime`.
  - Confirmed real data end-to-end: 116 entries over the last 10 days, sourced from Fitbit (`dataSource.platform: "FITBIT"`), with 22 distinct nutrient types per entry — documented full response shape in `doc/wiki/Data-Sync.md`.
  - Noted a data-quality observation: 4 of the last 10 days had zero logged entries — needs a spot-check against the source app, not assumed to be a sync bug.

### Planned (not yet implemented)
- Design MySQL schema based on the observed response shape. (Done in V0.0.10, #12.)
- Integrate the fetch into the actual app (currently a standalone script) and persist to the database. (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)

## V0.0.7 — 2026-08-10 19:00
### Changes
- **Add local dev server start/stop scripts** (#8)
  - `start-services.bat`/`.ps1` and `stop-services.bat`/`.ps1` to manage the local PHP dev server (port 8080) — `.bat` wrappers run PowerShell with `-ExecutionPolicy Bypass` for that invocation only, matching the pattern used in the other local web projects, so no system-wide execution policy change is needed. Never touches XAMPP/MySQL. Verified both start and stop work correctly.

## V0.0.6 — 2026-08-10 18:00
### Changes
- **Create Web-application OAuth client and complete first live Google login** (#7)
  - Created a **Web application**-type Google OAuth client (redirect URI `http://localhost:8080/auth-callback.php`) to replace the unusable Desktop-app client; recorded in `doc/credentials/google-health.md`.
  - Wired real credentials into local `.env` (gitignored).
  - Ran the full OAuth flow end-to-end against real Google login: consent screen, callback, and token exchange all verified working; `storage/google-tokens.json` confirmed populated with `access_token`, `refresh_token`, and the correct `nutrition.readonly` scope.

### Planned (not yet implemented)
- Design MySQL schema and swap `TokenStore`'s JSON file for a database-backed store. (MySQL schema designed in V0.0.10, #12; `TokenStore` itself was never actually migrated off the JSON file — still true today.)
- Fetch and store actual nutrition data using the obtained access token. (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)

## V0.0.5 — 2026-08-10 17:00
### Changes
- **Implement Google Health OAuth flow (login/callback, token storage)** (#6)
  - Added first PHP application code: `public/` (front-end entry points), `src/` (`GoogleOAuth`, `TokenStore`, `Env`).
  - Implemented the Google Health OAuth flow: `auth-login.php` redirects to Google's consent screen with the `googlehealth.nutrition.readonly` scope (`access_type=offline`, `prompt=consent` to get a refresh token); `auth-callback.php` verifies CSRF state, exchanges the auth code for tokens, and stores them.
  - Token storage is a temporary local JSON file (`storage/google-tokens.json`, gitignored) until the MySQL schema is designed.
  - Added `.env.example` / `.env` support via a small dependency-free `Env` loader (no Composer install needed for this).
  - Verified locally with PHP's built-in server (`php -S`): homepage loads without config, auth routes fail with a clear error when unconfigured, and the generated Google auth URL matches Google's documented format exactly.

### Known bugs (not yet fixed)
- Stored Google Health OAuth credentials (`doc/credentials/google-health.md`) are a **Desktop app** client; a **Web application**-type client must be created in Google Cloud Console (with the real redirect URI) before this flow can be tested end-to-end with real credentials. (Fixed in V0.0.6, #7.)

### Planned (not yet implemented)
- Design MySQL schema and swap `TokenStore`'s JSON file for a database-backed store. (MySQL schema designed in V0.0.10, #12; `TokenStore` itself was never actually migrated off the JSON file — still true today.)
- Fetch and store actual nutrition data using the obtained access token. (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)

## V0.0.4 — 2026-08-10 16:00
### Changes
- **Scope first milestone: Google Health food-data sync only** (#5)
  - Scoped first milestone: Google Health food data sync only (calories/nutrients), activity and weight sync deferred.
  - Added `doc/wiki/Data-Sync.md` documenting sync strategy: routine incremental sync reconciles (upserts) the last 7 days on every run to catch backfilled/edited entries, plus a separate manual full-resync option for anything older.

### Known bugs (not yet fixed)
- Stored Google Health OAuth credentials (`doc/credentials/google-health.md`) are a **Desktop app** client; NutriPal is a PHP web app, so a **Web application**-type client with proper redirect URIs needs to be created before implementing the OAuth flow. (Fixed in V0.0.6, #7.)

### Planned (not yet implemented)
- Scaffold the PHP + MySQL + React project structure. (Done progressively: PHP in V0.0.5 #6, MySQL schema in V0.0.10 #12, React in V0.1.0 #46.)
- Google Health OAuth flow (web application client) and food-data sync implementation. (Done in V0.0.5/V0.0.6, #6/#7.)
- Local MySQL schema for food log entries. (Done in V0.0.10, #12.)

## V0.0.3 — 2026-08-10 15:00
### Changes
- **Decide tech stack: PHP/MySQL backend + React SPA, targeting Bluehost** (#4)
  - Decided tech stack: PHP + MySQL backend (JSON API) developed locally on XAMPP, React SPA frontend, targeting Bluehost shared hosting for eventual deployment (auth and env-based secrets designed in from the start, deployment itself deferred).
  - Added `doc/wiki/Architecture.md` documenting the stack decision and rationale.
  - Expanded scope in `README.md` / `doc/wiki/Home.md`: added custom meal creation and fast repeat-meal logging (e.g. near-identical daily breakfast with minor tweaks) to the feature list.

### Planned (not yet implemented)
- Scope and build the first slice of functionality. (Done progressively starting V0.0.4, #5.)
- All application code (currently nothing exists beyond docs/scaffolding). (Done in V0.1.0, #46.)

## V0.0.2 — 2026-08-10 14:00
### Changes
- **Add README and scope the NutriPal rebuild** (#3)
  - Added root `README.md`.
  - Scoped the rebuild in `README.md` / `doc/wiki/Home.md`: NutriPal will be a web app for viewing/analyzing Google Health (formerly Fitbit) data from the desktop, with enhanced macro/micronutrient analysis and activity (running, workouts) vs. weight/food correlation. Building incrementally rather than all at once.

### Planned (not yet implemented)
- Decide tech stack for the new build. (Done in V0.0.3, #4.)
- All application code (currently nothing exists beyond docs/scaffolding). (Done in V0.1.0, #46.)

## V0.0.1 — 2026-08-10 13:00
### Changes
- **Fix broken wiki auto-sync GitHub Actions workflow** (#2)
  - Fixed `.github/workflows/main.yml` (Auto Update Wiki): the wiki-repo push URL was malformed (`@://github.com` instead of `@github.com/`, and `{{ github.repository }}` missing its `$` so it was never interpolated), causing the push step to fail on every run.
  - Added explicit `permissions: contents: write` to the workflow so `GITHUB_TOKEN` can push to the wiki repo regardless of repo/org default token permissions.

### Known bugs (not yet fixed)
- The workflow still requires the GitHub wiki to be manually initialized (Settings → Features → Wiki → create a first page) before its "Checkout Wiki Repo" step can succeed — not yet confirmed done for this repo.

## V0.0.0 — 2026-08-10 12:00
### Changes
- **Initialize NutriPal git repository and project scaffolding** (#1)
  - Initialized local git repository for NutriPal.
  - Added `.gitignore` excluding `doc/archive/` (reference material stays local-only, never committed).
  - Added `doc/credentials/` for credential reference notes (stays local-only, never committed — see `.gitignore`).
  - Added `doc/wiki/` with initial `Home.md`.
  - Added this `CHANGELOG.md`.

### Planned (not yet implemented)
- Decide and scope the actual NutriPal app going forward (an earlier prototype exists in `doc/archive/` as reference material for this rebuild)
