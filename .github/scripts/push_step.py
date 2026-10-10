"""The push step: what the automation does when a branch is pushed.

For each ticket in the changelog entries that the push added, it sets Delivery to Pushed and Build to
the ticket's latest build, moves a ticket still at ToDo or OnDeck to InProgress, and raises Caution in
Attention, with one comment naming the build, when the ticket is Completed, Abandoned, Review or
Suspended and its earlier work was already pushed or delivered (new work has arrived on a finished
ticket). Earlier work is recognised by a Build recorded on the board that is older than the build being
pushed, or by Delivery Implemented (which has no Build). A ticket whose Delivery was merely set by hand has
no such Build, so its push counts as a first push and never raises it. It never moves a ticket out of those
states.
See the guide on starting work (section 5) and project structure (section 4.3).

`--dry-run` only reports what it would do.
"""
import os
import re
import sys

import changelog
import checks
import condition_comments
import finalize
import preflight
from github_api import Client, GitHubError

FINISHED = ("Completed", "Abandoned", "Review", "Suspended")
DELIVERED = ("Pushed", "Merged", "Implemented", "Released", "Dropped")  # earlier work already reached the host
STAMP = re.compile(r"\d{14}")
OPEN_FLAGS = ("Caution", "AtRisk")  # a flag at this level or higher is already raised


def changelog_text(root, rev):
    code, text = checks.git(root, "show", f"{rev}:CHANGELOG.md")
    return text + "\n" if code == 0 else None


def new_ticket_builds(root, before, after, base="origin/main"):
    """{ticket number: (latest build stamp, branch)} for the tickets in the open version's builds that `after` has and `before` lacks.

    For a new branch (`before` all zeros) the comparison is with `base`, the changelog on main.
    """
    old = changelog_text(root, base if before == checks.ZEROS else before)
    new = changelog_text(root, after)
    if new is None:
        return {}
    known = {b.stamp for s in changelog.parse(old) for b in s.builds if b.stamp} if old else set()
    found = {}
    for section in changelog.parse(new):
        if section.kind != "wip":
            continue  # finalized versions come from main (for example after a sync), not from this push
        for build in section.builds:
            if not build.stamp or build.stamp in known:
                continue
            for block in build.blocks:
                if block.kind == "ticket" and build.stamp > found.get(block.number, ("", ""))[0]:
                    found[block.number] = (build.stamp, build.branch)
    return found


def has_earlier_work(delivery, recorded_build, stamp):
    """Whether the ticket had work before the build being pushed.

    Delivery alone is not trusted, because a person can set it by hand (or a write can land before the push
    step runs): a delivered ticket needs a recorded Build older than this one. Implemented is the exception,
    since such a ticket has no file change and gets no Build. A Build that is not a stamp counts as none.
    """
    if delivery not in DELIVERED:
        return False
    if delivery == "Implemented":
        return True
    return bool(STAMP.fullmatch(recorded_build or "")) and recorded_build < stamp


def handle_push(root, repo_client, project_client, board, before, after, dry_run=False):
    """Apply the push step to the tickets of this push. Returns the Runner."""
    run = finalize.Runner(dry_run)
    tickets = new_ticket_builds(root, before, after)
    if not tickets:
        run.log.append("no new changelog entries for a ticket in this push")
        return run
    if board is None or project_client is None:
        run.log.append("board steps skipped: no board (the preflight did not identify one)")
        return run
    fields = board.fields
    for number, (stamp, branch) in sorted(tickets.items()):
        try:
            issue, item = finalize.board_item(project_client, board, number)
            if item is None:
                item = {"id": run.do(f"#{number}: add to the board", project_client.add_to_project, board.id, issue["id"]) or "(new)"}
            status = finalize._value(item, "status", "name")
            attention = finalize._value(item, "attention", "name")
            delivery = finalize._value(item, "delivery", "name")
            recorded_build = finalize._value(item, "build", "text")
            # New work on top of earlier work, not the first push of a ticket (which may already be at Review).
            flag = status in FINISHED and has_earlier_work(delivery, recorded_build, stamp) and attention not in OPEN_FLAGS
            wanted = []
            if delivery != "Pushed":
                wanted.append(("Delivery", "Pushed", {"singleSelectOptionId": fields["Delivery"]["options"]["Pushed"]}))
            if recorded_build != stamp:
                wanted.append(("Build", stamp, {"text": stamp}))
            if status in ("ToDo", "OnDeck"):
                wanted.append(("Status", "InProgress", {"singleSelectOptionId": fields["Status"]["options"]["InProgress"]}))
            if flag:
                wanted.append(("Attention", "Caution", {"singleSelectOptionId": fields["Attention"]["options"]["Caution"]}))
            for name, shown, value in wanted:
                run.do(f"#{number}: set {name} to {shown}", project_client.set_project_field, board.id, item["id"], fields[name]["id"], value)
            if flag:
                run.do(f"#{number}: comment on the new work",
                       repo_client.comment, number,
                       condition_comments.decorate(
                           f"<!-- attention:caution -->\nAttention: Caution. New work arrived on this ticket, which is {status}: build {stamp} (branch {branch}). "
                           "Decide whether it belongs to this ticket (reopen it), is separate work (create a ticket for it), "
                           "or was only an adjustment, then tick a box below.", "new-work-on-finished-ticket"))
        except (GitHubError, KeyError) as error:
            run.log.append(f"#{number}: board update skipped: {error}")
    return run


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    after = os.environ.get("AFTER_SHA", os.environ.get("GITHUB_SHA", ""))
    before = os.environ.get("BEFORE_SHA", checks.ZEROS)
    if not repo or not after:
        print("GITHUB_REPOSITORY and AFTER_SHA (or GITHUB_SHA) must be set")
        return 1
    repo_client = Client(os.environ.get("GITHUB_TOKEN", ""), repo)
    project_client = Client(os.environ.get("PROJECT_TOKEN", ""), repo)
    report = preflight.run(repo_client, project_client, store=False)
    print(report.render())
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    run = handle_push(root, repo_client, project_client, report.board, before, after, dry_run="--dry-run" in args)
    prefix = "would: " if run.dry_run else "did: "
    for line in run.log:
        print(prefix + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
