# Governance adoption: known nonconformities

Record, 2026-10-09. Written before adoption starts, from a reading of the guides in `doc/governance` (all ten
guides, the appendices' index, and the bootstrap checklist) against the repository as it stands at V0.14.2.
It is a point-in-time record and is not rewritten afterwards. Later status goes in tickets.

Each item has a class:

- **Fixable**: can be brought into line by work in the repository.
- **Needs a decision**: can be reconciled, but only by a choice or a setting that is the owner's or the administrator's.
- **Irreconcilable**: cannot be brought into line. Stays as a documented exception.

## Irreconcilable (permanent exceptions)

| # | Nonconformity | Guide | Why it stays |
|---|---|---|---|
| I1 | Versions V0.0.0 to V0.14.2 predate the standard: headings carry local-time dates with no `UTC`, many have no build blocks, entries are not tied to tickets (`#123`) or `REF`, and 22 headings carry "Known bugs" or "Planned" sections. | 03 §7.2, §7.3 | Entries of earlier commits are never edited. Applies from the first governed version onward. |
| I2 | All 47 commits on `main` were made directly: no pull request, no merge commit, no build stamps, no `released/` or retirement tags. | 02 §5, §2.2 | History is not rewritten (02 §6.5). No Alert is raised retroactively. |
| I3 | The 152 existing issues were created by a migration and carry no Type, Area, Origin or Delivery. They cannot be given real creation dates. | 03 §4, appendix C | Can be given Origin *Backdated* and a best-fit Type, but their true history is lost. See F5. |
| I4 | The commit "V0.14.2: Add governance as a submodule…" (pushed to `origin/governance`) carries a `Co-Authored-By` trailer naming the assistant. | 09 §4.2 | It is already pushed, and rewriting a pushed commit is not allowed (09 §5.2). Recorded here; no trailer from now on. |
| I5 | Repository history contains no tickets for V0.0.0 to V0.14.2 work, so the first governed version has no Version ticket lineage before it. | 03 §5.2 | Follows from I1 to I3. |

## Needs a decision

| # | Nonconformity | Guide | Options |
|---|---|---|---|
| D1 | **The repository is owned by a personal account (`dbucovsky`), not an organization.** Issue types, which are the ticket Type that drives the version bump, are an organization feature. The board is also user-owned (`users/dbucovsky/projects/2`). | 10 §5.1, 02 §3.3 | (a) Transfer the repository and board to an organization. This reconciles it. (b) Stay personal and record the Type some other way, such as a `Type` text field on the board. This is a deliberate departure and would need the automation changed, which the standard forbids (10 §2.5). |
| D2 | **Squash and rebase merging are enabled; automatic branch deletion is off (correct).** | 10 §3 | Administrator turns both merge methods off. Not done by the assistant. |
| D3 | **No branch protection on `main`.** | 10 §3 | Optional on the plan; recommended, with the administrator bypass left open. |
| D4 | **Personal instructions conflict with the shared standard.** The global `CLAUDE.md` requires "Known bugs" and "Planned" sections and its own `V.s.m` logging; the standard forbids those sections (03 §7.3) and derives the bump from ticket Types. | 09 §6.5, 03 §7.3 | Shared file and guides win (09 §6.5). The personal file should drop those two changelog rules for this project, or be edited globally. The personal rule "confirm before bumping V" matches the standard's `+V` rule and stays. |
| D5 | **The board's built-in fields differ from the standard.** Status is `Todo, On Deck, In Progress, Completed, Suspended, Abandoned` (no `Review`); Priority is `P0, P1, P2` (the standard has six values); Size matches. `fields.py` never edits an existing field. | 10 §6 | Easiest: create a fresh board that the script fills in, relink it, and archive the old one. Otherwise edit by hand. |
| D6 | **A token is needed.** The automation requires a `PROJECT_TOKEN` secret (classic token with `project` and `repo`), created by the administrator and never read by the assistant. | 10 §4 | The administrator creates it and records its expiry. |
| D7 | **The 8 default labels** (`bug`, `documentation`, `duplicate`, `enhancement`, `invalid`, `question`, `wontfix`, `task`) must become exactly the 14 Area labels plus `dummy`. | 10 §5.2 | Deleting labels is the administrator's call, since it removes them from the 152 issues. |

## Fixable (in the plan)

| # | Gap | Guide |
|---|---|---|
| F1 | No `.gitattributes` with `* text=auto eol=lf`. | 03 §2.2 |
| F2 | No `.githooks/`, no hook activation line in the readme. | 03 §2.2, 10 §1 |
| F3 | No `.github/` automation (`versioning.yml`, `reenable-schedule.yml`, scripts, `views.json`, manifest, pull request template). The existing `main.yml` wiki sync differs from the standard's `wiki-sync.yml`. | 10 §2 |
| F4 | No `AGENTS.md` at the root. | 09 §6 |
| F5 | The 152 existing issues need Type, Area, Origin *Backdated* and Delivery/Resolution/Version to match their state. | appendix C |
| F6 | No automated tests for the product (`tests/` holds nothing). Several of the guides' rules assume tests with new logic. | 03 §2.1, 05 §4 |
| F7 | `doc/` records are not date-prefixed (`Future-DB-Tooling-Exploration.md`, `github-issues-migration.md`). | 03 §9.2 (recommendation) |
| F8 | The readme does not explain the setup or the hook activation command. | 10 §1 |
| F9 | Changelog stays at V0.14.x. The next governed version is decided at merge by the ticket Types, so it will not follow the old manual numbering. No first-version `V0.1.0` applies. | 02 §3.3 |
| F10 | The wiki has no page on the process; the standard says the wiki links to the guides and may keep a one-page summary. | 03 §9.2 |

## Notes on the submodule

- The standard expects the automation files to be copied unchanged into the project (10 §2.5). The submodule is
  the source for that copy, not a replacement: GitHub only runs workflows from the project's own `.github/`.
- The submodule's own `AGENTS.md`, hooks and `doc/wiki` are not the project's. The project needs its own.
- Updating the standard means moving the submodule pointer, copying changed automation files, and running
  `check_manifest.py`.

## Decisions taken (2026-10-09)

- **D1: stay personal.** The repository and board stay under the personal account, so issue types are not
  available. This is now a permanent departure: the ticket Type that drives the version bump cannot be the native
  issue type, and the standard forbids editing the automation (10 §2.5). How Type is recorded instead (for
  example a board field), and which automation files must therefore differ from the standard, is still open and
  is the first item of the adoption plan. Every file that ends up differing is listed here when it does.
- **D4: the standard wins.** For this project the changelog has no "Known bugs" or "Planned" sections; known
  bugs and planned work live in tickets. The project's `AGENTS.md` will say so.
- **D5: fresh board.** A new board is created with `fields.py` and `views.py`, linked to the repository, and the
  old one is archived.
- **Still open:** D2, D3, D6 and D7 are the administrator's settings and are done by the owner on request.

## Automation edits required by D1 (Type as a board field)

Decision: Type is recorded in a single-select `Type` board field (Feature, Enhancement, Change, Bug, Refactor,
Task, Version, Alert) instead of the native issue type. Found by searching `.github/scripts/` in the standard;
each of these files will differ from the standard once edited, and each is listed in the project's manifest as
locally edited:

| File | Why it changes |
|---|---|
| `github_api.py` | `issue_type()` and `create_issue(issue_type=…)` use the issue's native type; the REST calls for fields and views use `/orgs/{owner}/…`, which does not exist for a personal account (`/users/{owner}/…`). |
| `finalize.py`, `hotfix.py` | Read the Type per ticket through `issue_type()`. |
| `conditions.py`, `dates.py`, `release.py`, `version_numbers.py`, `watch.py` | Read `issueType{name}` in their board queries; must read the `Type` field value instead. |
| `fields.py`, `preflight.py` | Must require and create the `Type` field and its values. |
| `tests/` for the files above | Updated alongside. |

Open risk: the standard's `check_manifest.py` and its tests assume the shipped hashes, so they will report these
files as edited locally. That report is expected and is the record of this departure.

## Adoption log (2026-10-09)

- **I1 reduced by the owner's choice.** The history V0.0.0 to V0.14.2 was reformatted in place to the standard's
  headings, against the rule that entries of earlier commits are not edited (03 §7.3). What changed: times were
  converted from local (UTC-4) to UTC and labelled; each version got one build block and one `REF` block marking it
  as history from before the standard; "Known bugs", "Planned" and "Known limitations" sections were moved verbatim
  to `doc/2026-10-09_changelog-removed-sections.md`. The wording of entries is untouched. The headings no longer show
  the local times they were written with.
- **Type-field edits postponed.** The edits for D1 are larger than first listed (about 14 scripts, the saved-view
  filters in `views.json`, and about 59 test references; the `type:` filters may clash with a board field named
  `Type`). They get their own branch after the rest of the adoption. Until then the versioning workflow
  (`versioning.yml`) must stay disabled in the Actions settings, and version bumps are made by hand with the
  `+V`, `+s` and `+m` markers.
- **`test_tools.py` not copied.** It tests the guides' own build tools (`tools/combine.py`), which the project does not have.
- **Wiki sync.** `.github/workflows/main.yml` was replaced by the standard's `wiki-sync.yml`. It differs from the
  template in the personal instructions only in `actions/checkout@v7` instead of `@v4`, and comments removed.
- **Old board.** Not yet replaced. Needs the token and the fields script.
- **`tests/test_automation_library.py` edited.** `test_the_repository_changelog_parses` asserted the standard's own changelog (versions V0.1.0, V0.2.0 and their tickets); it now asserts this project's. `check_manifest.py` will report the file as edited locally.

## Board log (2026-10-09)

- Merged: pull request #153. The Versioning workflow is disabled by hand in the Actions settings.
- New board: project 6, "NutriPal (governed)", linked to the repository. The old board (project 2) was unlinked so
  the preflight sees one board, and is kept until the backfill is done, then archived.
- `fields.py` created the 15 missing fields; the preflight passes ("all 16 fields and their values are present").
  The `Status` values were set through the API (`updateProjectV2Field`), which worked even though the script says to
  do it by hand.
- **The board field cannot be named `Type`.** GitHub reserves the name (it is the built-in issue-type column), so the
  field is `Ticket type` (Feature, Enhancement, Change, Bug, Refactor, Task, Version, Alert). The Type-field edits
  must read `Ticket type`, and the saved-view filters need `ticket-type` rather than `type:`.
- **`views.py` fails with a 404.** It calls organization-only REST endpoints (`/orgs/{owner}/projectsV2/...`), as
  expected for a personal account. The saved views are not created yet; this is part of the Type-field step.
- The token used for these runs was the owner's `gh` login, not `PROJECT_TOKEN`. The preflight warned that it has no
  expiry date; `PROJECT_TOKEN` itself was not exercised and still needs its own preflight run.
