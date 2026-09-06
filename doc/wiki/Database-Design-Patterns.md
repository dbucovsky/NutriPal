# Database Design Patterns

General-purpose MySQL/MariaDB schema patterns worked out during NutriPal's database design. Written to be reusable as a reference for other projects — nothing here is specific to NutriPal's own tables or domain.

## Naming conventions

- **Lookup tables**: prefix `lut_` + the singular name of the field they back (e.g. a `status` column → `lut_status`). Every categorical/enumerated value lives in one of these — see "No ENUM types" below.
- **Many-to-many junction tables**: prefix `link_` (e.g. a users↔groups membership table → `link_user_group`).
- **A table that connects two others but carries substantial data of its own** (not just the relationship) keeps a descriptive name instead of the `link_` prefix — it's not really a "pure" link.

## No ENUM types — ever

Every categorical/enumerated concept becomes a `lut_` lookup table instead of a native `ENUM(...)` column, even ones that seem small and permanently fixed. Reasons:
- Adding a value to an ENUM requires an `ALTER TABLE`; adding a row to a lookup table is a plain `INSERT`.
- A lookup table can carry metadata (a description, an obsolete flag) that a bare ENUM value can't.
- A lookup table gets its own history (see below) — you can see exactly when a value was introduced or retired. An ENUM has no memory of values that used to exist.

Lookup tables use `is_obsolete BOOLEAN` to represent retirement, not a `status_id` pointing at `lut_status` — a lookup table's own status is its own concern, not deferred to another lookup (and `lut_status` referencing itself would be circular).

**A deliberate exception worth naming**: a lookup table doesn't have to passively mirror everything an external source sends. When ingesting third-party data (an API, an import file) into a field backed by a lookup, you can choose to treat the lookup as a *curated allowlist* — a value that doesn't already exist in the lookup gets dropped at ingest time rather than auto-added. This is the right call when a field should reflect what your application deliberately tracks, not everything an upstream source happens to report; adding a new value becomes a conscious admin action against the lookup table. Whether to drop-if-unmapped or auto-add is a per-field decision, not a blanket rule — a required field on a required parent row usually can't just drop the value without breaking the row, while an optional child row (one of several) can be dropped individually without harming anything else.

## History + provenance (a manual temporal-table pattern)

Every table that needs a durable audit trail gets a parallel `<table>_hist` table and enforced insert/update/delete behavior. This applies broadly (not just to "important" tables) — an empty history table for something that never changes costs nothing, while anything that *does* change gets a genuine debugging aid: a real record of what changed, when, and what caused it.

**Every main table carries:**
```
id                    (or its natural key, for junction tables without a surrogate id)
db_ts                 TIMESTAMP   -- when this row was last written (insert or update)
created_ts            TIMESTAMP   -- true original creation time; NEVER recomputed on update
changed_by            VARCHAR(255) -- see "Provenance" below
changed_by_user_id    BIGINT UNSIGNED
... the table's own real columns ...
```

**Every main table gets a parallel `<table>_hist` table:**
```
id_hist          BIGINT UNSIGNED, auto-increment PK — the history table's own row identity
db_hist_ts       TIMESTAMP   -- when this history row was written
id               (or natural key columns) — identifies which main-table row this snapshot belongs to
valid_start_ts   TIMESTAMP   -- old db_ts: when this snapshot became true
valid_end_ts     TIMESTAMP   -- new db_ts: when this snapshot stopped being true
created_ts, changed_by, changed_by_user_id, ...every other real column...  -- copied from the PRE-update state
```

**Enforced via database triggers, not application code**, so the guarantee holds no matter what touches the table — a future migration script, a manual edit, a new code path that forgets to call the "right" function:
- **Insert**: the main table gets the new row (`db_ts`/`created_ts` both set to the same timestamp); the `_hist` table is untouched — there's no prior state to have history of yet.
- **Update**: a `BEFORE UPDATE` trigger unconditionally copies the *pre-update* row into `<table>_hist`, and forces `id`/`created_ts` to stay unchanged regardless of what the application tried to set. Critically, **the trigger does no change-detection** — it doesn't compare old vs. new values to decide whether to log. That decision (should an `UPDATE` even be issued if nothing actually changed?) belongs in application/business logic, not the trigger, for two reasons: (1) a trigger that diffs every column is verbose and easy to leave out-of-sync when a column is added later, and (2) if the application logic has a bug and issues a needless no-op update anyway, the visible symptom — an extra history row with identical old/new values — is itself useful evidence for finding that bug, rather than being silently swallowed by the database.
- **Delete: forbidden entirely**, enforced via a `BEFORE DELETE` trigger that unconditionally raises an error (`SIGNAL SQLSTATE '45000'`). "Deletion" is represented by a status change instead (see the lookup-table pattern above) — nothing is ever actually destroyed.

