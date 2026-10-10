"""The last step of a job that writes to the board: end it red if a write failed, stamp the board if all went well.

The Fix field and the Attention flags are values the automation writes. If it stops writing, the board keeps
showing the last result, and an empty view looks healthy. Two measures against that (guide on the new-project
bootstrap, section 4.1):

- **A loud failure.** Whatever could not be written to the board was recorded by `failures.py` while the
  other steps carried on. This step prints each as an error and exits 1, so the job ends red and GitHub sends
  its failure notice, instead of a green run with a stale board.
- **A stamp.** When nothing failed, it writes "Board checked <UTC time>" to the project's short description,
  which the organization's list of projects and the project's details panel show. Look at it when you open the
  board: an old time means the automation has stopped. A dry run never stamps.

    python .github/scripts/board_status.py [--job-status success] [--no-stamp] [--dry-run]

`--job-status` is the status of the job so far (`${{ job.status }}`): if an earlier step failed the job is red
already, and the board is not stamped.
"""
import os
import sys

import failures
import preflight
import versions
from github_api import Client, GitHubError

PREFIX = "Board checked "


def description(now):
    return f"{PREFIX}{versions.heading_time(now)} UTC"


def stamp(project_client, board, now, dry_run=False):
    """Write the stamp. Returns the text (written, or that would be)."""
    text = description(now)
    if not dry_run:
        project_client.set_project_description(board.id, text)
    return text


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    job_status = args[args.index("--job-status") + 1] if "--job-status" in args else "success"
    lines = failures.recorded()
    for line in lines:
        print(f"::error title=The board was not updated::{line}")
    if lines:
        print(f"{len(lines)} board write(s) failed: this run ends red so that nobody mistakes a stale board for a healthy one")
        return 1
    if job_status != "success":
        print(f"the job is {job_status}, so the board is not stamped")
        return 0
    if "--no-stamp" in args:
        return 0
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("GITHUB_REPOSITORY is not set")
        return 1
    repo_client = Client(os.environ.get("GITHUB_TOKEN", ""), repo)
    project_client = Client(os.environ.get("PROJECT_TOKEN", ""), repo)
    report = preflight.run(repo_client, project_client, store=False)
    if report.board is None:
        print("::error title=The board was not stamped::the preflight did not identify a board")
        return 1
    dry_run = "--dry-run" in args
    try:
        text = stamp(project_client, report.board, versions.utc_now(), dry_run)
    except GitHubError as error:
        print(f"::error title=The board was not stamped::{error}")
        return 1
    print(("would write: " if dry_run else "wrote: ") + f"the project description is now \"{text}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
