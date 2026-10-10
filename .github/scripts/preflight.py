"""The preflight: the first thing the automation does, on every run and on request.

It checks, in order, that the repository is reachable with the permissions needed, that the
project token works, which board belongs to the repository (and stores its number in a
repository variable), and that the board has the fields and values the automation needs.
When a check fails it says which one and why, and the steps that depend on it are skipped.
It also warns, and only warns, about a repository setting that differs from the bootstrap guide
(merge methods, branch deletion, default branch, issues, projects, the wiki and the protection of
main); a setting it cannot read is skipped. See the guide on the new-project bootstrap, sections 2.3 and 3.
"""
import os
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field

from github_api import Client, GitHubError

BOARD_VARIABLE = "BOARD_NUMBER"
EXPIRY_WARNING_DAYS = 14
DEFAULT_BRANCH = "main"
WIKI_SYNC_WORKFLOW = os.path.join(".github", "workflows", "wiki-sync.yml")

# The repository settings of the bootstrap guide (section 3) that the repository response carries.
EXPECTED_SETTINGS = (
    ("allow_merge_commit", True, "merge commits must be allowed"),
    ("allow_squash_merge", False, "squash merging must be off, because merge commits are the only merge method"),
    ("allow_rebase_merge", False, "rebase merging must be off, because merge commits are the only merge method"),
    ("delete_branch_on_merge", False, "head branches must not be deleted automatically: a branch is tagged first and deleted second"),
    ("has_issues", True, "issues must be enabled"),
    ("has_projects", True, "projects must be enabled"),
)

TEXT, NUMBER, DATE, SELECT = "TEXT", "NUMBER", "DATE", "SINGLE_SELECT"

# The board's fields and their values, exactly as the bootstrap guide (section 6) lists them. The preflight
# checks them, `fields.py` creates the missing ones, and a test compares this table with the guide.
REQUIRED_FIELDS = {
    "Status": (SELECT, ["ToDo", "OnDeck", "InProgress", "Review", "Completed", "Suspended", "Abandoned"]),
    "Origin": (SELECT, ["Backfilled", "Backdated"]),
    "REF": (TEXT, None),
    "Waiting": (SELECT, ["Needs input"]),
    "Attention": (SELECT, ["Fine", "Acknowledged", "Watch", "Caution", "AtRisk"]),
    "Resolution": (SELECT, ["Done", "Duplicate", "Invalid", "WontFix", "Superseded", "Obsolete"]),
    "Delivery": (SELECT, ["Committed", "Pushed", "Merged", "Implemented", "Released", "Dropped"]),
    "Priority": (SELECT, ["Critical", "Urgent", "High", "Normal", "Low", "Wishlist"]),
    "Size": (SELECT, ["XS", "S", "M", "L", "XL"]),
    "Risk": (SELECT, ["1 Very low", "2 Low", "3 Medium", "4 High", "5 Very high"]),
    "Version": (TEXT, None),
    "Build": (TEXT, None),
    "Version#": (NUMBER, None),
    "Start date": (DATE, None),
    "End date": (DATE, None),
    "Fix": (TEXT, None),
}

# The colours the guide gives to options (every other option is gray).
OPTION_COLORS = {"Fine": "GREEN", "Acknowledged": "PURPLE", "Watch": "YELLOW", "Caution": "ORANGE", "AtRisk": "RED"}

LINKED_BOARDS = ("query($o:String!,$n:String!){repository(owner:$o,name:$n){"
                 "projectsV2(first:20){nodes{id number title}}}}")
BOARD_FIELDS = ("query($id:ID!){node(id:$id){... on ProjectV2{fields(first:50){nodes{"
                "... on ProjectV2Field{id name dataType}"
                "... on ProjectV2SingleSelectField{id name dataType options{id name}}}}}}}")


@dataclass
class Check:
    name: str
    ok: bool
    message: str
    skipped: bool = False


@dataclass
class Board:
    id: str
    number: int
    title: str
    fields: dict = field(default_factory=dict)  # name -> {"id", "type", "options": {name: id}}


