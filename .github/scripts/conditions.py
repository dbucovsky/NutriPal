"""The conditions the board shows: one registry, and the refresh of the Fix field.

A *condition* is something about a ticket that the board should draw attention to. There are three natures,
and each has its own view (guide on issues and the board, section 2.2):

- **decide**: the automation noticed something and a person must judge it (a stale ticket, new work on a
  finished ticket, a passed version, an open Alert). The detectors are in `watch.py`, `push_step.py`,
  `implemented.py` and `bypass.py`; the registry only describes them.
- **follow-up**: an ordinary queue, set and cleared by people (Waiting, Review).
- **fix**: the fields of a ticket contradict each other (the rules of the guide on project structure, section
  4.4). These are derived: their state is a pure function of the ticket's other fields, so nobody sets or
  clears them. `refresh` recomputes the set of broken rules of every ticket and writes it to the board's
  "Fix" field (the ids, separated by spaces; empty when nothing is broken), only when it changed. A person
  fixes the cause, and the id disappears at the next refresh.

A new condition is one new entry in `CONDITIONS` (and, for a fix rule, its detector function). The views, the
field and the guides' tables read the registry, so nothing else has to change.

Run by hand: `python .github/scripts/conditions.py [--dry-run]`.
"""
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

import condition_comments as cc
import failures
import finalize
import preflight
import versions
from github_api import Client, GitHubError

DECIDE, FOLLOW_UP, FIX = "decide", "follow-up", "fix"
FIX_FIELD = "Fix"
FIX_COMMENT_AFTER = timedelta(hours=2)  # a broken rule is put in a comment only when the ticket has not changed for this long

OPEN = ("ToDo", "OnDeck", "InProgress", "Review", "Suspended")
CLOSED = ("Completed", "Abandoned")
SHIPPED = ("Merged", "Implemented", "Released")
REASONS = ("Duplicate", "Invalid", "WontFix", "Superseded", "Obsolete")
NOT_WORK = ("Version", "Alert")  # bookkeeping tickets: no Delivery, no Attention


@dataclass(frozen=True)
class Condition:
    id: str
    name: str
    nature: str
    summary: str
    detected_by: str
    cleared_by: str
    level: str = ""  # the Attention level of a decide condition
    detect: Callable = None  # a fix rule: ticket -> the explanation when it is broken, else None


# --- the fix rules: pure functions of the ticket (see board_tickets for its keys) -------------------------

def completed_without_done(t):
    if t["status"] == "Completed" and t["resolution"] != "Done":
        return "it is Completed but its Resolution is not Done"


def abandoned_without_reason(t):
    if t["status"] == "Abandoned" and t["resolution"] not in REASONS:
        return "it is Abandoned but its Resolution is not one of the abandon reasons"


def open_with_resolution(t):
    if t["status"] in OPEN and t["resolution"]:
        return f"it is open ({t['status']}) but has the Resolution {t['resolution']}"


def open_with_end_date(t):
    if t["status"] in OPEN and t["end"]:
        return f"it is open ({t['status']}) but has the End date {t['end']}"


def waiting_on_closed(t):
    if t["status"] in CLOSED and t["waiting"]:
        return f"it is {t['status']} but Waiting is still set"


def backfilled_without_ref(t):
    if t["origin"] == "Backfilled" and not t["ref"]:
        return "its Origin is Backfilled but its REF is blank"


def completed_without_delivery(t):
    if t["status"] == "Completed" and not t["delivery"] and t["type"] not in NOT_WORK:
        return ("it is Completed but its Delivery is blank (set Implemented if no file changed, "
                "Merged if files did, or set Abandoned with a reason if nothing came of it)")


def shipped_without_version(t):
    if t["delivery"] in SHIPPED and not t["version"].strip() and t["status"] != "Abandoned" and t["type"] not in NOT_WORK:
        return (f"its Delivery is {t['delivery']} but its Version is blank (the scheduled run or the "
                "finalize step should have set it: set the Version of the version it belongs to)")


