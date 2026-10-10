# Changes removed from CHANGELOG.md when adopting the governance standard

Record, 2026-10-09. The standard allows no "Known bugs" or "Planned" sections in the changelog (guide 03, section 7.3). These sections were taken out of V0.0.0 to V0.14.1 verbatim and kept here. They are not tracked as tickets; check the open issues before relying on any of them.

### V0.14.1 — Planned (not yet implemented)
- **Build production build/deploy pipeline (Vite `dist/` → Bluehost)** (#149)
  - Local dev runs the React app unbuilt via `vite dev` (frontend/, port 5173, proxying `/api` to the PHP backend on :8080 - see `start-services.ps1`); Bluehost shared hosting won't run that dev server, so production needs `npm run build` (in `frontend/`) and the resulting `frontend/dist/` output deployed alongside the PHP backend instead.


### V0.14.1 — Known limitations (not addressed this pass)
- The two placeholder `foods_db` rows the Tomato entries used to point at (a stale real-gram match and an inconsistent earlier version) are now permanently unreferenced but can't be deleted (`trg_foods_db_bd` forbids it, like every table in this schema) - harmless, matches this codebase's existing precedent for orphaned placeholder rows.
- **Build a UI to review/correct placeholder "reported serving" units per-food** (#137)
  - Previously discussed, not yet built - would have caught this class of bug sooner than a from-scratch API-log audit.
- **(Won't fix / accepted limitation) Liquid foods with no gram/gramme conversion default to "reported serving"** (#150)
  - Confirmed real examples: "Tomato Basil Sauce", "Original Unsweetened Almondmilk", "Marinade, Teriyaki". Their Google food resource only offers volume-based conversions (ml/fl oz/cup, or nothing at all) with no gram pivot - resolving these would require assuming a density (e.g. 1mL ≈ 1g), which the user deliberately chose not to do, since it would be wrong for oils/syrups/thick liquids. Kcal display is already correct either way.
- **(Won't fix / accepted limitation) English/French unit-name mismatch within a single food's catalog entry (oz vs. once)** (#151)
  - Real case: a "Fat Free Cottage Cheese" entry reports its unit as "oz", but that food's own serving list only defines the French "once"/"onces liquides" for the same physical unit - the English label the entry itself uses isn't present to match against. Fixing this would need a language-alias table (oz↔once, tsp↔cuillère à café, etc.); deliberately not built, since one confirmed case doesn't reveal how many others like it exist in the catalog, and a wrong alias would be worse than the honest fallback already in place.


### V0.14.0 — Known limitations (not addressed this pass)
- **Support real multi-user sync (script hardcodes `$userId = 2`)** (#142)
  - `login_attempts`/`last_sync_completed_at` are per-`user_id`, but the sync script itself still hardcodes `$userId = 2` (this app is still single-user) - ready for multi-user, not exercised by it yet.


### V0.13.0 — Known limitations (not addressed this pass)
- **Reconcile steps cross-source duplication properly (not just pick-a-winner heuristic)** (#139)
  - The Fitbit/Phone classification is name-based (`Fitbit`, `Charge 5` = wearable; everything else, including Fitbit's own phone-fallback feature `MobileTrack` = Phone) - a future new device name would silently fall into "Phone" until added to the wearable list.


### V0.12.0 — Known limitations (not addressed this pass)
- **Map "Aerobics" to an exact `lut_activity_type` row** (#146)
  - `Exercise Class` is used as the closest real match. A future source reporting running/treadmill activity under a name not in the matched list won't count toward the observed estimate until added.


### V0.11.0 — Known limitations (not addressed this pass)
- **Fix Feb-29 birth-date edge case in Max HR age calculation** (#145)
  - Rolls to Mar 1 in a non-leap current year when computing "this year's birthday" (`DateTimeImmutable::setDate` behavior) — affects one specific day, once every ~4 years, for leap-birthday users only.


### V0.10.0 — Known limitations (not addressed this pass)
- **Fix "Expand all" Year-view performance across Food/Heart Rate/Sleep** (#141)
  - Fully expanding a full Year view via the toolbar's "Expand all" is dramatically heavier for Sleep than the same action on Food or Heart Rate (already-logged as heavy in V0.8.0/V0.9.0) — a real night's stage data is much more fine-grained (tens of segments per session, each needing two formatted timestamps for its tooltip) than either of those pages' per-day content, and mounting a full year of it at once measured well over a minute and briefly made the tab unresponsive during testing. Collapsed-by-default rendering (every other view and action) stays fast; only the explicit full-Year-expand action is this heavy.


### V0.9.0 — Known limitations (not addressed this pass)
- **Fix "Expand all" Year-view performance across Food/Heart Rate/Sleep** (#141)
  - Fully expanding a full Year view via the toolbar's "Expand all" mounts every day at once and takes real time (tens of seconds) — same tradeoff already logged for Food in V0.8.0; collapsed-by-default rendering (the common case) stays fast.


### V0.8.0 — Known limitations (not addressed this pass)
- "Log in" is not a reachable menu state — see V0.7.0's note below, still true, not addressed here either.
- **Fix "Expand all" Year-view performance across Food/Heart Rate/Sleep** (#141)
  - Fully expanding a Year view via the toolbar's "Expand all" mounts the whole year's data at once and can be slow — collapsed-by-default rendering (the common case) is fast; only the explicit full-expand action is heavy.


### V0.7.0 — Known limitations (not addressed this pass)
- "Log in" is not a reachable menu state — the app already full-screens the `Login` component whenever there's no current user, so the ribbon (and this menu) never renders while logged out. Not a new gap, just not fixed here.


### V0.6.0 — Known limitations (not addressed this pass)
- Group-level headers (year/quarter/month) show only a label, not aggregated stats — only day-level summaries show totals. Adding aggregates at every level would need real per-page work not requested here.


### V0.5.0 — Known limitations (not addressed this pass)
- **Reconcile steps cross-source duplication properly (not just pick-a-winner heuristic)** (#139)
  - Worked around (pick the day's highest-reporting source) but not actually reconciled the way food_log_entries/sleep/exercise/measurements were earlier — a real fix would need the same kind of natural-key cross-source merge work, not just picking a winner and discarding the rest.


### V0.4.0 — Known limitations (not addressed this pass)
- **Add a precomputed daily-rollup table for Heart Rate Year-view performance** (#140)
  - Heart Rate's Year view still takes real time to load (~10s) since it computes exact aggregates over the full raw dataset live on every request. A precomputed daily-rollup table, refreshed at sync time, would fix this properly but is a bigger schema/sync change than this pass's scope.


### V0.2.0 — Known limitations (not addressed this pass)
- Weight page has no charting/trend line yet — multi-day views list readings per day, same as Sleep/Exercise, no graph. (Fixed next version, #82.)
- A day with zero entries in a multi-day range is simply omitted from `days[]` (matches the existing single-day "no X logged" convention) rather than shown as an explicit empty section — so a week view can't currently highlight "you didn't log food on Tuesday" at a glance.


### V0.1.9 — Known bugs (not yet fixed)
- **Investigate 172 residual cross-source `food_log_entries` pairs with no real-gram data on either side** (#147)
  - Foods where at least one side never had usable real-gram serving data to reconcile against, so the placeholder can't be confirmed as the same food with confidence. Left as-is rather than guessed.
- **Investigate 14 `food_log_entries` rows sharing the same natural key more than once** (#148)
  - Still share `(user_id, start_time, food_id)` more than once — not yet individually investigated; could be genuine same-instant double-logging (e.g. two real servings at the same minute) rather than a bug.


### V0.1.6 — Known bugs (not yet fixed)
- **Fix `food_log_entries` cross-source duplication (the last unresolved category)** (#70)
  - Unresolved and structurally harder than the three fixed above. Checked before starting: 13,094 food-log pairs match on `(user_id, start_time)` alone, but only 122 also match on `food_id` — the same real meal usually resolves to a *different* `food_id` between sources (Health Connect's placeholder-serving-unit version vs. the live API's real-gram version), so a naive natural-key dedup can't just ignore `food_id` the way it does for sleep/exercise/measurements. A real fix needs the already-tracked "retroactively reconcile Health-Connect placeholder units against real-gram live-API data" work first, so the same real food resolves to the same `food_id` from either source. Deferred as a separate task. (Fixed in V0.1.9, #70.)


### V0.1.5 — Known bugs (not yet fixed)
- Cross-source duplication for **sleep sessions, exercise sessions, weight/height** (#65, fixed V0.1.6) **and food log entries** (#70, fixed V0.1.9) is still unresolved — Health Connect and the live API each have their own id space for the same real-world event, so `UNIQUE(user_id, api_uid)` can't recognize the same session/entry arriving from both sources. Narrowed this session: steps and heart-rate readings are no longer affected, since their new natural-key constraints (`UNIQUE(user_id, reading_time)`) catch duplicates regardless of source.
- The unexplained `--full` sync mentioned above was never root-caused. Watch for a repeat; if it recurs, capture the dev server's request pattern at the time rather than restarting it immediately.


### V0.1.1 — Known, disclosed limitations
- All three new pages surface the same already-disclosed Health-Connect/live-API duplication issue as the food log does (#65, #70) — e.g. a night's sleep or a walk shows up twice (once per source) on days covered by both. Confirms this is a real, pervasive, cross-category symptom now visible in every page, not just food — raises the priority of an actual reconciliation fix.


### V0.1.0 — Known, disclosed limitations
- The cross-source duplication issue (documented since V0.0.16) is now directly visible to a user looking at a real day's food log, not just a database-level concern — worth prioritizing the actual reconciliation fix sooner now that it has a visible symptom (#65, #70).
- Login has zero real security — anyone can "log in" as any real user by typing their email, and every API endpoint trusts whatever `user_id` it's given with no authorization check. Fine for single-developer local use only.


### V0.0.16 — Known, disclosed limitations (not solved this pass)
- **Cross-source duplication risk between Health Connect and the live API is not resolved.** (Fixed for sleep/exercise/weight in V0.1.6, #65; for food log entries in V0.1.9, #70.) Health Connect's `api_uid` (its own local `uuid`) and this sync's `api_uid` (the live API's cloud dataPoint id) are different ID spaces for the same real-world sleep session / exercise session / weight reading / food log entry — the `UNIQUE(user_id, api_uid)` constraint can't detect they're the same event. Same class of problem as the already-documented "upsert priority across sources" open item, just newly live. No automated mitigation exists yet; picking a sync window that starts after the last Health Connect export's own coverage avoids it in practice for now.
- The real-gram custom units this sync creates are not retroactively used to correct Health-Connect-created placeholder units for what might be the same real food (automatic reconciliation done in V0.1.9, #70; a manual review UI is still open, #137).
- `--full` mode's logic was reviewed but not exercised against the real account's entire history this pass (would mostly re-cover what Health Connect's bulk import already has, and take a long time against years of heart-rate data) — only the default incremental path and small explicit `--days` windows were actually run.
- **`lut_activity_type` mapping stays a plain find-or-create** (#138) keyed on the API's raw `exerciseType` string (`API_WALKING` etc.), same non-canonical state as the Health Connect importer.


### V0.0.14 — Known bugs (not yet fixed)
- `sql/sample_data.sql` is now stale/incompatible with the redesigned schema (still reflects the old `food_name`/`brand_name`/`food_log_nutrients`/`SRC`-`FIX`-`MOD` shape) — not rewritten this pass. (Fixed in V0.0.17, #41.)
- **`lut_activity_type` isn't a true canonical mapping yet** (#138) — both importers do a plain find-or-create keyed on each source's raw activity code, so the same real-world activity can produce multiple rows across sources.
- `daily_resting_heart_rate`'s multiple-readings-per-day question (whether Health Connect can report more than one per day, and how to dedup if so) was left unresolved — no `api_uid` added, structurally unchanged from V0.0.13. (Effectively answered by V0.0.16's `(user_id, reading_date)` natural-key upsert.)
- Health Connect's `exercise_session_record_table` has no calories/distance/steps/average-heart-rate columns (stored in separate generic time-series tables with no FK back to the session) — not cross-referenced; those four columns are left `NULL` for HC-sourced exercise sessions. GPS route points are not imported, only a `has_gps` flag. (Partially mitigated by V0.1.7's cross-source merge, #67, for sessions with a matching live-API copy.)


### V0.0.14 — Planned (not yet implemented)
- **UI to correct the placeholder "reported serving" custom units created by the quantity-problem fix** (#137): edit a food's unit directly, search for a specific food to adjust, and a post-sync/import review list of every food still on the placeholder unit (e.g. eggs → 1 egg, cottage cheese → 1 cup/4oz, chicken → ounces) — must keep historical log totals unchanged when a unit is corrected.
- **Real canonical mapping for `lut_activity_type`** (#138) across both Health Connect's and the live API's activity vocabularies.
- Matching catalog foods against a real reference nutrition database (e.g. USDA FoodData Central) for true gram-accurate quantities, rather than the placeholder unit. (Superseded — V0.0.16's real-gram data via Google's own API accomplished this without needing USDA.)
- Rewrite or retire `sql/sample_data.sql` to match the redesigned schema. (Done in V0.0.17, #41.)
- Resolve the `daily_resting_heart_rate` multiple-readings-per-day open question. (Effectively answered by V0.0.16.)
- **Build the "recipe" template feature** (#143) (a separate, not-yet-designed concept — food log entries stay ingredient-level and never reference a recipe directly).
- Build the live-API-to-database sync (currently only bulk importers write to the database). (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)


### V0.0.13 — Known bugs (not yet fixed)
- **Multi-device step overlap can double-count daily step totals if summed naively** (#139) — deliberately deferred to application/aggregation logic (see `doc/wiki/Database-Schema.md` Open Items), not a schema gap.


### V0.0.13 — Planned (not yet implemented)
- **Real canonical mapping for `lut_activity_type`** (#138) across Fitbit numeric IDs and the API's string enum — real reference-data work, deferred to ingest-time implementation.
- Deciding which raw Takeout sleep format the importer will parse, and reviewing the newly-discovered sleep-adjacent Takeout files. (Moot — Takeout dropped as an active source in V0.0.14, #28.)
- Create the actual MySQL database and run `sql/schema.sql` (needs confirmation before touching the local database, per project convention). (Done in V0.0.14, #26.)
- Build `scripts/import-takeout.php` to parse an extracted Takeout export and load it into the schema. (Done in V0.0.14, #27.)
- Build the live-API-to-database sync (currently the fetch scripts only write debug JSON, not the DB). (Done in V0.0.16, #36.)
- **Meal planning — logging an intended future meal, distinct from a consumed entry** (#144)
- React frontend. (Done in V0.1.0, #46.)


### V0.0.11 — Planned (not yet implemented)
- Finish the table-by-table schema review for `steps_readings`, `heart_rate_readings`, `weight_readings`, `exercise_sessions`, `sleep_sessions`/`sleep_stages`. (Done in V0.0.13, #17.)
- **Meal planning — logging an intended future meal, distinct from a consumed entry** (#144)
- Create the actual MySQL database and run `sql/schema.sql` (needs confirmation before touching the local database, per project convention). (Done in V0.0.14, #26.)
- Build `scripts/import-takeout.php` to parse an extracted Takeout export and load it into the schema. (Done in V0.0.14, #27.)
- Build the live-API-to-database sync (currently the fetch scripts only write debug JSON, not the DB). (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)


### V0.0.10 — Known bugs (not yet fixed)
- Takeout nutrition rows have no energy/calorie field — `energy_kcal` is estimated from macros for Takeout-sourced food entries and flagged `is_energy_estimated`. (Moot — Takeout dropped as an active source in V0.0.14, #28.)


### V0.0.10 — Planned (not yet implemented)
- Finish the table-by-table schema review for `steps_readings`, `heart_rate_readings`, `weight_readings`, `exercise_sessions`, `sleep_sessions`/`sleep_stages`. (Done in V0.0.13, #17.)
- Design the `food_log_entries` ↔ `foods_db` linkage (which catalog food, what quantity) — the unit half is resolved, this part isn't. (Done in V0.0.11, #13.)
- **Meal planning — logging an intended future meal, distinct from a consumed entry** (#144) (Google Health has no such capability; surfaced during this schema review.)
- Create the actual MySQL database and run `sql/schema.sql` (not done yet — needs confirmation before touching the local database, per project convention). (Done in V0.0.14, #26.)
- Build `scripts/import-takeout.php` to parse an extracted Takeout export and load it into the schema. (Done in V0.0.14, #27.)
- Build the live-API-to-database sync (currently the fetch scripts only write debug JSON, not the DB). (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)


### V0.0.9 — Planned (not yet implemented)
- Next build target: **steps + exercise** (activity data, toward the activity/food/weight correlation goal).
- Design MySQL schema based on the observed response shape(s). (Done in V0.0.10, #12.)
- Integrate fetch(es) into the actual app (currently standalone scripts) and persist to the database. (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)


### V0.0.8 — Planned (not yet implemented)
- Design MySQL schema based on the observed response shape. (Done in V0.0.10, #12.)
- Integrate the fetch into the actual app (currently a standalone script) and persist to the database. (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)


### V0.0.6 — Planned (not yet implemented)
- Design MySQL schema and swap `TokenStore`'s JSON file for a database-backed store. (MySQL schema designed in V0.0.10, #12; `TokenStore` itself was never actually migrated off the JSON file — still true today.)
- Fetch and store actual nutrition data using the obtained access token. (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)


### V0.0.5 — Known bugs (not yet fixed)
- Stored Google Health OAuth credentials (`doc/credentials/google-health.md`) are a **Desktop app** client; a **Web application**-type client must be created in Google Cloud Console (with the real redirect URI) before this flow can be tested end-to-end with real credentials. (Fixed in V0.0.6, #7.)


### V0.0.5 — Planned (not yet implemented)
- Design MySQL schema and swap `TokenStore`'s JSON file for a database-backed store. (MySQL schema designed in V0.0.10, #12; `TokenStore` itself was never actually migrated off the JSON file — still true today.)
- Fetch and store actual nutrition data using the obtained access token. (Done in V0.0.16, #36.)
- React frontend. (Done in V0.1.0, #46.)


### V0.0.4 — Known bugs (not yet fixed)
- Stored Google Health OAuth credentials (`doc/credentials/google-health.md`) are a **Desktop app** client; NutriPal is a PHP web app, so a **Web application**-type client with proper redirect URIs needs to be created before implementing the OAuth flow. (Fixed in V0.0.6, #7.)


### V0.0.4 — Planned (not yet implemented)
- Scaffold the PHP + MySQL + React project structure. (Done progressively: PHP in V0.0.5 #6, MySQL schema in V0.0.10 #12, React in V0.1.0 #46.)
- Google Health OAuth flow (web application client) and food-data sync implementation. (Done in V0.0.5/V0.0.6, #6/#7.)
- Local MySQL schema for food log entries. (Done in V0.0.10, #12.)


### V0.0.3 — Planned (not yet implemented)
- Scope and build the first slice of functionality. (Done progressively starting V0.0.4, #5.)
- All application code (currently nothing exists beyond docs/scaffolding). (Done in V0.1.0, #46.)


### V0.0.2 — Planned (not yet implemented)
- Decide tech stack for the new build. (Done in V0.0.3, #4.)
- All application code (currently nothing exists beyond docs/scaffolding). (Done in V0.1.0, #46.)


### V0.0.1 — Known bugs (not yet fixed)
- The workflow still requires the GitHub wiki to be manually initialized (Settings → Features → Wiki → create a first page) before its "Checkout Wiki Repo" step can succeed — not yet confirmed done for this repo.


### V0.0.0 — Planned (not yet implemented)
- Decide and scope the actual NutriPal app going forward (an earlier prototype exists in `doc/archive/` as reference material for this rebuild)