@dataclass
class Report:
    checks: list = field(default_factory=list)
    board: Board = None
    warnings: list = field(default_factory=list)
    repository: dict = None  # what GET /repos/{repo} returned, for the settings check
    candidate: Board = None  # the board that was identified, even when its fields are not right (fields.py needs it)

    @property
    def ok(self):
        return all(check.ok for check in self.checks)

    def add(self, name, ok, message):
        self.checks.append(Check(name, ok, message))
        return ok

    def skip(self, name, because):
        self.checks.append(Check(name, False, f"skipped: {because}", skipped=True))

    def render(self):
        lines = []
        for check in self.checks:
            mark = "skipped" if check.skipped else ("ok" if check.ok else "FAILED")
            lines.append(f"[{mark}] {check.name}: {check.message}")
        lines += [f"[warning] {warning}" for warning in self.warnings]
        lines.append("preflight: " + ("passed" if self.ok else "failed"))
        return "\n".join(lines)


def check_repository(repo_client, report, project_client=None):
    name = "repository access"
    try:
        info = repo_client.request("GET", f"/repos/{repo_client.repo}")
    except GitHubError as error:
        return report.add(name, False, f"cannot reach {repo_client.repo}: {error}")
    report.repository = info if isinstance(info, dict) else {}
    if (info.get("permissions") or {}).get("push"):
        return report.add(name, True, f"{repo_client.repo} is reachable with write access")
    # The workflow's own token does not report its rights (the workflow declares them instead),
    # but the project token belongs to an administrator and does.
    if project_client is not None and project_client.token:
        try:
            other = project_client.request("GET", f"/repos/{project_client.repo}")
        except GitHubError:
            other = {}
        if (other.get("permissions") or {}).get("push"):
            return report.add(name, True, f"{repo_client.repo} is reachable; write access is confirmed through the project "
                                          "token (the workflow token declares its own rights)")
        return report.add(name, False, "neither the workflow token nor the project token reports write access to the repository")
    return report.add(name, False, "the workflow token does not report write access and there is no project token to confirm it")


def _state(value):
    return "on" if value else "off"


def check_settings(report, wiki_sync=False):
    """Warn about a repository setting that differs from the bootstrap guide (section 3).

    It reads the repository the access check already fetched. A setting the response does not carry
    is skipped without a warning, and a mismatch is only ever a warning: the check fails open.
    """
    info = report.repository or {}
    for key, wanted, why in EXPECTED_SETTINGS:
        if key in info and bool(info[key]) != wanted:
            report.warnings.append(f"repository setting {key} is {_state(info[key])}: {why} (bootstrap guide, section 3)")
    if info.get("default_branch") not in (None, DEFAULT_BRANCH):
        report.warnings.append(f"the default branch is {info['default_branch']}, not {DEFAULT_BRANCH} (bootstrap guide, section 3)")
    if wiki_sync and info.get("has_wiki") is False:
        report.warnings.append("repository setting has_wiki is off, but the repository has the wiki-sync workflow: "
                               "the wiki must be enabled and initialized (bootstrap guide, section 3)")


def check_protection(report, project_client):
    """Warn about the protection of main, read through the project token (an administrator's).

    Protection is a recommendation where the plan offers it. A refusal other than "not protected" (no
    permission, or a plan without protection) is skipped without a warning.
    """
    if project_client is None or not project_client.token:
        return
    try:
        rules = project_client.request("GET", f"/repos/{project_client.repo}/branches/{DEFAULT_BRANCH}/protection")
    except GitHubError as error:
        if error.status == 404:
            report.warnings.append(f"the branch {DEFAULT_BRANCH} has no protection: the guide recommends requiring a pull request "
                                   "and an up-to-date branch where the plan offers it (bootstrap guide, section 3)")
        return
    if not isinstance(rules, dict) or "required_pull_request_reviews" not in rules and "required_status_checks" not in rules \
            and "enforce_admins" not in rules:
        return
    if "required_pull_request_reviews" not in rules:
        report.warnings.append(f"the protection of {DEFAULT_BRANCH} does not require a pull request (bootstrap guide, section 3)")
    if not (rules.get("required_status_checks") or {}).get("strict"):
        report.warnings.append(f"the protection of {DEFAULT_BRANCH} does not require the branch to be up to date (bootstrap guide, section 3)")
    if (rules.get("enforce_admins") or {}).get("enabled"):
        report.warnings.append(f"the protection of {DEFAULT_BRANCH} applies to administrators too: the guides leave the "
                               "administrator bypass open (bootstrap guide, section 3)")