def issue_open(t):
    if t["status"] in CLOSED and t["state"] == "OPEN":
        return f"it is {t['status']} but its issue is still open"


def issue_closed(t):
    if t["status"] not in CLOSED and t["state"] == "CLOSED":
        return f"its issue is closed but it is {t['status']}"


_AUTOMATION = "the refresh (conditions.py)"
_FIXES = "nobody: it goes when the fields agree again"

CONDITIONS = (
    # decide
    Condition("stale", "Stale", DECIDE, "No activity for too long: a week at Review, a month at OnDeck or InProgress, six months at Suspended.",
              "watch.py", "a person ticks a box (Fine or Handled elsewhere)", level="Watch"),
    Condition("waited-too-long", "Waited too long", DECIDE, "A ticket has waited for input for two weeks.",
              "watch.py", "a person ticks a box (Fine or Handled elsewhere)", level="Watch"),
    Condition("new-work-on-finished-ticket", "New work on a finished ticket", DECIDE,
              "A push brought work to a Completed, Abandoned, Review or Suspended ticket whose earlier work was already pushed or delivered.",
              "push_step.py", "a person ticks a box (Fine or Handled elsewhere)", level="Caution"),
    Condition("passed-version", "Aimed at a passed version", DECIDE,
              "An Implemented ticket is aimed at a version that was passed, so it can never be attached.",
              "implemented.py", "a person ticks a box (Fine or Handled elsewhere)", level="Caution"),
    Condition("open-alert", "Open Alert", DECIDE, "A bypass, a merge without changelog entries, an unreadable changelog or stale planned versions.",
              "bypass.py", "a person, through InProgress, Review and Completed"),
    # follow-up
    Condition("waiting", "Waiting", FOLLOW_UP, "Someone owes an answer (Waiting is Needs input).",
              "a person sets it", "a person, when it is answered; always at Completed or Abandoned"),
    Condition("review", "Review", FOLLOW_UP, "The work is done and waits for verification (Progress is Review).",
              "a person sets it", "a person: Completed with Done, or back to InProgress"),
    # fix
    Condition("completed-without-done", "Completed without Done", FIX, "A Completed ticket has Resolution Done.",
              _AUTOMATION, _FIXES, detect=completed_without_done),
    Condition("abandoned-without-reason", "Abandoned without a reason", FIX, "An Abandoned ticket has one of the abandon reasons as Resolution.",
              _AUTOMATION, _FIXES, detect=abandoned_without_reason),
    Condition("open-with-resolution", "Open with a Resolution", FIX, "An open ticket (ToDo, OnDeck, InProgress, Review, Suspended) has no Resolution.",
              _AUTOMATION, _FIXES, detect=open_with_resolution),
    Condition("open-with-end-date", "Open with an End date", FIX, "An open ticket has no End date.",
              _AUTOMATION, _FIXES, detect=open_with_end_date),
    Condition("waiting-on-closed", "Waiting on a closed ticket", FIX, "Waiting is only on open tickets.",
              _AUTOMATION, _FIXES, detect=waiting_on_closed),
    Condition("backfilled-without-ref", "Backfilled without a REF", FIX, "A Backfilled ticket has its REF.",
              _AUTOMATION, _FIXES, detect=backfilled_without_ref),
    Condition("completed-without-delivery", "Completed without a Delivery", FIX,
              "A Completed work ticket has a Delivery (Merged if files changed, Implemented if none did).",
              _AUTOMATION, _FIXES, detect=completed_without_delivery),
    Condition("shipped-without-version", "Shipped without a Version", FIX,
              "Shipped work (Delivery Merged, Implemented or Released) has a Version; an Abandoned ticket is left out.",
              _AUTOMATION, _FIXES, detect=shipped_without_version),
    Condition("issue-open", "Issue still open", FIX, "A Completed or Abandoned ticket has its issue closed.",
              _AUTOMATION, _FIXES, detect=issue_open),
    Condition("issue-closed", "Issue closed too soon", FIX, "An issue is closed only at Completed or Abandoned.",
              _AUTOMATION, _FIXES, detect=issue_closed),
)

