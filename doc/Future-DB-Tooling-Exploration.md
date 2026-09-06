# Future exploration: DB migration tooling & Composer

Not a current-state doc — a starting point for a **separate future chat** exploring two options that were deliberately deferred during the initial schema design session. Decision at the time: keep things as-is (a single checkpoint `sql/schema.sql`, no migration tooling, no Composer) while the schema is still actively evolving and no real data exists yet. Revisit once the schema has settled down and/or real data makes "just rewrite schema.sql" no longer viable.

## Context

NutriPal's schema grew a fairly heavy set of custom conventions during design: `lut_`/`link_` lookup and junction tables, a full audit-history mechanism (`<table>_hist` tables + triggers on every table), three-tier ownership (universal/group/user), and a non-destructive `SRC`/`FIX`/`MOD` correction pattern. That raised a real question: what's the right long-term way to *maintain* this schema — apply changes safely over time, keep it under CI, eventually deploy changes to the real Bluehost database — rather than continuing to hand-edit one big `schema.sql` file forever.

## Baseline recommendation already given (not yet implemented)

Plain versioned migration files (`sql/migrations/0001_initial_schema.sql`, `0002_...sql`, etc.) plus a small dependency-free PHP runner script and a `schema_migrations` tracking table — no new dependency, matches this project's existing hand-written, no-framework style. CI (GitHub Actions, extending the existing wiki-sync workflow) would spin up a throwaway MySQL/MariaDB service container and apply every migration from scratch on every push touching `sql/`, catching broken SQL/triggers immediately. Actually applying a migration to the real Bluehost database would stay a manual, explicitly-triggered step — never automatic — consistent with the standing project rule about never touching MySQL without confirmation.

This baseline is good enough for now and doesn't require deciding either of the two things below.

## Option 1 to explore later: a dedicated migration/schema tool

Instead of hand-rolling the runner script, evaluate an existing tool. Roughly three shapes, each with a real tradeoff:

- **Composer-based PHP migration libraries** — Phinx, Doctrine Migrations. Mature, well-documented, PHP-native. Require Composer (see Option 2 below) and generally assume a framework-adjacent project structure.
- **Standalone CLI binaries, no PHP dependency at all** — Flyway (Java, free community edition, extremely widely used, just needs versioned `.sql` files with its naming convention) or `golang-migrate` (single Go binary). Appealing because they don't touch the PHP codebase's dependency story at all — install once on the dev machine/CI runner, point at the database, done.
- **Declarative schema-diffing tools** — Skeema is the notable one: you keep writing `CREATE TABLE` statements as the desired end state (which is exactly what's already being done), and it computes/applies the safe `ALTER` path automatically. Big open question to verify before betting on this: **Skeema's trigger support has historically been weak or limited**, and this schema is unusually trigger-heavy (every table has two). Confirm current capability before considering it further — this could be a dealbreaker.

Also worth checking in that future session: what does Bluehost's shared hosting plan actually allow? SSH access, ability to install a CLI binary, whether it exposes remote MySQL connections (so migrations could run *from* a local machine or CI runner *against* the remote database without needing anything installed server-side). This matters a lot for which tool shape is even feasible.

## Option 2 to explore later: introducing Composer to the project

This project has deliberately stayed dependency-free so far — the `.env` loader, Google OAuth flow, and token storage were all hand-written specifically to avoid a Composer install (per the project's "no global package installs without asking" convention and a preference for explicit, inspectable code over pulled-in libraries). Adopting Composer would be a real philosophy shift, not just a migration-tooling detail — worth deciding deliberately, with its own pros/cons conversation (access to a much wider PHP library ecosystem generally, versus more moving parts / another thing to keep updated / a step further from the "read the whole codebase in one sitting" simplicity that's existed so far), rather than backing into it as a side effect of picking a migration tool.

## Questions to resolve in that future session

- Is the schema stable enough yet that "rewrite one big file" has actually become painful, or is it still early enough that the baseline (Option-free, plain files) is still fine?
- Does the chosen tool (if any) handle triggers correctly for this schema's pattern?
- What does Bluehost actually support (SSH, Composer, remote MySQL access)?
- Is Composer worth adopting for its own sake (broader ecosystem access going forward), independent of the migration-tooling question?
