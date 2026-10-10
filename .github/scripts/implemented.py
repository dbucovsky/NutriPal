"""Attach the tickets with Delivery "Implemented" to their Version tickets.

A ticket that changed no file has nothing in the changelog for the finalize step to find. A person
sets its Delivery to Implemented, with the Version it belongs to. At every finalize, at every scheduled
run and on a manual run, this sweep looks at the Implemented tickets that are not yet sub-issues of any
Version ticket:

- a blank Version gets the version being finalized (at a scheduled run, the latest finalized version);
- a Version that is already finalized is kept, and the ticket is attached to that version's ticket;
- a Version that is not finalized yet makes the ticket wait, quietly while a higher version is not finalized
  either; but when a higher version is already finalized, the aimed number was passed and can no longer
  happen, so the ticket would wait for ever: it gets Attention Caution and one comment, and a person decides
  (it is never moved by itself).

The ticket keeps Delivery Implemented and gets no Build. A comment on each Version ticket says which
tickets were added, because its description is written once. See the guide on project structure
(section 5.2) and appendix C.
"""
import condition_comments
import failures
from versions import Version

ITEMS = ("query($id:ID!,$after:String){node(id:$id){... on ProjectV2{items(first:100,after:$after){"
         "pageInfo{hasNextPage endCursor} nodes{id content{... on Issue{number title parent{number} comments(last:30){nodes{body}}}} "
         "attention:fieldValueByName(name:\"Attention\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "delivery:fieldValueByName(name:\"Delivery\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "status:fieldValueByName(name:\"Status\"){... on ProjectV2ItemFieldSingleSelectValue{name}} "
         "version:fieldValueByName(name:\"Version\"){... on ProjectV2ItemFieldTextValue{text}} "
         "number:fieldValueByName(name:\"Version#\"){... on ProjectV2ItemFieldNumberValue{number}}}}}}}")


def unattached(project_client, board):
    """The Implemented tickets on the board that are not sub-issues of any ticket (an Abandoned ticket never shipped)."""
    found, after = [], None
    while True:
        page = project_client.graphql(ITEMS, {"id": board.id, "after": after})["node"]["items"]
        for node in page["nodes"]:
            content = node.get("content") or {}
            delivery = (node.get("delivery") or {}).get("name")
            status = (node.get("status") or {}).get("name")
            if delivery == "Implemented" and content.get("number") and not content.get("parent") and status != "Abandoned":
                found.append({"item": node["id"], "number": content["number"], "title": content["title"],
                              "attention": (node.get("attention") or {}).get("name"),
                              "comments": [c.get("body") or "" for c in (content.get("comments") or {}).get("nodes") or []],
                              "version": (node.get("version") or {}).get("text") or "",
                              "version_number": (node.get("number") or {}).get("number")})
        if not page["pageInfo"]["hasNextPage"]:
            return found
        after = page["pageInfo"]["endCursor"]


def version_ticket(repo_client, version):
    """The Version ticket titled exactly `Version X.Y.Z`, closed (finalized) or not, or None."""
    title = f"Version {str(version)[1:]}"
    for page in range(1, 11):
        issues = repo_client.request("GET", repo_client.repo_path(f"/issues?state=all&type=Version&per_page=100&page={page}"))
        for issue in issues:
            if issue["title"] == title:
                return issue
        if len(issues) < 100:
            return None
    return None


def flag_passed(run, repo_client, project_client, board, ticket, aimed, latest):
    """Raise Caution, once, on an Implemented ticket aimed at a version that was passed (it will never be finalized)."""
    number, marker = ticket["number"], f"<!-- attention:caution passed={aimed} -->"
    if ticket["attention"] in ("Caution", "AtRisk"):
        run.log.append(f"#{number}: waits for {aimed}, which was passed ({latest} is finalized); an Attention flag is already open")
        return
    if any(marker in body for body in ticket["comments"]):
        run.log.append(f"#{number}: waits for {aimed}, which was passed ({latest} is finalized); already flagged")
        return
    field = board.fields["Attention"]
    run.do(f"#{number}: waits for {aimed}, which was passed ({latest} is finalized): set Attention to Caution", project_client.set_project_field,
           board.id, ticket["item"], field["id"], {"singleSelectOptionId": field["options"]["Caution"]})
    run.do(f"#{number}: comment on the passed version", repo_client.comment, number,
           condition_comments.decorate(
               f"{marker}\nAttention: Caution. This ticket is Implemented and aimed at {aimed}, but {latest} is already finalized and {aimed} was "
               f"never released, so it can no longer happen and the ticket would wait for ever. Set its Version to the version it belongs to "
               f"(for example {latest}), or clear the Version: a blank Version gets the latest finalized version. The next scheduled run then "
               "attaches it to that version's ticket. Then tick a box below.", "passed-version"))


def sweep(run, repo_client, project_client, board, finalized, current, now):
    """Attach the waiting Implemented tickets. `finalized` is the set of finalized Versions and
    `current` is (the version being finalized, the number of its Version ticket)."""
    current_version, current_ticket = current
    added = {}  # version -> (Version ticket number, [(ticket number, title)])
    for ticket in unattached(project_client, board):
        try:
            aimed = Version.parse(ticket["version"]) if ticket["version"] else current_version
        except ValueError:
            run.log.append(f"#{ticket['number']}: Version {ticket['version']!r} is not a version; left alone")
            continue
        if aimed not in finalized:
            latest = max(finalized, key=lambda v: v.number(), default=None)
            if latest is not None and latest.number() > aimed.number():
                flag_passed(run, repo_client, project_client, board, ticket, aimed, latest)
            else:
                run.log.append(f"#{ticket['number']}: waits for {aimed}, which is not finalized yet")
            continue
        if aimed == current_version:
            parent = current_ticket
        else:
            found = version_ticket(repo_client, aimed)
            if found is None or found["state"] != "closed":
                run.log.append(f"#{ticket['number']}: no finalized Version ticket for {aimed}; left alone")
                continue
            parent = found["number"]
        run.do(f"#{ticket['number']}: attach to the Version ticket #{parent} ({aimed})", repo_client.add_sub_issue, parent, ticket["number"])
        fields = board.fields
        if not ticket["version"]:
            run.do(f"#{ticket['number']}: set Version to {aimed}", project_client.set_project_field, board.id, ticket["item"],
                   fields["Version"]["id"], {"text": str(aimed)})
        if ticket["version_number"] != float(aimed.number()):
            run.do(f"#{ticket['number']}: set Version# to {aimed.number()}", project_client.set_project_field, board.id,
                   ticket["item"], fields["Version#"]["id"], {"number": float(aimed.number())})
        added.setdefault(aimed, (parent, []))[1].append((ticket["number"], ticket["title"]))
    when = now.strftime("%Y-%m-%d %H:%M")
    for aimed, (parent, tickets) in added.items():
        listing = "; ".join(f"#{number} {title}" for number, title in tickets)
        run.do(f"Version ticket #{parent}: comment on the Implemented tickets added",
               repo_client.comment, parent, f"Added by the automation on {when} UTC (Delivery Implemented, no file change): {listing}.")
    return added


def scheduled_sweep(root, repo_client, project_client, board, now, dry_run=False):
    """The scheduled run: attach waiting Implemented tickets without touching the changelog or main.

    The tickets are judged against the finalized versions in the changelog, and a blank Version gets the
    latest one, which is the version the work shipped with.
    """
    import changelog
    import finalize
    run = finalize.Runner(dry_run)
    with open(root + "/CHANGELOG.md", encoding="utf-8") as handle:
        finals = [s for s in changelog.parse(handle.read()) if s.kind == "final"]
    if not finals:
        run.log.append("no finalized version yet: nothing to attach to")
        return run
    latest = finals[0].version
    found = version_ticket(repo_client, latest)
    if found is None:
        run.log.append(f"no Version ticket for {latest}: nothing attached")
        return run
    sweep(run, repo_client, project_client, board, {s.version for s in finals}, (latest, found["number"]), now)
    return run


def main(argv=None):
    import os
    import sys
    import preflight
    import versions
    from github_api import Client, GitHubError
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
    if report.board is None:
        print("Implemented sweep skipped: no board (the preflight did not identify one)")
        return 0
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    try:
        run = scheduled_sweep(root, repo_client, project_client, report.board, versions.utc_now(), "--dry-run" in args)
    except GitHubError as error:
        print(f"Implemented sweep stopped: {error}")
        failures.record(f"Implemented sweep stopped: {error}")
        return 0
    for line in run.log or ["no Implemented tickets waiting"]:
        print(("would: " if run.dry_run else "did: ") + line)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