BY_ID = {c.id: c for c in CONDITIONS}
FIX_RULES = tuple(c for c in CONDITIONS if c.nature == FIX)
DECIDE_LEVELS = {c.id: c.level for c in CONDITIONS if c.nature == DECIDE and c.level}


def broken_rules(ticket):
    """The fix rules a ticket breaks, as {rule id: explanation}, in the registry's order."""
    if not ticket["status"]:
        return {}  # a Version ticket has no Progress
    broken = {}
    for rule in FIX_RULES:
        why = rule.detect(ticket)
        if why:
            broken[rule.id] = why
    return broken


def fix_value(broken):
    """What the Fix field holds for a set of broken rules: their ids separated by spaces, or nothing."""
    return " ".join(rule.id for rule in FIX_RULES if rule.id in broken)


# --- reading the board --------------------------------------------------------------------------------------

ITEMS = ("query($id:ID!,$after:String){node(id:$id){... on ProjectV2{items(first:100,after:$after){"
         "pageInfo{hasNextPage endCursor} nodes{id updatedAt "
         "content{... on Issue{number state updatedAt issueType{name}}} "
         "status:fieldValueByName(name:\"Status\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "resolution:fieldValueByName(name:\"Resolution\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "waiting:fieldValueByName(name:\"Waiting\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "delivery:fieldValueByName(name:\"Delivery\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "origin:fieldValueByName(name:\"Origin\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "attention:fieldValueByName(name:\"Attention\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "version:fieldValueByName(name:\"Version\"){... on ProjectV2ItemFieldTextValue{text}} "
         "ref:fieldValueByName(name:\"REF\"){... on ProjectV2ItemFieldTextValue{text}} "
         "fix:fieldValueByName(name:\"Fix\"){... on ProjectV2ItemFieldTextValue{text}} "
         "end:fieldValueByName(name:\"End date\"){... on ProjectV2ItemFieldDateValue{date}}}}}}}")


def board_tickets(project_client, board):
    """Every issue on the board with the values the rules read."""
    found, after = [], None
    while True:
        page = project_client.graphql(ITEMS, {"id": board.id, "after": after})["node"]["items"]
        for node in page["nodes"]:
            content = node.get("content") or {}
            if not content.get("number"):
                continue

            def name(key):
                return (node.get(key) or {}).get("name")

            found.append({"item": node["id"], "number": content["number"], "item_updated": node["updatedAt"],
                          "issue_updated": content["updatedAt"], "state": content["state"],
                          "type": (content.get("issueType") or {}).get("name"),
                          "status": name("status"), "delivery": name("delivery"), "resolution": name("resolution"), "waiting": name("waiting"),
                          "origin": name("origin"), "attention": name("attention"),
                          "ref": (node.get("ref") or {}).get("text") or "",
                          "version": (node.get("version") or {}).get("text") or "",
                          "fix": (node.get("fix") or {}).get("text") or "",
                          "end": (node.get("end") or {}).get("date")})
        if not page["pageInfo"]["hasNextPage"]:
            return found
        after = page["pageInfo"]["endCursor"]


# --- the refresh --------------------------------------------------------------------------------------------

def sync_comments(run, repo_client, ticket, broken, now):
    """Keep the ticket's condition comments in step with the board.

    The comments are read fresh just before anything is edited, and an edit changes only the automation's own
    lines, so a box ticked a moment ago is never lost.
    - a decide comment whose boxes are ticked moves Attention (cc.attention_after); damaged boxes are put back;
    - a fix rule still broken after FIX_COMMENT_AFTER gets a comment, and one that is no longer broken has its
      comment edited to say it was fixed.
    Returns the Attention value to set, or None."""
    number = ticket["number"]
    comments = repo_client.list_comments(number)
    ours = [(c, cc.condition_of(c.get("body"))) for c in comments]
    ours = [(c, i) for c, i in ours if i and c.get("user", {}).get("type") == "Bot"]
    decide = []
    for comment, condition_id in ours:
        if condition_id not in DECIDE_LEVELS or cc.is_fixed(comment["body"]):
            continue
        current = cc.state(comment["body"])
        if current == "damaged":
            run.do(f"#{number}: put back the boxes of the {condition_id} comment", repo_client.edit_comment, comment["id"], cc.restore(comment["body"]))
        decide.append((condition_id, current))
    quiet = now - datetime.fromisoformat(ticket["item_updated"].replace("Z", "+00:00"))
    for rule in FIX_RULES:
        open_comments = [c for c, i in ours if i == rule.id and cc.is_fix_comment(c["body"]) and not cc.is_fixed(c["body"])]
        if rule.id in broken:
            if not open_comments and quiet >= FIX_COMMENT_AFTER:
                run.do(f"#{number}: comment on the broken rule {rule.id}", repo_client.comment, number, cc.fix_comment(rule.id, broken[rule.id]))
        else:
            for comment in open_comments:
                run.do(f"#{number}: mark the {rule.id} comment fixed", repo_client.edit_comment, comment["id"],
                       cc.mark_fixed(comment["body"], now.strftime("%Y-%m-%d")))
    return cc.attention_after(decide, ticket["attention"], DECIDE_LEVELS)


def needs_comments(ticket, broken):
    """Whether the ticket's comments must be read: it has a flag the boxes can clear, or a rule broken now or before."""
    return bool(broken) or bool(ticket["fix"]) or ticket["attention"] in ("Watch", "Caution")


def refresh(run, project_client, board, repo_client=None, now=None):
    """Write the Fix field of every ticket whose set of broken rules changed, and keep the comments in step.
    Returns the numbers changed.

    There is no wait for the field: it is live, so a ticket in the middle of an edit shows and then clears at the
    next refresh. A comment about a broken rule does wait (FIX_COMMENT_AFTER). Without `repo_client` no comment is
    read or written.
    """
    field = board.fields.get(FIX_FIELD)
    if field is None:
        run.log.append(f"the board has no {FIX_FIELD} field, so nothing is written (create it with fields.py --apply)")
        return []
    now = now or versions.utc_now()
    attention = board.fields.get("Attention")
    changed = []
    for ticket in board_tickets(project_client, board):
        broken = broken_rules(ticket)
        wanted = fix_value(broken)
        number = ticket["number"]
        if wanted != ticket["fix"]:
            if wanted:
                run.do(f"#{number}: set {FIX_FIELD} to {wanted}", project_client.set_project_field,
                       board.id, ticket["item"], field["id"], {"text": wanted})
            else:
                run.do(f"#{number}: clear {FIX_FIELD} (was {ticket['fix']})", project_client.clear_project_field,
                       board.id, ticket["item"], field["id"])
            changed.append(number)
        if repo_client is None or not needs_comments(ticket, broken):
            continue
        new_attention = sync_comments(run, repo_client, ticket, broken, now)
        if new_attention and attention and new_attention in attention["options"]:
            run.do(f"#{number}: set Attention to {new_attention} (from the boxes in its comments)", project_client.set_project_field,
                   board.id, ticket["item"], attention["id"], {"singleSelectOptionId": attention["options"][new_attention]})
    return changed


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
        print("conditions skipped: no board (the preflight did not identify one)")
        return 0
    run = finalize.Runner("--dry-run" in args)
    try:
        refresh(run, project_client, report.board, repo_client)
    except GitHubError as error:
        run.log.append(f"the refresh of the conditions stopped: {error}")
        failures.record(f"the refresh of the conditions stopped: {error}")
    for line in run.log or ["no ticket's Fix field needs a change"]:
        print(("would: " if run.dry_run else "did: ") + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
