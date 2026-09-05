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

## Open items (to resolve during implementation)

- Google Health API request/sync rate limits — check before finalizing sync frequency.
- Local MySQL schema for food entries (per-item log vs. daily aggregate, which macro/micronutrient fields to store) — and swap `TokenStore`'s JSON file for a database-backed store once that schema exists.
- A **Web application**-type OAuth client now exists and is verified working (see `doc/credentials/google-health.md`); a production redirect URI for Bluehost will need to be added to it once deployment happens.
- Actual food/nutrition data fetch is proven working (see above) but only as an exploratory CLI script (`scripts/fetch-nutrition-test.php`) — not yet integrated into the app or persisted to a database.