def check_token(project_client, report):
    name = "project token"
    if not project_client.token:
        return report.add(name, False, "PROJECT_TOKEN is not set (see the bootstrap guide, section 4)")
    try:
        login = project_client.graphql("{viewer{login}}")["viewer"]["login"]
    except GitHubError as error:
        return report.add(name, False, f"PROJECT_TOKEN does not work: {error}")
    message = f"works, acting as {login}"
    expiry = getattr(project_client, "token_expiry", lambda: None)()
    if expiry is None:
        report.warnings.append("PROJECT_TOKEN has no expiry date: the guide recommends one, so a leaked token cannot be used forever")
    else:
        days = (expiry - datetime.now(timezone.utc)).days
        message += f"; expires {expiry:%Y-%m-%d}"
        if days <= EXPIRY_WARNING_DAYS:
            report.warnings.append(f"PROJECT_TOKEN expires in {max(days, 0)} day(s), on {expiry:%Y-%m-%d}: renew it before then "
                                   "(see the bootstrap guide, section 4)")
    return report.add(name, True, message)


def find_board(project_client, report, store=True):
    """Identify the board linked to the repository and keep its number in a repository variable."""
    name = "board"
    owner, repo_name = project_client.repo.split("/", 1)
    try:
        nodes = project_client.graphql(LINKED_BOARDS, {"o": owner, "n": repo_name})["repository"]["projectsV2"]["nodes"]
        chosen = project_client.get_variable(BOARD_VARIABLE)
    except GitHubError as error:
        report.add(name, False, f"cannot list the boards linked to the repository: {error}")
        return None
    if not nodes:
        report.add(name, False, "the repository has no linked board; link one to the repository")
        return None
    if len(nodes) > 1:
        match = [n for n in nodes if str(n["number"]) == chosen]
        if not match:
            listing = ", ".join(f"#{n['number']} {n['title']}" for n in nodes)
            report.add(name, False, f"the repository has {len(nodes)} linked boards ({listing}); "
                       f"the administrator must set the repository variable {BOARD_VARIABLE} to the one to use")
            return None
        nodes = match
    node = nodes[0]
    if store and chosen != str(node["number"]):
        try:
            project_client.set_variable(BOARD_VARIABLE, str(node["number"]))
        except GitHubError as error:
            report.add(name, False, f"found board #{node['number']} but could not store {BOARD_VARIABLE}: {error}")
            return None
    report.add(name, True, f"board #{node['number']} \"{node['title']}\" ({BOARD_VARIABLE} = {node['number']})")
    return Board(node["id"], node["number"], node["title"])


def check_fields(project_client, board, report):
    name = "board fields"
    try:
        nodes = project_client.graphql(BOARD_FIELDS, {"id": board.id})["node"]["fields"]["nodes"]
    except GitHubError as error:
        return report.add(name, False, f"cannot read the board's fields: {error}")
    for node in nodes:
        if node:
            options = {o["name"]: o["id"] for o in node.get("options", [])}
            board.fields[node["name"]] = {"id": node["id"], "type": node["dataType"], "options": options}
    problems = []
    for field_name, (kind, values) in REQUIRED_FIELDS.items():
        found = board.fields.get(field_name)
        if found is None:
            problems.append(f"missing field {field_name}")
        elif found["type"] != kind:
            problems.append(f"field {field_name} is {found['type']}, expected {kind}")
        elif values:
            absent = [v for v in values if v not in found["options"]]
            if absent:
                problems.append(f"field {field_name} lacks the values {', '.join(absent)}")
    if problems:
        return report.add(name, False, "; ".join(problems))
    return report.add(name, True, f"all {len(REQUIRED_FIELDS)} fields and their values are present")


def run(repo_client, project_client, store=True, root=None):
    """Run every check in order and return the report. Dependent checks are skipped on failure."""
    report = Report()
    check_repository(repo_client, report, project_client)
    root = root if root is not None else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    check_settings(report, wiki_sync=os.path.exists(os.path.join(root, WIKI_SYNC_WORKFLOW)))
    check_protection(report, project_client)
    if check_token(project_client, report):
        board = find_board(project_client, report, store)
        report.candidate = board
        if board and check_fields(project_client, board, report):
            report.board = board
        elif not board:
            report.skip("board fields", "no board was identified")
    else:
        report.skip("board", "the project token does not work")
        report.skip("board fields", "no board was identified")
    return report


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    store = "--no-store" not in (argv if argv is not None else sys.argv[1:])
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("GITHUB_REPOSITORY is not set")
        return 1
    repo_client = Client(os.environ.get("GITHUB_TOKEN", ""), repo)
    project_client = Client(os.environ.get("PROJECT_TOKEN", ""), repo)
    report = run(repo_client, project_client, store)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
