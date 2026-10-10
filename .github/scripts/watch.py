"""The Watch flags: a ticket left alone at a stage is pointed out.

*Watch* is raised, with one comment, when a ticket has had no activity at *Review* for a week, at
*OnDeck* or *InProgress* for a month, at *Suspended* for six months, or has been waiting for input
for two weeks. Activity is a comment, a change to a field, or a new build that mentions the ticket;
the automation's own flag comments do not count.

A flag is set only on a ticket that is blank, *Fine* or *Acknowledged*, never lowering a level, and
it is raised when a situation begins and not again while it goes on: after a person closed it, it is
raised again only if the ticket's stage changes or new work arrives (a later build). A situation is
the Progress together with the latest build, remembered in a hidden marker in the flag's comment.
Version and Alert tickets have no Attention. See appendix C and the guide on project structure
(section 4.3). `--dry-run` only reports.
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import condition_comments
import finalize
import preflight
import versions
import failures
from github_api import Client, GitHubError

THRESHOLDS = {"Review": timedelta(days=7), "OnDeck": timedelta(days=30), "InProgress": timedelta(days=30),
              "Suspended": timedelta(days=182)}
WAITING_AFTER = timedelta(days=14)
OPEN = ("ToDo", "OnDeck", "InProgress", "Review", "Suspended")
NO_ATTENTION = ("Version", "Alert")
FLAG_MARKER = "<!-- attention:"  # every flag comment the automation writes starts with this
SITUATION = re.compile(r"<!-- attention:watch situation=(\S+) -->")

ITEMS = ("query($id:ID!,$after:String){node(id:$id){... on ProjectV2{items(first:100,after:$after){"
         "pageInfo{hasNextPage endCursor} nodes{id updatedAt "
         "content{... on Issue{number issueType{name} comments(last:30){nodes{createdAt body}}}} "
         "status:fieldValueByName(name:\"Status\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "waiting:fieldValueByName(name:\"Waiting\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "attention:fieldValueByName(name:\"Attention\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "build:fieldValueByName(name:\"Build\"){... on ProjectV2ItemFieldTextValue{text}}}}}}}")


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def board_tickets(project_client, board):
    found, after = [], None
    while True:
        page = project_client.graphql(ITEMS, {"id": board.id, "after": after})["node"]["items"]
        for node in page["nodes"]:
            content = node.get("content") or {}
            if not content.get("number"):
                continue
            found.append({"item": node["id"], "number": content["number"], "updated": node["updatedAt"],
                          "type": (content.get("issueType") or {}).get("name"),
                          "comments": (content.get("comments") or {}).get("nodes") or [],
                          "status": (node.get("status") or {}).get("name"),
                          "waiting": (node.get("waiting") or {}).get("name"),
                          "attention": (node.get("attention") or {}).get("name"),
                          "build": (node.get("build") or {}).get("text") or ""})
        if not page["pageInfo"]["hasNextPage"]:
            return found
        after = page["pageInfo"]["endCursor"]


def last_activity(ticket):
    """The latest of: a field change on the board, a comment that is not a flag, and the latest build."""
    times = [parse_time(ticket["updated"])]
    times += [parse_time(c["createdAt"]) for c in ticket["comments"] if not (c.get("body") or "").startswith(FLAG_MARKER)]
    if re.fullmatch(r"\d{14}", ticket["build"]):
        times.append(datetime.strptime(ticket["build"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc))
    return max(times)


def reason(ticket, now):
    """Why the ticket looks out of date, or None."""
    if ticket["status"] not in OPEN:
        return None
    quiet = now - last_activity(ticket)
    days = quiet.days
    if ticket["status"] in THRESHOLDS and quiet >= THRESHOLDS[ticket["status"]]:
        return f"no activity at {ticket['status']} for {days} days"
    if ticket["waiting"] == "Needs input" and quiet >= WAITING_AFTER:
        return f"waiting for input for {days} days"
    return None


def situation(ticket):
    return f"{ticket['status']}/{ticket['build'] or 'none'}"


def already_raised(ticket):
    return any(m.group(1) == situation(ticket) for c in ticket["comments"] for m in [SITUATION.search(c.get("body") or "")] if m)


def comment_text(ticket, why, now):
    text = (f"{FLAG_MARKER}watch situation={situation(ticket)} -->\n"
            f"Attention: Watch. This ticket has had {why} (last activity {last_activity(ticket):%Y-%m-%d %H:%M} UTC). "
            "Update it, complete it if the work is done and verified, suspend or abandon it, or ask again if it is waiting; "
            "then tick a box below.")
    return condition_comments.decorate(text, "waited-too-long" if ticket["waiting"] == "Needs input" and why.startswith("waiting") else "stale")


def sweep(run, repo_client, project_client, board, now):
    """Raise the Watch flags that are due. Returns the numbers of the tickets flagged."""
    flagged = []
    field = board.fields["Attention"]
    for ticket in board_tickets(project_client, board):
        if ticket["type"] in NO_ATTENTION:
            continue
        why = reason(ticket, now)
        if why is None or ticket["attention"] in ("Watch", "Caution", "AtRisk") or already_raised(ticket):
            continue
        number = ticket["number"]
        run.do(f"#{number}: set Attention to Watch ({why})", project_client.set_project_field, board.id, ticket["item"],
               field["id"], {"singleSelectOptionId": field["options"]["Watch"]})
        run.do(f"#{number}: comment on why", repo_client.comment, number, comment_text(ticket, why, now))
        flagged.append(number)
    return flagged


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
        print("Watch flags skipped: no board (the preflight did not identify one)")
        return 0
    run = finalize.Runner("--dry-run" in args)
    try:
        sweep(run, repo_client, project_client, report.board, versions.utc_now())
    except GitHubError as error:
        run.log.append(f"Watch sweep stopped: {error}")
        failures.record(f"Watch sweep stopped: {error}")
    for line in run.log or ["no stale tickets to flag"]:
        print(("would: " if run.dry_run else "did: ") + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
