"""The board views: create, recreate and remove saved views from a definition file.

GitHub lets a view's name, layout, filter and visible fields be changed later, but its grouping, board
rows and columns and sorting can only be set when the view is created. So a view that differs from the
definition is created again and the old one deleted, and this keeps the views the same in every project.
GitHub never deletes the last view of a board, so the new view is created before the old one is deleted.

The definition file (`.github/views.json`) lists the views in the order of their tabs. Each entry has a
`name`, a `layout` (`table`, `board` or `roadmap`) and optionally a `filter`, `group_by` (a field name),
`vertical_group_by` (the board columns), `sort_by` (a list of [field name, "asc" or "desc"]) and
`visible_fields` (field names). Every filter automatically ends with ` AND is:issue AND -label:dummy`, so
pull requests (which are on the board only to fill the gaps in the numbers of the All view) and test tickets
(see the ticket fields reference) never show in a view, unless the entry has `"include_pull_requests": true`
and `"include_test_tickets": true` (the view that lists everything). A sort by Created, Updated or Closed can be written in `sort_by`, but the
API cannot set it when a view is created, so the script leaves it out, does not compare it, and says to set
it by hand in the web interface. An entry may also list `manual_steps`: settings the API cannot reach (for
example turning off "Show hierarchy"), which the script prints as a reminder whenever it creates the view.

    python .github/scripts/views.py                         report what would change (a dry run)
    python .github/scripts/views.py --apply                 do it
    python .github/scripts/views.py --only NAME             limit it to one view of the file
    python .github/scripts/views.py --delete-unlisted       also delete the views that are not in the file
    python .github/scripts/views.py --delete NAME           delete the view with that name (and no other)
    python .github/scripts/views.py --show                  print the board's views in the file's format
    python .github/scripts/views.py --definition PATH       use another definition file

The token needs the project scope (`PROJECT_TOKEN`). Board settings are the administrator's: run it only
when the administrator asks.
"""
import json
import os
import sys

import finalize
import preflight
from github_api import Client, GitHubError

DEFINITION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "views.json")
LAYOUTS = {"table": "TABLE_LAYOUT", "board": "BOARD_LAYOUT", "roadmap": "ROADMAP_LAYOUT"}
KEYS = {"name", "layout", "filter", "group_by", "vertical_group_by", "sort_by", "visible_fields", "include_test_tickets", "include_pull_requests", "manual_steps"}
TEST_TICKETS = "-label:dummy"
ISSUES_ONLY = "is:issue"
UNREADABLE = ("Type",)  # GraphQL does not report this field among a view's visible fields, so it is not compared
MANUAL_SORT = ("Created", "Updated", "Closed")  # the API rejects these as a sort field when a view is created


class ViewsError(RuntimeError):
    pass


def effective_filter(text, include_test_tickets=False, include_pull_requests=False):
    """The filter a view really gets: the written one, then `is:issue` (pull requests are on the board only so that
    the All view has no gaps in the numbers) and the exclusion of the test tickets, unless they are wanted."""
    text = (text or "").strip()
    added = ([] if include_pull_requests else [ISSUES_ONLY]) + ([] if include_test_tickets else [TEST_TICKETS])
    if not added:
        return text
    if text and " OR " in text and not (text.startswith("(") and text.endswith(")")):
        text = f"({text})"
    return " AND ".join(([text] if text else []) + added)


