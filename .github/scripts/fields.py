"""Create the board fields the standard requires and the board lacks (bootstrap guide, section 6).

The fields and their values are `preflight.REQUIRED_FIELDS`, which is also what the preflight checks and what a
test compares with the guide's table. Run on a board, this script creates every field that is missing, with its
values (single-select options get the guide's colours, gray otherwise). It never changes a field that exists:
a field of the wrong type, or lacking values, is listed so that an administrator corrects it by hand, and the
built-in Status field, which every board has, is only ever reported.

A dry run unless `--apply` is given, and the board's settings are the administrator's, so it is run only when
the administrator asks. It needs `PROJECT_TOKEN` (an administrator's, with the `project` scope).

    python .github/scripts/fields.py            what it would create
    python .github/scripts/fields.py --apply    create it
"""
import os
import sys

import finalize
import preflight
from github_api import Client, GitHubError

BUILT_IN = ("Status",)


def plan(board):
    """(missing, differing): what to create as (name, kind, values), and the differences nobody here can change."""
    missing, differing = [], []
    for name, (kind, values) in preflight.REQUIRED_FIELDS.items():
        found = board.fields.get(name)
        if found is None:
            if name in BUILT_IN:
                differing.append(f"the built-in field {name} is missing: it exists on every board, so check that this is the right board")
            else:
                missing.append((name, kind, list(values or [])))
        elif found["type"] != kind:
            differing.append(f"field {name} is {found['type']}, expected {kind}: change it by hand")
        elif values:
            absent = [v for v in values if v not in found["options"]]
            if absent:
                differing.append(f"field {name} lacks the values {', '.join(absent)}: add them by hand")
    return missing, differing


def create(run, project_client, board, missing):
    """Create each missing field. Returns the names created (or that would be, in a dry run)."""
    created = []
    for name, kind, values in missing:
        options = [(value, preflight.OPTION_COLORS.get(value, "GRAY")) for value in values]
        shown = f"{name} ({kind}" + (f": {', '.join(values)}" if values else "") + ")"
        run.do(f"create the field {shown}", project_client.create_field, board.id, name, kind, options)
        created.append(name)
    return created


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("GITHUB_REPOSITORY is not set")
        return 1
    repo_client = Client(os.environ.get("GITHUB_TOKEN", ""), repo)
    project_client = Client(os.environ.get("PROJECT_TOKEN", ""), repo)
    report = preflight.run(repo_client, project_client, store=False)
    print(report.render())
    board = report.candidate
    if board is None:
        print("fields skipped: no board was identified (link one to the repository first)")
        return 1
    missing, differing = plan(board)
    run = finalize.Runner("--apply" not in args)
    try:
        create(run, project_client, board, missing)
    except GitHubError as error:
        run.log.append(f"creating the fields stopped: {error}")
        print("\n".join(("would: " if run.dry_run else "did: ") + line for line in run.log))
        return 1
    for line in run.log or ["no field is missing"]:
        print(("would: " if run.dry_run else "did: ") + line)
    for line in differing:
        print("not changed: " + line)
    if run.dry_run and missing:
        print("dry run: nothing was changed; add --apply to create the fields")
    return 0


if __name__ == "__main__":
    sys.exit(main())
