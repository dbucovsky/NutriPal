"""The advisory check on a pull request.

It fails, and comments once, when the branch is behind main. The same comment lists any merge in
the branch that carries a manual conflict resolution, as a reminder to confirm it was built and
tested. It is a warning, never a block: the merge button still works.
See the guide on branching and merging (section 4.6).
"""
import os
import sys

import checks
from github_api import Client, GitHubError

MARKER = "<!-- advisory-check -->"


def comment_text(behind_by, manual):
    lines = [MARKER, "**Advisory check**", ""]
    if behind_by:
        lines += [f"This branch is {behind_by} commit(s) behind `main`. Merge `main` into the branch, rebuild and retest, "
                  "then check again. Merging anyway is allowed, but it is detected as a bypass and raises an Alert.", ""]
    if manual:
        lines += ["These merges in the branch carry a manual conflict resolution. Confirm that the result was built and tested:"]
        lines += [f"- `{sha[:7]}`" for sha in manual]
    return "\n".join(lines).rstrip() + "\n"


def run_check(root, repo_client, pull_request, base="origin/main", head="HEAD", post=True):
    """Return (passed, comment text or None). Posts the comment once per pull request."""
    behind_by = checks.behind(root, base, head)
    manual = checks.manual_merges(root, base, head)
    if not behind_by and not manual:
        return True, None
    text = comment_text(behind_by, manual)
    if post and pull_request:
        existing = repo_client.request("GET", repo_client.repo_path(f"/issues/{pull_request}/comments?per_page=100"))
        if not any(MARKER in (c.get("body") or "") for c in existing):
            repo_client.comment(pull_request, text)
    return behind_by == 0, text


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    repo, number = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("PULL_REQUEST", "")
    if not repo:
        print("GITHUB_REPOSITORY is not set")
        return 1
    client = Client(os.environ.get("GITHUB_TOKEN", ""), repo)
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    try:
        passed, text = run_check(root, client, int(number) if number else None)
    except GitHubError as error:
        print(f"advisory check could not finish: {error}")  # a warning must not block: fail open
        return 0
    print(text or "The branch is up to date with main.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
