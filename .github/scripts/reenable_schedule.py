"""Turn the scheduled workflow back on after GitHub switched it off for inactivity.

GitHub disables the scheduled workflows of a public repository after 60 days without repository activity, and
a disabled workflow runs on no event, so `versioning.yml` cannot wake itself. This step belongs to a separate
workflow with no schedule (so it is never disabled) that runs on every push.

- State `disabled_inactivity`: the workflow is enabled again.
- State `active`: nothing to do.
- Any other state (`disabled_manually`, `disabled_fork`, `deleted`): left alone, because a person chose it.

`--dry-run` only reports. A failure to enable fails the run, so it shows. See the wiki page on the automation.
"""
import os
import sys

from github_api import Client, GitHubError

WORKFLOW = "versioning.yml"
REENABLE = "disabled_inactivity"


def decide(state):
    """"enable" for a workflow GitHub switched off for inactivity, "leave" for any other state."""
    return "enable" if state == REENABLE else "leave"


def state_of(client, workflow=WORKFLOW):
    return client.request("GET", client.repo_path(f"/actions/workflows/{workflow}"))["state"]


def enable(client, workflow=WORKFLOW):
    client.request("PUT", client.repo_path(f"/actions/workflows/{workflow}/enable"))


def run(client, dry_run=False, workflow=WORKFLOW):
    """The report lines; raises GitHubError when the state cannot be read or the workflow cannot be enabled."""
    state = state_of(client, workflow)
    if decide(state) == "leave":
        return [f"{workflow} is {state}: nothing to do"]
    if dry_run:
        return [f"{workflow} is {state}: would enable it"]
    enable(client, workflow)
    return [f"{workflow} was {state}: enabled it"]


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("GITHUB_REPOSITORY is not set")
        return 1
    client = Client(os.environ.get("GITHUB_TOKEN", ""), repo)
    try:
        lines = run(client, "--dry-run" in args)
    except GitHubError as error:
        print(f"could not check or enable {WORKFLOW}: {error}")
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
