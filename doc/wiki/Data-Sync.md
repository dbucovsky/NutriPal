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

## Open items (to resolve during implementation)

- Google Health API request/sync rate limits — check before finalizing sync frequency.
- Local MySQL schema for food entries (per-item log vs. daily aggregate, which macro/micronutrient fields to store) — and swap `TokenStore`'s JSON file for a database-backed store once that schema exists.
- A **Web application**-type OAuth client now exists and is verified working (see `doc/credentials/google-health.md`); a production redirect URI for Bluehost will need to be added to it once deployment happens.
- Actual food/nutrition data fetch (beyond auth) — not yet implemented.
