"""The sweep for Start date and End date.

The dates are the days the automation noticed a ticket start and end, in UTC. The automation cannot be told
when a person changes Progress, so it looks at every ticket on the board on each run and on a schedule:

- Start date is set when a ticket is first seen at InProgress or beyond (anything but ToDo and OnDeck),
  only if it is blank: it is never overwritten, whether set earlier or by a person.
- End date is set when a ticket is first seen Completed or Abandoned, only if it is blank.
- End date is cleared when a ticket is seen open again, and set again the next time it ends.
- Version and Alert tickets have no dates.

See appendix C and the guide on project structure (section 4.4). `--dry-run` only reports.
"""
import os
import sys

import finalize
import preflight
import versions
import failures
from github_api import Client, GitHubError

STARTED = ("InProgress", "Review", "Completed", "Suspended", "Abandoned")
ENDED = ("Completed", "Abandoned")
NO_DATES = ("Version", "Alert")

ITEMS = ("query($id:ID!,$after:String){node(id:$id){... on ProjectV2{items(first:100,after:$after){"
         "pageInfo{hasNextPage endCursor} nodes{id content{... on Issue{number issueType{name}}} "
         "status:fieldValueByName(name:\"Status\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "start:fieldValueByName(name:\"Start date\"){... on ProjectV2ItemFieldDateValue{date}} "
         "end:fieldValueByName(name:\"End date\"){... on ProjectV2ItemFieldDateValue{date}}}}}}}")


def board_items(project_client, board):
    """Every issue on the board with its Progress and dates (draft items and pull requests are skipped)."""
    found, after = [], None
    while True:
        page = project_client.graphql(ITEMS, {"id": board.id, "after": after})["node"]["items"]
        for node in page["nodes"]:
            content = node.get("content") or {}
            if not content.get("number"):
                continue
            found.append({"item": node["id"], "number": content["number"],
                          "type": (content.get("issueType") or {}).get("name"),
                          "status": (node.get("status") or {}).get("name"),
                          "start": (node.get("start") or {}).get("date"),
                          "end": (node.get("end") or {}).get("date")})
        if not page["pageInfo"]["hasNextPage"]:
            return found
        after = page["pageInfo"]["endCursor"]


def sweep(run, project_client, board, today):
    """Set and clear the dates as described above. `today` is the UTC date as yyyy-mm-dd."""
    start_field, end_field = board.fields["Start date"]["id"], board.fields["End date"]["id"]
    for ticket in board_items(project_client, board):
        if ticket["type"] in NO_DATES or not ticket["status"]:
            continue
        number, status = ticket["number"], ticket["status"]
        if status in STARTED and not ticket["start"]:
            run.do(f"#{number}: set Start date to {today} (seen at {status})", project_client.set_project_field,
                   board.id, ticket["item"], start_field, {"date": today})
        if status in ENDED and not ticket["end"]:
            run.do(f"#{number}: set End date to {today} (seen {status})", project_client.set_project_field,
                   board.id, ticket["item"], end_field, {"date": today})
        elif status not in ENDED and ticket["end"]:
            run.do(f"#{number}: clear End date {ticket['end']} (seen open again at {status})", project_client.clear_project_field,
                   board.id, ticket["item"], end_field)
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
        print("date sweep skipped: no board (the preflight did not identify one)")
        return 0
    run = finalize.Runner("--dry-run" in args)
    try:
        sweep(run, project_client, report.board, versions.utc_now().strftime("%Y-%m-%d"))
    except GitHubError as error:
        run.log.append(f"date sweep stopped: {error}")
        failures.record(f"date sweep stopped: {error}")
    for line in run.log or ["no dates to set or clear"]:
        print(("would: " if run.dry_run else "did: ") + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
