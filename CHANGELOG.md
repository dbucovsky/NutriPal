# Changelog

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
