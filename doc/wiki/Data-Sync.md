# Data Sync Strategy

## First milestone scope

Food data only to start (calories and other nutrients available via the Google Health API's nutrition scope). Activity and weight sync are deferred to later milestones.

## Why sync strategy matters

Food log entries can be edited or backfilled for past dates after the fact — someone might log breakfast today but go back and correct yesterday's lunch. A naive "only fetch what's new since last sync" approach would silently miss those edits.

## Approach

- **Incremental sync (routine):** every regular sync re-fetches and reconciles (upserts, not blind inserts) the last **7 days**, not just brand-new entries, so edits to recently-past days get picked up automatically.
- **Full resync (manual/on-demand):** a separate, explicitly-triggered option to resync the entire available history beyond the 7-day window, for cases where older data was edited outside that range or a backfill/fix is needed.

## Open items (to resolve during implementation)

- Google Health API request/sync rate limits — check before finalizing sync frequency.
- Local MySQL schema for food entries (per-item log vs. daily aggregate, which macro/micronutrient fields to store).
- The stored OAuth credentials in `doc/credentials/google-health.md` are registered as a **Desktop app** client. Since NutriPal is now a PHP web app (not a desktop app), a **Web application**-type OAuth client should be created in Google Cloud Console instead, with proper redirect URIs (local XAMPP URL for dev, Bluehost domain for prod later).
