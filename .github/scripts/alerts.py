"""Alert tickets and the AUTO-REF changelog entry.

An Alert is raised when a rule was bypassed, a push landed without changelog entries, the
changelog could not be read, or planned versions can no longer happen. It has Priority
Critical, Area process and Progress ToDo; every later move is a person's.
See the guide on project structure (section 5.3) and on issues and the board (section 5).
"""
import re

import checks
from github_api import GitHubError
from versions import Version

_PLANNED = re.compile(r"^Version (\d+\.\d+\.\d+)$")

HEADLINES = {
    checks.DIRECT_PUSH: ("Direct push to main",
                         "This push reached main without a pull request."),
    checks.NOT_IDENTICAL: ("Merge to main not identical to its branch",
                           "This merge's result is not identical to its branch's final state. The sync-first rule was not "
                           "followed, or a conflict was resolved during the merge itself rather than beforehand on the branch."),
    checks.MANUAL_RESOLUTION: ("Merge to main resolved by hand",
                               "This merge differs from what git's own merge of its two parents gives: a conflict was "
                               "resolved by hand and nobody verified the result."),
}
NO_ENTRIES = ("Merge to main without changelog entries",
              "File changes reached main with no changelog entries.")


def bypass_headline(findings, missing):
    """The title, and the explanation for the changelog entry, of the one Alert for a push."""
    for kind in (checks.DIRECT_PUSH, checks.NOT_IDENTICAL, checks.MANUAL_RESOLUTION):
        if any(f.kind == kind for f in findings):
            return HEADLINES[kind]
    return NO_ENTRIES


def bypass_alert(findings, missing, version, push_sha, when):
    """(title, body) of the Alert for one push to main. Every flagged commit is listed."""
    headline, explanation = bypass_headline(findings, missing)
    lines = [f"Detected on the push of {when} UTC to `main` (commit `{push_sha[:7]}`): {explanation[0].lower()}{explanation[1:]}", ""]
    if findings:
        lines.append("Flagged commits:")
        lines += [f"- `{f.sha[:7]}` {f.subject} ({f.kind}, by {f.author})" for f in findings]
        lines.append("")
    if missing:
        lines += ["The push also changed files with no changelog entries: the automation created the version and the "
                  "changelog entry itself, with a mod bump.", ""]
    lines += ["**To do.** Confirm that the merged result was built and tested, and document anything that changed in the "
              "changelog (in the entry that points at this ticket, or in a new block in the current version)."]
    return f"{headline} ({version})", "\n".join(lines) + "\n"


def stale_alert(version, planned):
    """(title, body) of the Alert for planned Version tickets that can no longer happen."""
    listing = ", ".join(f"#{number} {title}" for number, title in planned)
    body = (f"Version {str(version)[1:]} was finalized. These planned Version tickets have a lower number and cannot "
            f"happen under it: {listing}.\n\n**To do.** For each one, set Delivery to *Dropped* and close it with a "
            "comment saying what replaced it, or correct the number if it was a mistake.\n")
    return f"Stale planned Version tickets after {version}", body


def changelog_error_alert(error, push_sha, when):
    body = (f"Detected on the push of {when} UTC to `main` (commit `{push_sha[:7]}`): the changelog could not be read, so no "
            f"version was finalized.\n\n> {error}\n\n**To do.** Correct `CHANGELOG.md` by hand (one open `WIP-Version` "
            "heading, with at most one marker and no other text), then run the finalize step again.\n")
    return "Changelog error on main: no version finalized", body


def stale_planned(repo_client, version):
    """Open planned Version tickets numbered below `version` as (issue number, title). Hotfix versions are not checked."""
    if version.hotfix:
        return []
    found = []
    for page in range(1, 11):
        issues = repo_client.request("GET", repo_client.repo_path(f"/issues?state=open&type=Version&per_page=100&page={page}"))
        for issue in issues:
            match = _PLANNED.match(issue["title"])
            if match and Version.parse("V" + match.group(1)).number() < version.number():
                found.append((issue["number"], issue["title"]))
        if len(issues) < 100:
            break
    return sorted(found)


def create_alert(run, repo_client, project_client, board, title, body, assignee=None, version=None):
    """Create the Alert ticket and put it on the board as Critical and ToDo. Returns its number."""
    created = run.do(f"create the Alert \"{title}\"", repo_client.create_issue, title, body, "Alert", ["process"],
                     [assignee] if assignee else [])
    number = created["number"] if created else 0
    if board is None or project_client is None:
        run.log.append(f"Alert \"{title}\": board fields skipped: no board")
        return number
    try:
        item = run.do(f"Alert \"{title}\": add to the board", project_client.add_to_project, board.id, created["node_id"] if created else None)
        for name, value in (("Priority", "Critical"), ("Status", "ToDo")):
            run.do(f"Alert \"{title}\": set {name} to {value}", project_client.set_project_field, board.id, item,
                   board.fields[name]["id"], {"singleSelectOptionId": board.fields[name]["options"][value]})
    except (GitHubError, KeyError) as error:
        run.log.append(f"Alert \"{title}\": board fields skipped: {error}")
    return number


def add_autoref(text, stamp, alert_number, explanation, created_version):
    """Return the changelog text with an AUTO-REF entry pointing at the Alert.

    The entry goes in a new build at the top of the open version. When there is no open version,
    one is created, so the merge still produces a version.
    """
    tail = ("Issue #%d opened automatically for review: document the change once triaged." % alert_number)
    bullet = f"- **Auto-flagged: {explanation}** {tail}"
    if created_version:
        bullet = (f"- **Auto-flagged: {explanation}** The version and this entry were created automatically. "
                  f"{tail}")
    build = f"### Build {stamp} (branch main)\n#### AUTO-REF {stamp} (tracked as #{alert_number})\n{bullet}\n"
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if line.startswith("## WIP-Version"):
            lines[index + 1:index + 1] = build.rstrip("\n").split("\n")
            return "\n".join(lines)
    heading = "## WIP-Version\n" + build + "\n"
    if text.startswith("# "):
        first_break = text.index("\n") + 1
        rest = text[first_break:].lstrip("\n")
        return text[:first_break] + "\n" + heading + rest
    return heading + text
