"""The retire step: record where a branch ended up with a tag, then delete it.

Given a branch, an outcome (archived, suspended or abandoned) and the branch name typed again as a
confirmation, it tags the branch's last commit `<outcome>/<yyyy-mm-dd>_<branch>[_<comment>]` (the UTC date of
that commit), and only then deletes the remote branch. It refuses `main`, a wrong confirmation, a
tag name that already exists, an archived branch whose commits are not all on main, and a suspended or
abandoned branch that still has an open pull request. For an abandoned branch it sets the Delivery of
the tickets in the branch's changelog entries to Dropped. A finished hotfix branch (its tip carries a
hotfix release tag) is deleted without a retirement tag, because that tag already keeps its history.
Closing pull requests and moving tickets to Suspended or Abandoned stay a person's steps (guide 08,
section 3). `--dry-run` only reports.
"""
import os
import re
import sys
from datetime import datetime, timezone

import checks
import finalize
import preflight
import push_step
import release
from github_api import Client, GitHubError

OUTCOMES = ("archived", "suspended", "abandoned")
COMMENT = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HOTFIX_TAG = re.compile(r"^(test/)?released/V\d+\.\d+\.\d+-HF\d$")


class RetireError(RuntimeError):
    pass


def tag_for(outcome, branch, when, comment="", trial=False):
    return f"{release.TRIAL_LEVEL if trial else ''}{outcome}/{when:%Y-%m-%d}_{branch}" + (f"_{comment}" if comment else "")


def tip(root, branch):
    code, sha = checks.git(root, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{branch}^{{commit}}")
    if code != 0:
        raise RetireError(f"the branch {branch} is not on the remote (origin/{branch} is not in this clone)")
    return sha.strip()


def commit_date(root, sha):
    _, text = checks.git(root, "log", "-1", "--format=%cI", sha)
    return datetime.fromisoformat(text.strip()).astimezone(timezone.utc)


def finished_hotfix(root, branch, sha):
    if not branch.startswith("hotfix-"):
        return False
    _, tags = checks.git(root, "tag", "--points-at", sha)
    return any(HOTFIX_TAG.match(t) for t in tags.split())


def open_pull_requests(repo_client, branch):
    owner = repo_client.repo.split("/")[0]
    return repo_client.request("GET", repo_client.repo_path(f"/pulls?state=open&head={owner}:{branch}"))


def retire(root, repo_client, project_client, board, branch, outcome, confirm, comment="", dry_run=False, trial=False):
    """Retire the branch. Returns the Runner; raises RetireError on a refusal."""
    run = finalize.Runner(dry_run)
    if outcome not in OUTCOMES:
        raise RetireError(f"the outcome must be one of {', '.join(OUTCOMES)}")
    if branch in ("main", ""):
        raise RetireError("main is never retired")
    if confirm != branch:
        raise RetireError("the confirmation must be the branch name typed again, exactly")
    if comment and not COMMENT.match(comment):
        raise RetireError("the tag comment must be short and in kebab-case")
    sha = tip(root, branch)
    on_main = checks.git(root, "merge-base", "--is-ancestor", sha, "refs/remotes/origin/main")[0] == 0
    hotfix_done = finished_hotfix(root, branch, sha)
    if outcome == "archived" and not on_main and not hotfix_done:
        raise RetireError("an archived branch must be fully merged: its last commit is not on main (suspend or abandon it instead)")
    if outcome != "archived" and open_pull_requests(repo_client, branch):
        raise RetireError("the branch still has an open pull request: close it with a comment saying why first")
    tag = tag_for(outcome, branch, commit_date(root, sha), comment, trial)
    if not hotfix_done:
        try:
            repo_client.request("GET", repo_client.repo_path(f"/git/ref/tags/{tag}"))
            raise RetireError(f"the tag {tag} already exists: add a short comment to make the name unique")
        except GitHubError as error:
            if error.status != 404:
                raise
    tickets = {}
    if outcome == "abandoned":
        tickets = push_step.new_ticket_builds(root, checks.ZEROS, f"origin/{branch}")
    if hotfix_done:
        run.log.append(f"{branch} is a finished hotfix: deleted without a retirement tag (its release tag keeps its history)")
    else:
        run.do(f"tag {sha[:7]}, the last commit of {branch}, as {tag}", repo_client.create_tag, tag, sha)
    run.do(f"delete the remote branch {branch}", repo_client.delete_ref, f"heads/{branch}")
    if tickets:
        if board is None or project_client is None:
            run.log.append("board steps skipped: no board (the preflight did not identify one)")
        else:
            dropped = {"singleSelectOptionId": board.fields["Delivery"]["options"]["Dropped"]}
            for number in sorted(tickets):
                try:
                    _, item = finalize.board_item(project_client, board, number)
                    if item is not None and finalize._value(item, "delivery", "name") != "Dropped":
                        run.do(f"#{number}: set Delivery to Dropped", project_client.set_project_field, board.id, item["id"],
                               board.fields["Delivery"]["id"], dropped)
                except GitHubError as error:
                    run.log.append(f"#{number}: board update skipped: {error}")
    return run


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    branch, outcome = os.environ.get("BRANCH", "").strip(), os.environ.get("OUTCOME", "").strip()
    confirm, comment = os.environ.get("CONFIRM", ""), os.environ.get("COMMENT", "").strip()
    if not repo or not branch or not outcome:
        print("GITHUB_REPOSITORY, BRANCH, OUTCOME (archived, suspended or abandoned) and CONFIRM must be set")
        return 1
    repo_client = Client(os.environ.get("GITHUB_TOKEN", ""), repo)
    project_client = Client(os.environ.get("PROJECT_TOKEN", ""), repo)
    report = preflight.run(repo_client, project_client, store=False)
    print(report.render())
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    try:
        run = retire(root, repo_client, project_client, report.board, branch, outcome, confirm, comment, "--dry-run" in args, release.is_trial())
    except RetireError as error:
        print(f"retire refused: {error}")
        return 1
    for line in run.log:
        print(("would: " if run.dry_run else "did: ") + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
