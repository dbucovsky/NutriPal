"""Bypass detection after a push to main, and the Alerts that go with it.

A bypass (a direct push, a merge that is not identical to its branch, a hand-resolved merge, or file
changes with no changelog entries) never blocks anyone. It is detected afterwards and recorded: one
Alert ticket and one AUTO-REF changelog entry per push, listing every flagged commit. A push with no
changelog entries at all also gets the missing version heading, so the finalize step still gives it a
version. See the guide on branching and merging (section 6.3).

Run it before the finalize step. `--dry-run` only reports what it would do. `stale` checks for
planned Version tickets that a finalized version has passed.
"""
import os
import subprocess
import sys

import alerts
import changelog
import checks
import finalize
import preflight
import versions
from github_api import Client, GitHubError

CHANGELOG = "CHANGELOG.md"


def has_pull_request(repo_client):
    def check(sha):
        try:
            return bool(repo_client.request("GET", repo_client.repo_path(f"/commits/{sha}/pulls")))
        except GitHubError:
            return True  # when in doubt, do not accuse
    return check


def commit_entry(root, alert_number, push):
    def git(*args):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)

    git("add", CHANGELOG)
    git("commit", "-m", f"Flag bypass (Alert #{alert_number})\n\nAdds the AUTO-REF changelog entry for Alert #{alert_number}, "
        "as the versioning automation does when it detects a bypass.")
    if push:
        git("push", "origin", "HEAD")  # not a bare push: a clone may have no upstream set


def handle_push(root, repo_client, project_client, board, before, after, pusher, now=None, dry_run=False, push=True):
    """Detect a bypass in the push `before..after` and record it. Returns the Runner."""
    run = finalize.Runner(dry_run)
    now = now or versions.utc_now()
    path = os.path.join(root, CHANGELOG)
    with open(path, encoding="utf-8", newline="") as handle:
        text = handle.read()
    try:
        sections = changelog.parse(text)
    except changelog.ChangelogError as error:
        title, body = alerts.changelog_error_alert(error, after, versions.heading_time(now))
        alerts.create_alert(run, repo_client, project_client, board, title, body, pusher)
        run.log.append("no version can be finalized until the changelog is corrected")
        return run
    findings = checks.flagged_commits(root, before, after, has_pull_request(repo_client))
    missing = checks.missing_entries(root, before, after)
    if not findings and not missing:
        run.log.append("no bypass detected")
        return run
    version, _, _ = finalize.decide(sections, repo_client)
    title, body = alerts.bypass_alert(findings, missing, version, after, versions.heading_time(now))
    number = alerts.create_alert(run, repo_client, project_client, board, title, body, pusher, version)
    _, explanation = alerts.bypass_headline(findings, missing)

    def write():
        stamp = versions.stamp(now)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(alerts.add_autoref(text, stamp, number, explanation, changelog.open_section(sections) is None))
        commit_entry(root, number, push)

    run.do(f"add the AUTO-REF entry for Alert #{number} to the changelog and commit it", write)
    return run


def raise_stale_alert(repo_client, project_client, board, version, dry_run=False):
    """After a version is finalized: one Alert listing planned Version tickets that cannot happen any more."""
    run = finalize.Runner(dry_run)
    planned = alerts.stale_planned(repo_client, version)
    if planned:
        title, body = alerts.stale_alert(version, planned)
        alerts.create_alert(run, repo_client, project_client, board, title, body)
    return run


def stale_command(root, repo_client, project_client, board, dry_run=False):
    """The `stale` command: check the topmost finalized version for planned tickets it has passed."""
    with open(os.path.join(root, CHANGELOG), encoding="utf-8") as handle:
        latest = changelog.latest_final(changelog.parse(handle.read()))
    if latest is None:
        run = finalize.Runner(dry_run)
        run.log.append("no finalized version")
        return run
    return raise_stale_alert(repo_client, project_client, board, latest.version, dry_run)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "stale" in args:
        repo_client = Client(os.environ.get("GITHUB_TOKEN", ""), repo)
        project_client = Client(os.environ.get("PROJECT_TOKEN", ""), repo)
        report = preflight.run(repo_client, project_client, store=False)
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
        run = stale_command(root, repo_client, project_client, report.board, "--dry-run" in args)
        for line in run.log or ["no stale planned versions"]:
            print(("would: " if run.dry_run else "did: ") + line)
        return 0
    before, after = os.environ.get("BEFORE_SHA", checks.ZEROS), os.environ.get("AFTER_SHA", os.environ.get("GITHUB_SHA", ""))
    if not repo or not after:
        print("GITHUB_REPOSITORY and AFTER_SHA (or GITHUB_SHA) must be set")
        return 1
    repo_client = Client(os.environ.get("GITHUB_TOKEN", ""), repo)
    project_client = Client(os.environ.get("PROJECT_TOKEN", ""), repo)
    report = preflight.run(repo_client, project_client, store=False)
    print(report.render())
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    run = handle_push(root, repo_client, project_client, report.board, before, after, os.environ.get("PUSHER", ""),
                      dry_run="--dry-run" in args, push="--no-push" not in args)
    prefix = "would: " if run.dry_run else "did: "
    for line in run.log:
        print(prefix + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
