"""The sweep for Version#.

Version# is the number that is derived from a ticket's Version, used only to sort versions. The finalize step
sets it when a version ships, but a ticket that is only aimed at a version (its Version field says `V2.1.0` before
that version exists) would have none, and a view could not sort it among the others. So the scheduled run sets
Version# on every work ticket whose Version is a version and whose Version# is blank or different. It changes
nothing else: not Version, not Build. A Version that is not a version (any other text) is reported and skipped.
Version and Alert tickets are left alone (finalize sets theirs).

See appendix C and the guide on project structure (section 4.3). `--dry-run` only reports.
"""
import os
import sys

import finalize
import preflight
import failures
from github_api import Client, GitHubError
from versions import Version, VersionError

SKIPPED_TYPES = ("Version", "Alert")

ITEMS = ("query($id:ID!,$after:String){node(id:$id){... on ProjectV2{items(first:100,after:$after){"
         "pageInfo{hasNextPage endCursor} nodes{id content{... on Issue{number issueType{name}}} "
         "version:fieldValueByName(name:\"Version\"){... on ProjectV2ItemFieldTextValue{text}} "
         "number:fieldValueByName(name:\"Version#\"){... on ProjectV2ItemFieldNumberValue{number}}}}}}}")


def board_items(project_client, board):
    """Every issue on the board with its Version and Version# (draft items and pull requests are skipped)."""
    found, after = [], None
    while True:
        page = project_client.graphql(ITEMS, {"id": board.id, "after": after})["node"]["items"]
        for node in page["nodes"]:
            content = node.get("content") or {}
            if not content.get("number"):
                continue
            found.append({"item": node["id"], "number": content["number"],
                          "type": (content.get("issueType") or {}).get("name"),
                          "version": ((node.get("version") or {}).get("text") or "").strip(),
                          "version_number": (node.get("number") or {}).get("number")})
        if not page["pageInfo"]["hasNextPage"]:
            return found
        after = page["pageInfo"]["endCursor"]


def sweep(run, project_client, board):
    """Set Version# from Version as described above."""
    field = board.fields["Version#"]["id"]
    for ticket in board_items(project_client, board):
        if ticket["type"] in SKIPPED_TYPES or not ticket["version"]:
            continue
        number = ticket["number"]
        try:
            wanted = float(Version.parse(ticket["version"]).number())
        except VersionError:
            run.log.append(f"#{number}: Version {ticket['version']!r} is not a version, so no Version# was set")
            continue
        if ticket["version_number"] != wanted:
            run.do(f"#{number}: set Version# to {int(wanted)} (from Version {ticket['version']})", project_client.set_project_field,
                   board.id, ticket["item"], field, {"number": wanted})
    return run


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
    if report.board is None:
        print("Version# sweep skipped: no board (the preflight did not identify one)")
        return 0
    run = finalize.Runner("--dry-run" in args)
    try:
        sweep(run, project_client, report.board)
    except GitHubError as error:
        run.log.append(f"Version# sweep stopped: {error}")
        failures.record(f"Version# sweep stopped: {error}")
    for line in run.log or ["no Version# to set"]:
        print(line if "is not a version" in line else ("would: " if run.dry_run else "did: ") + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
