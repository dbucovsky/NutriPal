# NutriPal Wiki

## What is NutriPal?

NutriPal is a web app for accessing and analyzing personal health data pulled from Google Health (the successor to Fitbit's data), viewed from the desktop. Beyond just displaying synced data, it aims to go further than the raw source data:

- Enhanced nutrition analysis — tracking additional macronutrients and micronutrients beyond what's provided out of the box
- Deeper activity analysis — running, workouts, etc.
- Correlating activity, food, and weight trends over time
- Custom meal creation, plus fast logging of frequent/repeated meals (e.g. a near-identical daily breakfast) with quick minor adjustments rather than re-entering from scratch each time

Development is being restarted from scratch; the current codebase is empty aside from documentation. Building incrementally, starting small rather than attempting the full feature set at once.

## Reference material

`doc/archive/` contains a prior prototype of NutriPal (a Fitbit-focused precursor to this rebuild). It's excluded from git (see `.gitignore`) but kept on disk as reference material.

## Status

No app code exists yet at the project root. Tech stack has been decided (see [[Architecture]]). First milestone: Google Health food data sync (calories/nutrients only) — see [[Data-Sync]].

## Pages

- [[Home]] — this page
- [[Architecture]] — stack, hosting target, and rationale
- [[Data-Sync]] — food data sync strategy for the first milestone