def load_definition(path=DEFINITION):
    """The list of view entries in the file, checked. Raises ViewsError for anything that is not valid."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise ViewsError(f"cannot read the definition file {path}: {error}")
    views = data.get("views") if isinstance(data, dict) else None
    if not isinstance(views, list):
        raise ViewsError("the definition file must hold an object with a list named `views`")
    names = set()
    for entry in views:
        label = entry.get("name") if isinstance(entry, dict) else None
        if not isinstance(label, str) or not label.strip():
            raise ViewsError("every view needs a name")
        if label in names:
            raise ViewsError(f"the view name {label!r} is used twice")
        names.add(label)
        extra = set(entry) - KEYS
        if extra:
            raise ViewsError(f"{label}: unknown key(s) {', '.join(sorted(extra))}")
        if entry.get("layout") not in LAYOUTS:
            raise ViewsError(f"{label}: the layout must be one of {', '.join(LAYOUTS)}")
        for flag in ("include_test_tickets", "include_pull_requests"):
            if flag in entry and not isinstance(entry[flag], bool):
                raise ViewsError(f"{label}: {flag} must be true or false")
        steps = entry.get("manual_steps", [])
        if not (isinstance(steps, list) and all(isinstance(step, str) and step.strip() for step in steps)):
            raise ViewsError(f"{label}: manual_steps must be a list of sentences")
        for key in ("group_by", "vertical_group_by"):
            if entry.get(key) is not None and not isinstance(entry[key], str):
                raise ViewsError(f"{label}: {key} must be one field name")
        for sort in entry.get("sort_by", []):
            if not (isinstance(sort, list) and len(sort) == 2 and isinstance(sort[0], str) and sort[1] in ("asc", "desc")):
                raise ViewsError(f"{label}: each sort_by item must be [field name, \"asc\" or \"desc\"]")
        fields = entry.get("visible_fields")
        if fields is not None:
            if not (isinstance(fields, list) and all(isinstance(f, str) for f in fields)):
                raise ViewsError(f"{label}: visible_fields must be a list of field names")
            if entry["layout"] == "roadmap":
                raise ViewsError(f"{label}: a roadmap has no visible_fields")
        if entry.get("vertical_group_by") and entry["layout"] != "board":
            raise ViewsError(f"{label}: vertical_group_by is only for a board")
    return views


def desired_state(entry):
    """The entry in the form that a board view is read back in, with the automatic filter added."""
    state = {"name": entry["name"], "layout": entry["layout"],
             "filter": effective_filter(entry.get("filter"), entry.get("include_test_tickets", False), entry.get("include_pull_requests", False)),
             "group_by": entry.get("group_by"), "vertical_group_by": entry.get("vertical_group_by"),
             "sort_by": [list(sort) for sort in entry.get("sort_by", [])]}
    if entry.get("visible_fields") is not None:
        state["visible_fields"] = sorted(entry["visible_fields"])
    return state


def current_state(node):
    """A view read from the board, in the same form."""
    layout = {value: key for key, value in LAYOUTS.items()}.get(node.get("layout"), node.get("layout"))
    names = lambda key: [item["name"] for item in (node.get(key) or {}).get("nodes", []) if item and item.get("name")]
    group, vertical = names("groupByFields"), names("verticalGroupByFields")
    return {"id": node["id"], "number": node.get("number"), "name": node["name"], "layout": layout,
            "filter": (node.get("filter") or "").strip(), "group_by": group[0] if group else None,
            "vertical_group_by": vertical[0] if vertical else None,
            "sort_by": [[item["field"]["name"], item["direction"].lower()] for item in (node.get("sortByFields") or {}).get("nodes", [])
                        if item and item.get("field")],
            "visible_fields": sorted(names("visibleFields"))}


def differences(wanted, current):
    """The keys in which the view on the board differs from the definition."""
    keys = ["layout", "filter", "group_by", "vertical_group_by", "sort_by"]
    if "visible_fields" in wanted and wanted["layout"] != "roadmap":
        keys.append("visible_fields")
    return [key for key in keys if _comparable(key, wanted) != _comparable(key, current)]


def _comparable(key, state):
    if key == "visible_fields":
        return [name for name in state[key] if name not in UNREADABLE]
    if key == "sort_by":
        return [sort for sort in state[key] if sort[0] not in MANUAL_SORT]  # these can only be set by hand
    return state[key]


def manual_sorts(entry):
    """The sorts of the entry that the API cannot set (Created, Updated, Closed): they are set by hand."""
    return [f"{name} {direction}" for name, direction in entry.get("sort_by", []) if name in MANUAL_SORT]


def request_body(entry, ids):
    """The body of the REST call that creates the view; field names become the board's numeric field ids."""
    unknown = []

    def one(name):
        if name not in ids:
            unknown.append(name)
        return ids.get(name)

    body = {"name": entry["name"], "layout": entry["layout"],
            "filter": effective_filter(entry.get("filter"), entry.get("include_test_tickets", False), entry.get("include_pull_requests", False))}
    if entry.get("visible_fields") is not None:
        body["visible_fields"] = [one(name) for name in entry["visible_fields"]]
    sorts = [[name, direction] for name, direction in entry.get("sort_by", []) if name not in MANUAL_SORT]
    if sorts:
        body["sort_by"] = [[one(name), direction] for name, direction in sorts]
    if entry.get("group_by"):
        body["group_by"] = [one(entry["group_by"])]
    if entry.get("vertical_group_by"):
        body["vertical_group_by"] = [one(entry["vertical_group_by"])]
    if unknown:
        raise ViewsError(f"{entry['name']}: unknown field(s) {', '.join(sorted(set(unknown)))} "
                         f"(the board has: {', '.join(sorted(ids))})")
    return body


