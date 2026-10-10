"""The hotfix-finalize step: finish a hotfix with an explicit version.

A hotfix starts from a release tag and is never merged into main, so it has nothing to compute its
version from. Run on the hotfix branch with the version (for example `V1.25.0-HF1`), it renames the open
`## WIP-Version` heading to that version in a commit of its own on the branch, tags that commit
`released/V1.25.0-HF1`, creates the Version ticket, and sets the tickets' Delivery straight to
Released (a hotfix is never merged, so it skips Merged). It refuses a marker on the heading, a branch
that is not named for the release, a branch that does not contain the release (or the previous
hotfix's) tag, a hotfix number outside 1 to 9, and a version that already has its tag. The finished
branch is deleted afterwards without a retirement tag. See the guide on releases and hotfixes
(section 2). `--dry-run` only reports.
"""
import os
import subprocess
import sys

import changelog
import checks
import finalize
import preflight
import release
import versions
from github_api import Client, GitHubError
from versions import Version

CHANGELOG = "CHANGELOG.md"


class HotfixError(RuntimeError):
    pass


def branch_prefix(version):
    return f"hotfix-v{version.major}-{version.sub}-{version.mod}-"


def base_tag(version, trial=False):
    """The tag the hotfix starts from: the release, or the previous hotfix of that release."""
    base = Version(version.major, version.sub, version.mod)
    return release.tag_name(base if version.hotfix == 1 else Version(version.major, version.sub, version.mod, version.hotfix - 1), trial)


def check(root, repo_client, version, branch, trial=False):
    """Refuse a hotfix that does not follow the rules. Returns the open section of the changelog."""
    if not 1 <= version.hotfix <= 9:
        raise HotfixError("a hotfix version needs a number from 1 to 9 (V1.25.0-HF1); a release that would need a tenth "
                          "hotfix should be replaced: finish the fix on main and release that version")
    if not branch.startswith(branch_prefix(version)):
        raise HotfixError(f"the branch {branch} is not named for this release: expected {branch_prefix(version)}<description>")
    with open(os.path.join(root, CHANGELOG), encoding="utf-8") as handle:
        sections = changelog.parse(handle.read())
    wip = changelog.open_section(sections)
    if wip is None:
        raise HotfixError("the changelog has no open WIP-Version heading to finalize")
    if wip.marker:
        raise HotfixError(f"markers are not allowed on a hotfix branch (found {wip.marker})")
    if not wip.ticket_numbers():
        raise HotfixError("the open version has no ticket entry: a hotfix is finished with its tickets in the changelog")
    if version in [s.version for s in sections if s.kind == "final"]:
        raise HotfixError(f"{version} is already a finalized version in the changelog")
    tag = release.tag_name(version, trial)
    if release.tag_exists(repo_client, tag):
        raise HotfixError(f"{version} already has the release tag {tag}: a version has at most one")
    base = base_tag(version, trial)
    code, tag_sha = checks.git(root, "rev-parse", "-q", "--verify", f"refs/tags/{base}^{{commit}}")
    if code != 0:
        raise HotfixError(f"the tag {base} is not in this clone (a hotfix starts from it, and it must exist)")
    if checks.git(root, "merge-base", "--is-ancestor", tag_sha.strip(), "HEAD")[0] != 0:
        raise HotfixError(f"the branch does not contain {base}: a hotfix branch starts from that tag, never from main")
    return wip


def finish(root, repo_client, project_client, board, version, branch, now=None, dry_run=False, push=True, trial=False):
    """Finish the hotfix. Returns the Runner; raises HotfixError on a refusal."""
    run = finalize.Runner(dry_run)
    now = now or versions.utc_now()
    wip = check(root, repo_client, version, branch, trial)
    when = versions.heading_time(now)
    path = os.path.join(root, CHANGELOG)
    tag = release.tag_name(version, trial)
    tickets = wip.ticket_numbers()
    types = {n: repo_client.issue_type(n) for n in tickets}
    titles = {b.number: b.title for b in wip.blocks() if b.kind == "ticket"}
    builds = finalize.ticket_builds(wip)
    last_build = wip.last_build()
    state = {}

    def rename_and_push():
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(changelog.rename_open_heading(text, version, when))
        subprocess.run(["git", "add", CHANGELOG], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Finalize {version}\n\nRenames the open WIP-Version heading to {version}, "
                        "as the hotfix finish step does. A hotfix is never merged into main."], cwd=root, check=True, capture_output=True, text=True)
        if push:
            subprocess.run(["git", "push", "origin", f"HEAD:refs/heads/{branch}"], cwd=root, check=True, capture_output=True, text=True)
        state["sha"] = checks.git(root, "rev-parse", "HEAD")[1].strip()

    run.do(f"rename the open WIP-Version heading to {version} — {when} UTC and commit it on {branch}", rename_and_push)
    run.do(f"tag the finalizing commit as {tag}", lambda: repo_client.create_tag(tag, state["sha"]))
    if board is None or project_client is None:
        run.log.append("board steps skipped: no board (the preflight did not identify one)")
    else:
        for number in tickets:
            try:
                finalize.update_ticket(run, project_client, board, number, version, builds.get(number), delivery="Released")
            except GitHubError as error:
                run.log.append(f"#{number}: board update skipped: {error}")
    listing = [(n, titles[n], types[n] or "no Type") for n in tickets]
    bump = f"hotfix of {Version(version.major, version.sub, version.mod)}, with the version stated explicitly"
    number = finalize.record_version_ticket(run, repo_client, project_client, board, version, when, bump, None, last_build, listing,
                                            delivery="Released", source=f"the hotfix branch {branch}")
    run.do(f"Version ticket #{number}: comment with the date and the tag", repo_client.comment, number,
           f"Released {now:%Y-%m-%d %H:%M} UTC. Tag: `{tag}`. The hotfix branch {branch} may now be deleted (no retirement tag).")
    return run


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    asked, branch = os.environ.get("VERSION", "").strip(), os.environ.get("BRANCH", "").strip()
    if not repo or not asked or not branch:
        print("GITHUB_REPOSITORY, VERSION (for example V1.25.0-HF1) and BRANCH must be set")
        return 1
    repo_client = Client(os.environ.get("GITHUB_TOKEN", ""), repo)
    project_client = Client(os.environ.get("PROJECT_TOKEN", ""), repo)
    report = preflight.run(repo_client, project_client, store=False)
    print(report.render())
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    try:
        run = finish(root, repo_client, project_client, report.board, Version.parse(asked), branch, dry_run="--dry-run" in args,
                     trial=release.is_trial())
    except (HotfixError, ValueError) as error:
        print(f"hotfix finish refused: {error}")
        return 1
    for line in run.log:
        print(("would: " if run.dry_run else "did: ") + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
