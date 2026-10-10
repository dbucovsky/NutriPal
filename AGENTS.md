# Instructions for assistants

Follow the process guides in [`doc/governance/guides/`](doc/governance/guides/README.md) (a git submodule of
the governance standard). Work from the checklist at the end of each guide.

This project
- Build: `npm run build` in `frontend/`. Tests: `python -m unittest discover -s tests` (the automation's tests,
  expect `OK`) and `python .github/scripts/check_manifest.py` (expect all files unchanged). The manifest is the
  project's own, so the files that differ from the standard are listed in `doc/2026-10-09_governance-nonconformities.md`;
  after editing one, rewrite the manifest with `--update --standard V0.10.1` and update that list.
- Hooks: activate them once per clone with `git config core.hooksPath .githooks`. Fetch the standard with
  `git submodule update --init`.
- Local services (Apache, MySQL) are started and stopped by the owner through the XAMPP Control Panel, never by
  the assistant. `start-services.*` and `stop-services.*` are provided for the owner to run.
- Ticket Type is a single-select `Ticket type` field on the board (GitHub reserves the name `Type`), not the native issue type (the repository is
  personal, so issue types are unavailable). The automation files that read it differ from the standard and
  are listed in the nonconformity record.
- The changelog has no "Known bugs" or "Planned" sections: known bugs and planned work are tickets.
- Roles: Damian Bucovsky holds the administrator, project owner and developer roles. No one else.
- Durable authorizations: none.
- Out of bounds: `doc/governance/` is a submodule, changed only through its own repository. Repository,
  organization and board settings, and the `PROJECT_TOKEN` secret, change only when the administrator asks.
  `doc/archive/`, `doc/credentials/`, `.env` and `storage/` hold local-only or personal data: never commit or
  print them.
- Commit messages and pull request descriptions carry no assistant attribution (no co-author trailer and no
  "generated with" line), even if the assistant's tooling suggests adding one.
