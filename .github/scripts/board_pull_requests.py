"""Pull requests on the board.

A pull request takes a number from the same counter as the tickets, but it is not a ticket, so without this
step its number is missing from the board's All view. The step puts a pull request on the board as an item
and sets no field (a pull request has no Type, Progress or Size). The other views leave pull requests out
(`views.py` adds `is:issue` to their filters), and the sweeps skip a board item that is not an issue.

- With `PULL_REQUEST` (its number, and optionally `PULL_REQUEST_NODE_ID`) in the environment, it adds that pull
  request. This is what the workflow does when a pull request is opened or reopened. It never fails the run: a
  problem is reported and the exit code stays 0, because the advisory check must not depend on the board.
- With `--all` it adds every pull request of the repository that is not on the board yet (a one-time backfill).
- Adding is safe to repeat: a pull request that is already on the board is left alone. `--dry-run` only reports.

See the guide on project structure (section 6) and the wiki page on the automation.
"""
import os
import sys

import finalize
import preflight
from github_api import Client, GitHubError

PULL_REQUEST_ITEMS = ("query($o:String!,$n:String!,$num:Int!){repository(owner:$o,name:$n){pullRequest(number:$num){"
                      "projectItems(first:20){nodes{project{id}}}}}}")
PER_PAGE = 100


def on_board(project_client, board, number):
    """Whether the pull request is already an item of the board. Asked of the pull request itself, because the board's own
    list of items does not include the pull requests that were added to it."""
    owner, name = project_client.repo.split("/", 1)
    pull = project_client.graphql(PULL_REQUEST_ITEMS, {"o": owner, "n": name, "num": number})["repository"]["pullRequest"]
    return any((item.get("project") or {}).get("id") == board.id for item in ((pull or {}).get("projectItems") or {}).get("nodes", []))


def all_pull_requests(repo_client):
    """[(number, node id)] of every pull request of the repository, open or not."""
    found, page = [], 1
    while True:
        batch = repo_client.request("GET", repo_client.repo_path(f"/pulls?state=all&per_page={PER_PAGE}&page={page}")) or []
        found += [(pull["number"], pull["node_id"]) for pull in batch]
        if len(batch) < PER_PAGE:
            return found
        page += 1


def add(run, project_client, board, pulls):
    """Put the pull requests that are not on the board yet on it. `pulls` is [(number, node id)]."""
    for number, node_id in sorted(pulls):
        if on_board(project_client, board, number):
            run.log.append(f"#{number}: the pull request is already on the board")
            continue
        run.do(f"#{number}: add the pull request to the board", project_client.add_to_project, board.id, node_id)
    return run


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("GITHUB_REPOSITORY is not set")
        return 1
    everything = "--all" in args
    number = os.environ.get("PULL_REQUEST", "").strip()
    if not everything and not number:
        print("PULL_REQUEST (a pull request number) or --all is needed")
        return 1
    repo_client = Client(os.environ.get("GITHUB_TOKEN") or os.environ.get("PROJECT_TOKEN", ""), repo)
    project_client = Client(os.environ.get("PROJECT_TOKEN", ""), repo)
    code = 1 if everything else 0  # one pull request never fails the run; the backfill does
    report = preflight.run(repo_client, project_client, store=False)
    print(report.render())
    if report.board is None:
        print("pull requests not added: no board (the preflight did not identify one)")
        return code
    run = finalize.Runner("--dry-run" in args)
    try:
        if everything:
            pulls = all_pull_requests(repo_client)
        else:
            node_id = os.environ.get("PULL_REQUEST_NODE_ID", "").strip()
            if not node_id:
                node_id = repo_client.request("GET", repo_client.repo_path(f"/pulls/{number}"))["node_id"]
            pulls = [(int(number), node_id)]
        add(run, project_client, report.board, pulls)
    except (GitHubError, KeyError, ValueError) as error:
        print(f"pull requests not added: {error}")
        return code
    for line in run.log or ["no pull request to add"]:
        print(line if "already on the board" in line or line.startswith("no ") else ("would: " if run.dry_run else "did: ") + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
