"""Give every option of the board's single-select fields the colour and description in the tables of preflight.py.

`fields.py` gives them to a field when it creates it and never changes a field that exists. This script changes
an existing board: it replaces the options of each single-select field in `REQUIRED_FIELDS`, sending each existing
option with its id so that the tickets holding it keep their value (without the id GitHub makes a new option and
clears the value). An option on the board that is not in the tables is kept, gray and without a description.

A dry run unless `--apply` is given. The board's settings are the administrator's, so run it only when the
administrator asks. It needs `PROJECT_TOKEN` (an administrator's, with the `project` scope).

    python .github/scripts/option_styles.py            what it would change
    python .github/scripts/option_styles.py --apply    change it
"""
import os
import sys

import finalize
import preflight
from github_api import Client, GitHubError


def plan(board):
    """[(field name, field id, [(option id, name, color, description)])] for each required single-select field on the board."""
    found = []
    for name, (kind, values) in preflight.REQUIRED_FIELDS.items():
        field = board.fields.get(name)
        if kind != preflight.SELECT or field is None:
            continue
        options = [(field["options"].get(value), value, preflight.OPTION_COLORS[value], preflight.OPTION_DESCRIPTIONS[value])
                   for value in values]
        extra = [(option_id, option, "GRAY", "") for option, option_id in field["options"].items() if option not in values]
        found.append((name, field["id"], options + extra))
    return found


def apply(run, project_client, board):
    for name, field_id, options in plan(board):
        run.do(f"set the colour and description of the {len(options)} options of {name}", project_client.set_options, field_id, options)


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
        print("option styles skipped: no board was identified (link one to the repository first)")
        return 1
    run = finalize.Runner("--apply" not in args)
    try:
        apply(run, project_client, board)
    except GitHubError as error:
        run.log.append(f"setting the options stopped: {error}")
        print("\n".join(("would: " if run.dry_run else "did: ") + line for line in run.log))
        return 1
    for line in run.log:
        print(("would: " if run.dry_run else "did: ") + line)
    if run.dry_run:
        print("dry run: nothing was changed; add --apply to change the options")
    return 0


if __name__ == "__main__":
    sys.exit(main())
