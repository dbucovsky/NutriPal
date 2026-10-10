"""The fallback for a commit made without the local hooks.

A commit that changed the changelog but still has its `### WIP-Build` placeholder when it is pushed
was made with the hooks skipped. The automation fills the heading in (the commit's own UTC time, and
its hash in the heading), adds a note to the first entry under it, commits that on the branch and
pushes it. A pushed placeholder is the only trace of skipped hooks the guides say can be detected.
See the guide on starting work (section 5.1) and on branching and merging (section 6.4).

Run it before the push step. `--dry-run` only reports what it would do.
"""
import os
import subprocess
import sys
from datetime import datetime

import changelog
import checks
import finalize
import versions
from push_step import changelog_text

CHANGELOG = "CHANGELOG.md"
PLACEHOLDER = "### WIP-Build"


def has_placeholder(text):
    return text is not None and PLACEHOLDER in [line.rstrip("\r") for line in text.split("\n")]


def placeholder_commit(root, before, after, base="origin/main"):
    """(sha, UTC time) of the newest commit in the push whose changelog still has the placeholder, or None."""
    span = f"{base if before == checks.ZEROS else before}..{after}"
    _, shas = checks.git(root, "rev-list", span, "--", CHANGELOG)
    for sha in shas.split():
        if has_placeholder(changelog_text(root, sha)):
            _, when = checks.git(root, "log", "-1", "--format=%cI", sha)
            return sha, datetime.fromisoformat(when.strip())
    return None


def note_text(sha, when):
    return (f"Note from the automation: this commit ({sha[:7]}, made {versions.heading_time(when)} UTC) was pushed with the build "
            "placeholder still in the changelog, so the local hooks were skipped. The build heading was filled in here, "
            "and the commit message was not drafted from these entries.")


def repair(root, before, after, branch, base="origin/main", dry_run=False, push=True):
    """Fill in the placeholder at the tip of the push. Returns the Runner."""
    run = finalize.Runner(dry_run)
    if not has_placeholder(changelog_text(root, after)):
        run.log.append("no build placeholder in the pushed changelog")
        return run
    found = placeholder_commit(root, before, after, base)
    if found is None:
        run.log.append("the placeholder was already in the branch before this push; left alone")
        return run
    sha, when = found
    stamp = versions.stamp(when)
    path = os.path.join(root, CHANGELOG)

    def write_and_commit():
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
        text = changelog.stamp_wip_build(text, stamp, branch, sha[:7])
        text = changelog.add_note(text, stamp, note_text(sha, when))
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        subprocess.run(["git", "add", CHANGELOG], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Fill in a build heading (hooks skipped on {sha[:7]})\n\n"
                        "The changelog still had its build placeholder, so the automation filled in the heading and added a note."],
                       cwd=root, check=True, capture_output=True, text=True)
        if push:
            done = subprocess.run(["git", "push", "origin", f"HEAD:refs/heads/{branch}"], cwd=root, capture_output=True, text=True)
            if done.returncode:
                run.log.append(f"the commit could not be pushed (the branch moved on?): {done.stderr.strip().splitlines()[-1]}")

    run.do(f"fill in the build heading for {sha[:7]} as {stamp} and commit it on {branch}", write_and_commit)
    return run


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    after = os.environ.get("AFTER_SHA", os.environ.get("GITHUB_SHA", ""))
    before = os.environ.get("BEFORE_SHA", checks.ZEROS)
    branch = os.environ.get("BRANCH", "")
    if not after or not branch:
        print("AFTER_SHA (or GITHUB_SHA) and BRANCH must be set")
        return 1
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    run = repair(root, before, after, branch, dry_run="--dry-run" in args, push="--no-push" not in args)
    for line in run.log:
        print(("would: " if run.dry_run else "did: ") + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