### Provenance: what caused this write

Two columns capture *why* a row changed, not just *that* it did:
- `changed_by` — one flexible string describing which part of the application performed the write, plus its version, plus (in debug builds only) file/line detail — e.g. `"google_api_sync (v0.2.0)"` in production, `"SomeClass.php:142 (v0.0.10)"` in debug. Deliberately a single column rather than several separate ones (module / version / file / line) — how much detail to include is an environment-flag decision the application makes, not something the schema needs multiple columns to express.
- `changed_by_user_id` — the acting user (or a reserved "system" sentinel for automated processes).

Both are **explicit values the application always supplies on every insert/update** — not MySQL session variables. This matches a broader principle worth calling out: explicit function/statement parameters are easier to read, test, and trust than hidden connection-level state that something has to remember to set at the right time. A nice side effect: a write that doesn't supply `changed_by` (e.g. someone editing a row directly through a database GUI) naturally shows up as `changed_by = NULL` — which is exactly how you distinguish "the application did this" from "someone touched the database directly," with no extra logic required.

## Reserved sentinel rows, not `0` or `NULL`

When a column needs to express "none" / "unowned" / "universal" (e.g. "this record isn't owned by any particular user"), use a real reserved row in the referenced table (conventionally `id = 1`) rather than a magic literal or `NULL`:
- **Not literal `0`**: MySQL's `AUTO_INCREMENT` columns treat an explicitly-inserted `0` specially in the default SQL mode (it typically triggers auto-assignment rather than literally storing zero) — relying on it as a sentinel value fights the column type instead of working with it.
- **Not `NULL`**: MySQL's unique-index semantics treat every `NULL` as distinct from every other `NULL`. If "unowned" meant `NULL`, a uniqueness constraint meant to prevent duplicate unowned rows would silently stop protecting against exactly that — two "unowned" rows with otherwise-identical data would both insert successfully, since `NULL ≠ NULL` for uniqueness purposes.

A real, deliberately-seeded row sidesteps both problems and keeps every row's foreign key genuinely non-nullable and uniformly comparable.

## Three-tier ownership / sharing model

