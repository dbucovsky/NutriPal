"""Git-only analysis behind the advisory check and the bypass detection.

Nothing here talks to GitHub: the caller says which commits have a pull request.
See the guide on branching and merging (sections 4.6 and 6.3).
"""
import subprocess
from dataclasses import dataclass

import changelog

ZEROS = "0" * 40
CHANGELOG = "CHANGELOG.md"

DIRECT_PUSH = "direct-push"
NOT_IDENTICAL = "not-identical"
MANUAL_RESOLUTION = "manual-resolution"


def git(root, *args):
    """Run git and return (exit code, standard output without the final newline)."""
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    return result.returncode, result.stdout.rstrip("\n")


@dataclass
class Finding:
    sha: str
    kind: str
    subject: str
    author: str


def behind(root, base, head):
    """How many commits of `base` (main) the `head` branch does not have."""
    return int(git(root, "rev-list", "--count", f"{head}..{base}")[1] or 0)


def parents(root, sha):
    return git(root, "rev-list", "--parents", "-n", "1", sha)[1].split()[1:]


def tree(root, rev):
    return git(root, "rev-parse", f"{rev}^{{tree}}")[1]


def merge_kind(root, sha):
    """None for an ordinary merge, else NOT_IDENTICAL or MANUAL_RESOLUTION.

    A merge is not identical when its result differs from its branch's final state (the second
    parent): the branch was not synced first, or a conflict was resolved during the merge. It is a
    manual resolution when git's own merge of the two parents is not what was committed.
    """
    first, second = parents(root, sha)[:2]
    result = tree(root, sha)
    code, automatic = git(root, "merge-tree", "--write-tree", "--no-messages", first, second)
    manual = code != 0 or automatic.split("\n")[0] != result
    if manual:
        return MANUAL_RESOLUTION
    if result != tree(root, second):
        return NOT_IDENTICAL
    return None


def manual_merges(root, base, head):
    """Merge commits in `base..head` whose content was resolved by hand (the advisory check lists them)."""
    shas = git(root, "rev-list", "--merges", f"{base}..{head}")[1].split()
    return [sha for sha in shas if merge_kind(root, sha) == MANUAL_RESOLUTION]


def _info(root, sha):
    return git(root, "log", "-1", "--format=%s%x00%an", sha)[1].split("\x00")


def _only_changelog(root, sha):
    names = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)[1].split()
    return names == [CHANGELOG]


def flagged_commits(root, before, after, has_pull_request):
    """The commits of a push to main that bypassed the flow.

    `has_pull_request(sha)` says whether a commit came in through a pull request. The version
    commit the automation makes itself (a heading rename touching only the changelog) is exempt.
    """
    span = f"{before}..{after}" if before != ZEROS else f"{after}^!"
    found = []
    for sha in git(root, "rev-list", "--first-parent", span)[1].split():
        subject, author = _info(root, sha)
        if subject.startswith("Finalize ") and _only_changelog(root, sha):
            continue
        is_merge = len(parents(root, sha)) > 1
        if not has_pull_request(sha):
            found.append(Finding(sha, DIRECT_PUSH, subject, author))
        elif is_merge:
            kind = merge_kind(root, sha)
            if kind:
                found.append(Finding(sha, kind, subject, author))
    return found


def _changelog_at(root, rev):
    code, text = git(root, "show", f"{rev}:{CHANGELOG}")
    return text + "\n" if code == 0 else None


def missing_entries(root, before, after):
    """True when files other than the changelog changed in the push but no entries were logged."""
    if before == ZEROS:
        return False
    names = git(root, "diff", "--name-only", before, after)[1].split()
    if not [n for n in names if n != CHANGELOG]:
        return False
    old, new = _changelog_at(root, before), _changelog_at(root, after)
    if new is None:
        return True
    try:
        known = {b.stamp for s in changelog.parse(old) for b in s.builds if b.stamp} if old else set()
        wip = changelog.open_section(changelog.parse(new))
    except changelog.ChangelogError:
        return False  # a malformed changelog is reported by its own Alert
    if wip is None:
        return True
    fresh = [b for b in wip.builds if (not b.stamp or b.stamp not in known) and b.blocks]
    return not fresh
