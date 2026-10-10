"""The release step: declare a finalized version a release.

Given a finalized version (by default the latest), it tags the commit where that version was finalized
as `released/V<major>.<sub>.<mod>`, sets the Version ticket to Delivery Released with a comment giving the
date and the tag, and sets to Released every ticket whose Delivery is Merged or Implemented and whose
version is at or below the released one. A ticket with newer work pushed (Delivery Pushed) keeps it.
A version has at most one release tag, and only a finalized version can be released. Verifying the
version first is the developer's step (guide 08, section 1.1). `--dry-run` only reports.
"""
import os
import sys

import changelog
import checks
import finalize
import implemented
import preflight
import versions
from github_api import Client, GitHubError
from versions import Version

CHANGELOG = "CHANGELOG.md"
RELEASABLE = ("Merged", "Implemented")
NO_RELEASE = ("Version", "Alert")

ITEMS = ("query($id:ID!,$after:String){node(id:$id){... on ProjectV2{items(first:100,after:$after){"
         "pageInfo{hasNextPage endCursor} nodes{id content{... on Issue{number issueType{name}}} "
         "delivery:fieldValueByName(name:\"Delivery\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "version:fieldValueByName(name:\"Version\"){... on ProjectV2ItemFieldTextValue{text}}}}}}}")


class ReleaseError(RuntimeError):
    pass


TRIAL_LEVEL = "test/"  # a trial keeps its tags under this level, so the real namespaces stay true


def is_trial(env=None):
    """Whether the manual run is a trial: the workflow input `trial` is passed as TRIAL=true."""
    return (env if env is not None else os.environ).get("TRIAL", "").strip().lower() == "true"


def tag_name(version, trial=False):
    return f"{TRIAL_LEVEL if trial else ''}released/{version}"


def finalized_versions(root):
    with open(os.path.join(root, CHANGELOG), encoding="utf-8") as handle:
        return [s.version for s in changelog.parse(handle.read()) if s.kind == "final"]


def finalize_commit(root, version):
    """The commit where the version heading first appears: where the version was finalized."""
    _, out = checks.git(root, "log", "--reverse", "--format=%H", f"-S## {version} ", "--", CHANGELOG)
    shas = out.split()
    return shas[0] if shas else None


def tag_exists(repo_client, tag):
    try:
        repo_client.request("GET", repo_client.repo_path(f"/git/ref/tags/{tag}"))
        return True
    except GitHubError as error:
        if error.status == 404:
            return False
        raise


def releasable_tickets(project_client, board, version):
    """The board tickets that become Released: Merged or Implemented, at or below `version`."""
    found, after = [], None
    while True:
        page = project_client.graphql(ITEMS, {"id": board.id, "after": after})["node"]["items"]
        for node in page["nodes"]:
            content = node.get("content") or {}
            if not content.get("number") or (content.get("issueType") or {}).get("name") in NO_RELEASE:
                continue
            if (node.get("delivery") or {}).get("name") not in RELEASABLE:
                continue
            try:
                theirs = Version.parse((node.get("version") or {}).get("text") or "")
            except ValueError:
                continue
            if theirs.number() <= version.number():
                found.append((content["number"], node["id"]))
        if not page["pageInfo"]["hasNextPage"]:
            return found
        after = page["pageInfo"]["endCursor"]


def release(root, repo_client, project_client, board, version=None, now=None, dry_run=False, trial=False):
    """Release `version` (the latest finalized one if None). Returns the Runner; raises ReleaseError on a refusal."""
    run = finalize.Runner(dry_run)
    now = now or versions.utc_now()
    finals = finalized_versions(root)
    if not finals:
        raise ReleaseError("no finalized version in the changelog")
    version = version or finals[0]
    if version not in finals:
        raise ReleaseError(f"{version} is not a finalized version of this changelog, so it cannot be released")
    tag = tag_name(version, trial)
    if tag_exists(repo_client, tag):
        raise ReleaseError(f"{version} already has the release tag {tag}: a version has at most one")
    sha = finalize_commit(root, version)
    if sha is None:
        raise ReleaseError(f"cannot find the commit where {version} was finalized")
    ticket = implemented.version_ticket(repo_client, version)
    if ticket is None or ticket["state"] != "closed":
        raise ReleaseError(f"{version} has no finalized Version ticket")
    run.do(f"tag {sha[:7]} (where {version} was finalized) as {tag}", repo_client.create_tag, tag, sha)
    if board is None or project_client is None:
        run.log.append("board steps skipped: no board (the preflight did not identify one)")
    else:
        released = {"singleSelectOptionId": board.fields["Delivery"]["options"]["Released"]}
        delivery = board.fields["Delivery"]["id"]
        try:
            _, item = finalize.board_item(project_client, board, ticket["number"])
            if item is not None:
                run.do(f"Version ticket #{ticket['number']}: set Delivery to Released", project_client.set_project_field,
                       board.id, item["id"], delivery, released)
            for number, item_id in releasable_tickets(project_client, board, version):
                run.do(f"#{number}: set Delivery to Released", project_client.set_project_field, board.id, item_id, delivery, released)
        except GitHubError as error:
            run.log.append(f"board steps stopped: {error}")
    run.do(f"Version ticket #{ticket['number']}: comment with the date and the tag", repo_client.comment, ticket["number"],
           f"Released {now:%Y-%m-%d %H:%M} UTC. Tag: `{tag}`.")
    return run


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
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    asked = os.environ.get("VERSION", "").strip()
    try:
        version = Version.parse(asked) if asked else None
        run = release(root, repo_client, project_client, report.board, version, dry_run="--dry-run" in args, trial=is_trial())
    except (ReleaseError, ValueError) as error:
        print(f"release refused: {error}")
        return 1
    for line in run.log:
        print(("would: " if run.dry_run else "did: ") + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