def sync(project_client, board, definition, only=None, delete_unlisted=False, dry_run=True):
    """Bring the board's views in line with the definition. Returns the Runner (its log says what was or would be done)."""
    run = finalize.Runner(dry_run)
    names = [entry["name"] for entry in definition]
    if only is not None and only not in names:
        raise ViewsError(f"there is no view named {only!r} in the definition file")
    ids = project_client.view_field_ids(board.id, board.number)
    current = [current_state(node) for node in project_client.project_views(board.id)]
    by_name = {}
    for view in current:
        by_name.setdefault(view["name"], []).append(view)
    if delete_unlisted and only is None and not definition and current:
        raise ViewsError("GitHub never deletes the last view of a board: with an empty definition, --delete-unlisted would try to "
                         "delete them all. Add a view to the definition, or delete the others by name with --delete NAME and keep one")
    chosen = [entry for entry in definition if only is None or entry["name"] == only]
    bodies = {entry["name"]: request_body(entry, ids) for entry in chosen}  # every field name is checked before anything is changed
    # Create or recreate: once one view changes, the ones listed after it are recreated too, so the tabs keep the file's order.
    cascade = False
    for entry in chosen:
        body = bodies[entry["name"]]
        wanted = desired_state(entry)
        existing = by_name.get(entry["name"], [])
        changed = differences(wanted, existing[0]) if existing else ["missing"]
        if len(existing) > 1:
            changed.append("duplicate")
        if not changed and not (cascade and only is None):
            run.log.append(f"view {entry['name']}: up to date")
            continue
        changed = changed or ["recreated to keep the order of the tabs"]
        cascade = True
        # The new view is created first and the old one deleted after it: GitHub refuses to delete the last view of a board.
        run.do(f"view {entry['name']}: create the {entry['layout']} view with filter `{body['filter']}`", project_client.create_view, board.number, body)
        for sort in manual_sorts(entry):
            run.log.append(f"view {entry['name']}: set the sort by {sort} by hand in the web interface (the API cannot)")
        for step in entry.get("manual_steps", []):
            run.log.append(f"view {entry['name']}: by hand in the web interface (the API cannot): {step}")
        for view in existing:
            run.do(f"view {entry['name']}: delete the old view #{view['number']} ({', '.join(changed)})", project_client.delete_view, view["id"])
    if only is None:
        for view in current:
            if view["name"] in names:
                continue
            if delete_unlisted:
                run.do(f"view {view['name']}: delete view #{view['number']} (not in the definition file)", project_client.delete_view, view["id"])
            else:
                run.log.append(f"view {view['name']}: not in the definition file (kept; use --delete-unlisted to delete it)")
    return run


def delete_named(project_client, board, name, dry_run=True):
    """Delete the view(s) with this name and no other. Returns the Runner; raises ViewsError if there is none."""
    run = finalize.Runner(dry_run)
    every = project_client.project_views(board.id)
    found = [current_state(node) for node in every if node["name"] == name]
    if not found:
        raise ViewsError(f"there is no view named {name!r} on the board")
    if len(found) == len(every):
        raise ViewsError(f"{name!r} is the last view of the board, and GitHub never deletes the last view: create another one first")
    for view in found:
        run.do(f"view {name}: delete view #{view['number']}", project_client.delete_view, view["id"])
    return run


def by_hand(definition):
    """The lines that remind of what the API cannot set (sorts by a date, and each entry's `manual_steps`)."""
    lines = []
    for entry in definition:
        for sort in manual_sorts(entry):
            lines.append(f"  {entry['name']}: set the sort to {sort}")
        lines += [f"  {entry['name']}: {step}" for step in entry.get("manual_steps", [])]
    return ["Settings to make or check by hand in the web interface (the API cannot, and recreating a view loses them):"] + lines if lines else []


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = list(argv if argv is not None else sys.argv[1:])
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("GITHUB_REPOSITORY is not set")
        return 1

    def option(name):
        return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None

    project_client = Client(os.environ.get("PROJECT_TOKEN", ""), repo)
    repo_client = Client(os.environ.get("GITHUB_TOKEN") or os.environ.get("PROJECT_TOKEN", ""), repo)
    report = preflight.run(repo_client, project_client, store=False)
    print(report.render())
    if report.board is None:
        print("views: no board was identified, nothing to do")
        return 1
    try:
        if "--show" in args:
            nodes = project_client.project_views(report.board.id)
            print(json.dumps({"views": [{k: v for k, v in current_state(n).items() if k not in ("id", "number")} for n in nodes]},
                             indent=2, ensure_ascii=False))
            return 0
        if "--delete" in args:
            run = delete_named(project_client, report.board, option("--delete") or "", "--apply" not in args)
        else:
            definition = load_definition(option("--definition") or DEFINITION)
            run = sync(project_client, report.board, definition, option("--only"), "--delete-unlisted" in args, "--apply" not in args)
    except (ViewsError, GitHubError) as error:
        print(f"views refused: {error}")
        return 1
    prefix = "would: " if run.dry_run else "did: "
    for line in run.log:
        print(line if line.endswith("up to date") or "(kept" in line or "by hand" in line else prefix + line)
    for line in by_hand(definition):
        print(line)
    if run.dry_run:
        print("dry run: nothing was changed; add --apply to do it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
