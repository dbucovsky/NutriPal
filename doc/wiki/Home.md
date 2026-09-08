# NutriPal Wiki

## What is NutriPal?

NutriPal is a web app for accessing and analyzing personal health data pulled from Google Health (the successor to Fitbit's data), viewed from the desktop. Beyond just displaying synced data, it aims to go further than the raw source data:

- Enhanced nutrition analysis — tracking additional macronutrients and micronutrients beyond what's provided out of the box
- Deeper activity analysis — running, workouts, etc.
- Correlating activity, food, and weight trends over time
- Custom meal creation, plus fast logging of frequent/repeated meals (e.g. a near-identical daily breakfast) with quick minor adjustments rather than re-entering from scratch each time

Built incrementally, backend-first: the database schema, data ingestion, and sync are done and verified against real data; the frontend/UI is the next major piece (see Status below).

## Reference material

`doc/archive/` contains a prior prototype of NutriPal (a Fitbit-focused precursor to this rebuild). It's excluded from git (see `.gitignore`) but kept on disk as reference material.

## Status

Tech stack decided (see [[Architecture]]). The database layer is finished and running against real personal data:

- **Schema**: `sql/schema.sql` — every health category (food, steps, heart rate/HRV/resting HR, sleep, weight/height, exercise) plus a personal food catalog (`foods_db`), full audit history on every table, and no-ENUM/lookup-table conventions throughout (see [[Database-Schema]] and [[Database-Design-Patterns]]).
- **Bulk ingestion**: `scripts/import-health-connect.php` is the active bulk importer (an Android Health Connect export) — Google Takeout was tried first, then dropped as an active source once real gaps surfaced (see [[Database-Schema]]); its importer is kept only as a historical artifact.
- **Live sync**: `scripts/sync-google-health.php` incrementally syncs the live Google Health API (see [[Data-Sync]]), including gram-accurate nutrition quantities pulled from Google's own food catalog.

**Not yet built**: any actual application/UI. There is no way yet to browse a food log, see analysis, or log a new meal — `public/index.php` is currently just a one-line "connected to Google Health or not" stub. The React frontend is the next major milestone.

## Pages

- [[Home]] — this page
- [[Architecture]] — stack, hosting target, and rationale
- [[Data-Sync]] — live Google Health API sync design and implementation
- [[Database-Schema]] — MySQL schema, ingestion sources, dedup strategy, Health Connect/Takeout export format notes
- [[Database-Design-Patterns]] — general, project-agnostic schema patterns (naming, history/audit, ownership, dedup) reusable across other projects