Where data needs to be shared at more than one level — universal (everyone), group (a specific team/household/whatever), and individual (one user's personal override) — one pattern that works well:
- The owned table carries both a `group_id` and a `user_id` (both using the sentinel-row convention above for "none").
- **Universal**: both sentinel.
- **Group-owned**: real `group_id`, sentinel `user_id`.
- **User-owned**: real `user_id` — `group_id` can be anything on a user-owned row (it's provenance/context only, e.g. "this personal copy originated from group X's version"), since a non-sentinel `user_id` alone is what makes a row user-owned, taking priority regardless of `group_id`.
- **Resolution priority** when looking up which row applies for a given user: (1) that user's own row wins outright if one exists; (2) otherwise, walk that user's groups **in that user's own ranked order** (see below) and use the first group that has a matching row; (3) otherwise, fall back to the universal row. This resolution logic belongs in the application/query layer — it's a lookup algorithm, not something a foreign key alone can express.
- Group membership is a many-to-many junction table (`link_user_group`) carrying a `priority` column that's the **ranking that specific user gave to that specific group**, not a global ranking of groups — two users in the same two groups can rank them in opposite orders. Enforce uniqueness with `UNIQUE(user_id, priority)`; allow gaps in the numbering (1, 5, 10) rather than requiring contiguous values, so inserting a new ranked group between two existing ones never requires renumbering everything else.

## Multi-tenancy: `user_id` on every table, including children

When a schema needs to support multiple users' data living in the same tables (even if only one user exists today), add `user_id` directly to **every** user-owned table — child/detail tables included, not just their parents. The alternative (only the parent table has `user_id`, children are scoped only via a join through the parent) saves one column per child table but costs more later: every future access-control check or index needs to join through the parent to know who owns a child row, and a missed join anywhere is a real class of bug (one user's data leaking into another's query). A direct column avoids that entirely.

Every uniqueness constraint on such tables needs `user_id` folded into the key too (`UNIQUE(user_id, some_natural_key)` instead of `UNIQUE(some_natural_key)`) — two different users can otherwise produce identical natural keys without that being a real duplicate.

## Reconciling multiple data sources into one table

When the same table can be populated from more than one independent source (e.g. a live API sync and a bulk historical import) that don't share a common identifier, two complementary mechanisms:

**Content-based fingerprint.** Every row gets a `fingerprint CHAR(64)` — a sha256 hash of that row's core identifying fields, computed *identically* regardless of which source produced the row. The same real-world event produces the same fingerprint from either source, so an upsert (`INSERT ... ON DUPLICATE KEY UPDATE` or equivalent) naturally merges them instead of creating a duplicate. Exclude fields prone to source-specific noise (e.g. floating-point rounding differences) from the hash — include only what genuinely identifies "this is the same real thing," not everything about it.

**Native-ID-before-fingerprint identity resolution.** When a source *does* provide a stable native ID (not shared with the other source, but stable across that source's own updates), that ID must take priority over the fingerprint for finding an existing row to update — because fingerprints built from mutable fields break when those fields are legitimately edited. Concretely: if a record's identifying timestamp can be edited by the user after the fact, its fingerprint changes, but a native ID tied to that same record does not — so looking up by native ID first (when available) correctly finds and updates the existing row across such an edit, while fingerprint-only matching would treat the edit as a brand-new record and leave a stale duplicate behind. Fall back to fingerprint matching only when no native ID exists for that source.

**A dedicated "genuine conflict" value**, distinct from either source's own value, for when two sources actively disagree on a fact for what's otherwise clearly the same record (e.g. one reports a slightly different quantity than the other) — not for one source merely filling in a gap the other left blank (that's an ordinary upsert), and not for values that get corrected via the non-destructive pattern below.

## Non-destructive value correction (`SRC` / `FIX` / `MOD`)

When a sourced value sometimes needs correcting or supplementing — without ever destroying what the source actually reported, and without needing a vague "estimated" boolean bolted onto a single column — model up to three rows per (record, field) pair, tagged by kind:
- **`SRC`** — the raw value as imported, always preserved untouched, forever.
- **`FIX`** — a hard override. If present, it wins outright; `SRC`/`MOD` are ignored entirely for that field.
- **`MOD`** — an additive adjustment layered on top of `SRC` (positive or negative), used only when no `FIX` exists.

**Effective value**, computed at read time and never stored/overwritten:
```
IF a FIX row exists:  effective = FIX
ELSE:                 effective = GREATEST(0, COALESCE(SRC, 0) + COALESCE(MOD, 0))
```
(The zero-floor guards against a case where a negative `MOD` would otherwise push the effective value below a physically meaningless negative number — omit the `GREATEST` clamp if negative values are actually valid for whatever you're modeling.)

This cleanly covers three real cases with one mechanism: a field the source never reported at all (no `SRC` row — just a `MOD` supplying the whole value, since `COALESCE(SRC,0)` treats the absence as zero), a field whose reported value needs a proportional nudge (`SRC` + a small `MOD`), and a field that needs to be completely replaced with a known-correct value (`FIX`).

## Resolving a "could be one of several other tables" reference

When a column's value could conceptually reference one of *several* different tables depending on context (e.g. "the unit used here is either a universal standard unit or a context-specific custom one"), avoid adding multiple nullable foreign-key columns directly on a high-volume table (a "nullable-XOR-columns" smell — awkward to query, awkward to enforce "exactly one is set"). Instead, introduce one thin indirection lookup table that itself holds the several nullable FK columns, resolving onward to whichever specific table actually applies:
```
lut_whatever
  id
  label                     -- human-readable fallback/display value
  target_a_id  NULL, FK → table_a
  target_b_id  NULL, FK → table_b
  -- exactly one of the FK columns populated when recognized;
  -- both may be NULL for a value from an external source that
  -- doesn't map to anything currently defined — `label` still
  -- records what was actually seen even then.
```
The high-volume table then carries just one foreign key (into this indirection table) instead of several nullable ones. Note this kind of table is structurally different from a small universal lookup like `lut_status` — it can grow much larger, since some of its rows may be scoped to one specific context rather than representing a small shared vocabulary — but it still follows the same naming and history conventions as every other lookup.
