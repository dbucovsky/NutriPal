import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import preflight  # noqa: E402
import views  # noqa: E402
from github_api import Client  # noqa: E402

IDS = {"Title": 1, "Status": 2, "Priority": 3, "Version": 4, "Version#": 5, "Updated": 6, "Type": 7}


def node(number, name, layout="TABLE_LAYOUT", filter="is:issue AND -label:dummy", group=None, vertical=None, sort=(), fields=("Title",)):
    return {"id": f"V{number}", "number": number, "name": name, "layout": layout, "filter": filter,
            "groupByFields": {"nodes": [{"name": group}] if group else []},
            "verticalGroupByFields": {"nodes": [{"name": vertical}] if vertical else []},
            "sortByFields": {"nodes": [{"field": {"name": n}, "direction": d} for n, d in sort]},
            "visibleFields": {"nodes": [{"name": f} for f in fields]}}


class FakeProject:
    repo = "owner/repo"

    def __init__(self, nodes=()):
        self.nodes, self.calls = list(nodes), []

    def view_field_ids(self, project_id, number):
        return dict(IDS)

    def project_views(self, project_id):
        return self.nodes

    def create_view(self, number, body):
        self.calls.append(("create", number, body))

    def delete_view(self, view_id):
        self.calls.append(("delete", view_id))


BOARD = preflight.Board("P7", 7, "Governance", {})

ALL = {"name": "All", "layout": "table", "sort_by": [["Version#", "desc"]], "visible_fields": ["Title", "Status"]}
BACKLOG = {"name": "Backlog", "layout": "board", "filter": "status:ToDo,OnDeck", "vertical_group_by": "Status",
           "sort_by": [["Priority", "asc"]]}
BOARD_VIEW = {"name": "Board", "layout": "board", "filter": "is:open", "vertical_group_by": "Status", "group_by": "Version"}


def stored(entry):
    """The node the board would hold after the entry was created."""
    layout = {"table": "TABLE_LAYOUT", "board": "BOARD_LAYOUT", "roadmap": "ROADMAP_LAYOUT"}[entry["layout"]]
    return node(10, entry["name"], layout, views.effective_filter(entry.get("filter")), entry.get("group_by"),
                entry.get("vertical_group_by"), [(n, d.upper()) for n, d in entry.get("sort_by", [])],
                entry.get("visible_fields", ["Title"]))


class FilterTests(unittest.TestCase):
    def test_a_blank_filter_only_leaves_out_the_test_tickets(self):
        self.assertEqual(views.effective_filter(""), "is:issue AND -label:dummy")
        self.assertEqual(views.effective_filter(None), "is:issue AND -label:dummy")

    def test_the_test_tickets_are_left_out_of_every_filter(self):
        self.assertEqual(views.effective_filter("is:open"), "is:open AND is:issue AND -label:dummy")

    def test_a_filter_with_or_is_put_in_parentheses(self):
        self.assertEqual(views.effective_filter("a:1 OR b:2"), "(a:1 OR b:2) AND is:issue AND -label:dummy")
        self.assertEqual(views.effective_filter("(a:1 OR b:2)"), "(a:1 OR b:2) AND is:issue AND -label:dummy")


class ConditionViewsTests(unittest.TestCase):
    """The real definition file: one view for each nature of condition (Decide, Follow up, Fix), and no Health."""

    def entries(self):
        return views.load_definition(os.path.join(ROOT, ".github", "views.json"))

    def view(self, name):
        return next(entry for entry in self.entries() if entry["name"] == name)

    def test_the_views_are_these_seven_in_this_order(self):
        self.assertEqual([entry["name"] for entry in self.entries()],
                         ["All", "Backlog", "Board", "Decide", "Follow up", "Fix", "Versions"])

    def test_decide_lists_the_open_attention_flags_and_the_open_alerts(self):
        self.assertEqual(self.view("Decide")["filter"], "attention:Watch,Caution,AtRisk OR (type:Alert AND is:open)")

    def test_follow_up_lists_what_waits_for_an_answer_or_a_verification(self):
        self.assertEqual(self.view("Follow up")["filter"], "has:waiting OR status:Review")

    def test_fix_lists_the_tickets_the_refresh_found_broken_and_nothing_else(self):
        self.assertEqual(self.view("Fix")["filter"], "has:fix")

    def test_fix_shows_the_rules_first_and_the_version_next_to_the_delivery(self):
        fields = self.view("Fix")["visible_fields"]
        self.assertEqual(fields[:3], ["Title", "Assignees", "Fix"])
        self.assertEqual(fields[fields.index("Delivery") + 1], "Version")

    def test_every_field_a_view_shows_is_a_field_of_the_board_or_a_built_in_one(self):
        known = set(preflight.REQUIRED_FIELDS) | {"Title", "Assignees", "Type", "Labels", "Parent issue", "Sub-issues progress",
                                                  "Created", "Updated", "Closed", "Repository", "Milestone", "Reviewers"}
        for entry in self.entries():
            for name in entry.get("visible_fields", []):
                self.assertIn(name, known, f"{entry['name']}: {name}")


class FilterLengthTests(unittest.TestCase):
    """GitHub refuses a view filter longer than 512 characters (a 422, found when the old Health view grew), and the
    script adds its own suffix to what the file says. The views hold one short clause each, so a new condition never
    reaches the limit."""

    MAXIMUM = 512

    def test_no_view_gets_a_filter_longer_than_github_accepts(self):
        entries = views.load_definition(os.path.join(ROOT, ".github", "views.json"))
        self.assertGreaterEqual(len(entries), 5)
        for entry in entries:
            really = views.effective_filter(entry.get("filter"), bool(entry.get("include_test_tickets")),
                                            bool(entry.get("include_pull_requests")))
            self.assertLessEqual(len(really), self.MAXIMUM, f"{entry['name']}: {len(really)} characters")

    def test_every_view_keeps_room_to_grow(self):
        entries = views.load_definition(os.path.join(ROOT, ".github", "views.json"))
        for entry in entries:
            really = views.effective_filter(entry.get("filter"), bool(entry.get("include_test_tickets")),
                                            bool(entry.get("include_pull_requests")))
            self.assertLessEqual(len(really), self.MAXIMUM - 100, f"{entry['name']}: {len(really)} characters")


class DefinitionTests(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "views.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            return views.load_definition(path)

    def refused(self, data, text):
        with self.assertRaises(views.ViewsError) as caught:
            self.load(data)
        self.assertIn(text, str(caught.exception))

    def test_the_project_definition_is_valid(self):
        self.assertIsInstance(views.load_definition(), list)

    def test_a_valid_definition_is_returned_in_order(self):
        self.assertEqual([v["name"] for v in self.load({"views": [ALL, BACKLOG]})], ["All", "Backlog"])

    def test_refusals(self):
        self.refused([], "an object with a list")
        self.refused({"views": [{"layout": "table"}]}, "needs a name")
        self.refused({"views": [ALL, ALL]}, "used twice")
        self.refused({"views": [{"name": "X", "layout": "grid"}]}, "layout must be one of")
        self.refused({"views": [{"name": "X", "layout": "table", "color": "red"}]}, "unknown key")
        self.refused({"views": [{"name": "X", "layout": "table", "sort_by": [["Priority", "up"]]}]}, "sort_by")
        self.refused({"views": [{"name": "X", "layout": "roadmap", "visible_fields": ["Title"]}]}, "no visible_fields")
        self.refused({"views": [{"name": "X", "layout": "table", "vertical_group_by": "Status"}]}, "only for a board")
        self.refused({"views": [{"name": "X", "layout": "table", "group_by": ["Status"]}]}, "one field name")
        self.refused({"views": [{"name": "X", "layout": "table", "include_test_tickets": "yes"}]}, "true or false")
        self.refused({"views": [{"name": "X", "layout": "table", "include_pull_requests": 1}]}, "true or false")
        self.refused({"views": [{"name": "X", "layout": "table", "manual_steps": "do it"}]}, "manual_steps")
        self.refused({"views": [{"name": "X", "layout": "table", "manual_steps": [""]}]}, "manual_steps")

    def test_a_missing_file_is_refused(self):
        with self.assertRaises(views.ViewsError):
            views.load_definition(os.path.join(ROOT, "no-such-file.json"))


class BodyTests(unittest.TestCase):
    def test_field_names_become_numeric_ids(self):
        body = views.request_body(BOARD_VIEW, IDS)
        self.assertEqual(body, {"name": "Board", "layout": "board", "filter": "is:open AND is:issue AND -label:dummy",
                                "group_by": [4], "vertical_group_by": [2]})

    def test_sort_and_visible_fields(self):
        body = views.request_body(ALL, IDS)
        self.assertEqual(body["sort_by"], [[5, "desc"]])
        self.assertEqual(body["visible_fields"], [1, 2])
        self.assertEqual(body["filter"], "is:issue AND -label:dummy")

    def test_an_unknown_field_is_named_and_the_known_ones_listed(self):
        with self.assertRaises(views.ViewsError) as caught:
            views.request_body({"name": "X", "layout": "table", "group_by": "Colour"}, IDS)
        self.assertIn("unknown field(s) Colour", str(caught.exception))
        self.assertIn("Priority", str(caught.exception))


    def test_a_sort_the_api_cannot_set_is_left_out_of_the_request(self):
        entry = {"name": "X", "layout": "table", "sort_by": [["Created", "asc"], ["Priority", "asc"]]}
        self.assertEqual(views.request_body(entry, dict(IDS, Created=9))["sort_by"], [[3, "asc"]])
        self.assertEqual(views.manual_sorts(entry), ["Created asc"])
        self.assertEqual(views.request_body({"name": "X", "layout": "table", "sort_by": [["Created", "asc"]]}, IDS).get("sort_by"), None)

    def test_the_test_tickets_are_kept_only_when_the_entry_asks_for_them(self):
        entry = {"name": "X", "layout": "table", "include_test_tickets": True}
        self.assertEqual(views.request_body(entry, IDS)["filter"], "is:issue")
        self.assertEqual(views.request_body(dict(entry, filter="is:open"), IDS)["filter"], "is:open AND is:issue")
        everything = dict(entry, include_pull_requests=True)
        self.assertEqual(views.request_body(everything, IDS)["filter"], "")
        self.assertEqual(views.request_body(dict(everything, filter="is:open"), IDS)["filter"], "is:open")
        self.assertEqual(views.request_body(dict(everything, filter="a:1 OR b:2"), IDS)["filter"], "a:1 OR b:2")
        self.assertEqual(views.request_body({"name": "X", "layout": "table", "include_pull_requests": True}, IDS)["filter"], "-label:dummy")
        self.assertEqual(views.effective_filter("is:open"), "is:open AND is:issue AND -label:dummy")


class ReadingTests(unittest.TestCase):
    def test_a_view_is_read_in_the_form_of_the_definition(self):
        read = views.current_state(node(3, "Board", "BOARD_LAYOUT", " is:open ", "Version", "Status", [("Priority", "ASC")], ["Title", "Status"]))
        self.assertEqual((read["layout"], read["filter"], read["group_by"], read["vertical_group_by"]),
                         ("board", "is:open", "Version", "Status"))
        self.assertEqual(read["sort_by"], [["Priority", "asc"]])
        self.assertEqual(read["visible_fields"], ["Status", "Title"])

    def test_a_view_that_matches_has_no_differences(self):
        entry = BACKLOG
        self.assertEqual(views.differences(views.desired_state(entry), views.current_state(stored(entry))), [])

    def test_each_difference_is_named(self):
        wanted = views.desired_state({"name": "X", "layout": "board", "filter": "a:1", "group_by": "Version",
                                      "vertical_group_by": "Status", "sort_by": [["Priority", "asc"]], "visible_fields": ["Title"]})
        current = views.current_state(node(1, "X", "TABLE_LAYOUT", "b:2", None, None, [], ["Title", "Status"]))
        self.assertEqual(views.differences(wanted, current),
                         ["layout", "filter", "group_by", "vertical_group_by", "sort_by", "visible_fields"])

    def test_a_visible_field_the_board_cannot_report_is_not_compared(self):
        # GraphQL does not list the Type field among a view's visible fields, so a view showing it must not look changed.
        wanted = views.desired_state({"name": "X", "layout": "table", "visible_fields": ["Title", "Type"]})
        current = views.current_state(node(1, "X", "TABLE_LAYOUT", "is:issue AND -label:dummy", fields=["Title"]))
        self.assertEqual(views.differences(wanted, current), [])

    def test_a_sort_that_can_only_be_set_by_hand_is_not_compared(self):
        wanted = views.desired_state({"name": "X", "layout": "table", "sort_by": [["Created", "asc"]]})
        by_hand = views.current_state(node(1, "X", "TABLE_LAYOUT", "is:issue AND -label:dummy", sort=[("Created", "ASC")]))
        none = views.current_state(node(1, "X", "TABLE_LAYOUT", "is:issue AND -label:dummy"))
        self.assertEqual(views.differences(wanted, by_hand), [])
        self.assertEqual(views.differences(wanted, none), [])

    def test_visible_fields_are_compared_only_when_the_definition_names_them(self):
        wanted = views.desired_state({"name": "X", "layout": "table"})
        current = views.current_state(node(1, "X", "TABLE_LAYOUT", "is:issue AND -label:dummy", fields=["Title", "Status"]))
        self.assertEqual(views.differences(wanted, current), [])


class SyncTests(unittest.TestCase):
    def sync(self, project, definition, **options):
        options.setdefault("dry_run", False)
        return views.sync(project, BOARD, definition, **options)

    def test_missing_views_are_created_in_the_order_of_the_file(self):
        project = FakeProject()
        self.sync(project, [ALL, BACKLOG])
        self.assertEqual([(c[0], c[2]["name"]) for c in project.calls], [("create", "All"), ("create", "Backlog")])
        self.assertTrue(all(c[1] == 7 for c in project.calls))

    def test_a_dry_run_changes_nothing_and_says_what_it_would_do(self):
        project = FakeProject([node(2, "Mine")])
        run = self.sync(project, [ALL], dry_run=True, delete_unlisted=True)
        self.assertEqual(project.calls, [])
        self.assertTrue(any("create the table view" in line for line in run.log))
        self.assertTrue(any("delete view #2" in line for line in run.log))

    def test_a_created_view_with_a_hand_set_sort_says_so(self):
        entry = {"name": "Everything", "layout": "table", "sort_by": [["Created", "asc"]], "include_test_tickets": True}
        run = self.sync(FakeProject(), [entry])
        self.assertTrue(any("set the sort by Created asc by hand" in line for line in run.log))

    def test_a_created_view_reminds_of_its_manual_steps(self):
        entry = {"name": "Everything", "layout": "table", "manual_steps": ["turn off Show hierarchy"]}
        run = self.sync(FakeProject(), [entry])
        self.assertTrue(any("by hand in the web interface (the API cannot): turn off Show hierarchy" in line for line in run.log))
        quiet = self.sync(FakeProject([stored(entry)]), [entry])
        self.assertFalse(any("by hand" in line for line in quiet.log))

    def test_views_that_match_are_left_alone(self):
        project = FakeProject([stored(ALL), stored(BACKLOG)])
        run = self.sync(project, [ALL, BACKLOG])
        self.assertEqual(project.calls, [])
        self.assertEqual(run.log, ["view All: up to date", "view Backlog: up to date"])

    def test_a_changed_view_is_created_again_and_the_old_one_deleted_after(self):
        old = stored(BACKLOG)
        old["filter"] = "status:ToDo"
        old["id"] = "OLD"
        project = FakeProject([old])
        run = self.sync(project, [BACKLOG])
        self.assertEqual([c[0] for c in project.calls], ["create", "delete"])
        self.assertEqual(project.calls[1][1], "OLD")
        self.assertIn("filter", run.log[1])

    def test_the_last_view_of_a_board_is_replaced_by_creating_first(self):
        # GitHub refuses to delete a board's last view, so a lone changed view must get its replacement before it goes.
        only = stored(ALL)
        only["filter"] = "different"
        project = FakeProject([only])
        self.sync(project, [ALL])
        self.assertEqual(project.calls[0][0], "create")

    def test_views_after_a_changed_one_are_recreated_to_keep_the_order(self):
        first = stored(ALL)
        first["filter"] = "something else"
        second = stored(BACKLOG)
        second["id"] = "SECOND"
        project = FakeProject([first, second])
        self.sync(project, [ALL, BACKLOG])
        self.assertEqual([(c[0], c[2]["name"] if c[0] == "create" else c[1]) for c in project.calls],
                         [("create", "All"), ("delete", "V10"), ("create", "Backlog"), ("delete", "SECOND")])

    def test_a_view_before_the_changed_one_is_left_alone(self):
        changed = stored(BACKLOG)
        changed["filter"] = "x"
        project = FakeProject([stored(ALL), changed])
        self.sync(project, [ALL, BACKLOG])
        self.assertEqual([c[0] for c in project.calls], ["create", "delete"])
        self.assertEqual(project.calls[0][2]["name"], "Backlog")

    def test_only_one_view_is_applied_without_touching_the_others(self):
        project = FakeProject([node(2, "Mine")])
        self.sync(project, [ALL, BACKLOG], only="Backlog", delete_unlisted=True)
        self.assertEqual([(c[0], c[2]["name"]) for c in project.calls], [("create", "Backlog")])

    def test_an_unknown_name_for_only_is_refused(self):
        with self.assertRaises(views.ViewsError):
            self.sync(FakeProject(), [ALL], only="Nope")

    def test_unlisted_views_are_kept_unless_deletion_is_asked_for(self):
        project = FakeProject([node(2, "Mine"), stored(ALL)])
        run = self.sync(project, [ALL])
        self.assertEqual(project.calls, [])
        self.assertTrue(any("Mine: not in the definition file (kept" in line for line in run.log))
        self.sync(project, [ALL], delete_unlisted=True)
        self.assertEqual(project.calls, [("delete", "V2")])

    def test_an_empty_definition_cannot_delete_every_view(self):
        # Replaces the earlier idea that an empty definition removes everything: GitHub keeps a board's last view.
        project = FakeProject([node(2, "Mine"), node(3, "Alerts")])
        with self.assertRaises(views.ViewsError):
            self.sync(project, [], delete_unlisted=True)
        self.assertEqual(project.calls, [])

    def test_a_duplicate_name_on_the_board_is_cleaned_up(self):
        project = FakeProject([stored(ALL), dict(stored(ALL), id="DUP", number=11)])
        self.sync(project, [ALL])
        self.assertEqual([c[0] for c in project.calls], ["create", "delete", "delete"])

    def test_nothing_is_changed_when_a_field_name_is_unknown(self):
        project = FakeProject()
        bad = {"name": "Bad", "layout": "table", "group_by": "Colour"}
        with self.assertRaises(views.ViewsError):
            self.sync(project, [ALL, bad])
        self.assertEqual(project.calls, [])  # All was not created either: every field name is checked first


class ByHandTests(unittest.TestCase):
    def test_the_reminder_lists_sorts_and_steps_of_every_entry(self):
        lines = views.by_hand([{"name": "All", "layout": "table", "sort_by": [["Created", "asc"]], "manual_steps": ["turn off Show hierarchy"]},
                               {"name": "Board", "layout": "board"}])
        self.assertIn("  All: set the sort to Created asc", lines)
        self.assertIn("  All: turn off Show hierarchy", lines)
        self.assertEqual(len(lines), 3)

    def test_there_is_no_reminder_when_nothing_is_by_hand(self):
        self.assertEqual(views.by_hand([ALL]), [])


class DeleteTests(unittest.TestCase):
    def test_only_the_named_view_is_deleted(self):
        project = FakeProject([node(2, "Mine"), node(3, "DUMMY scratch")])
        run = views.delete_named(project, BOARD, "DUMMY scratch", dry_run=False)
        self.assertEqual(project.calls, [("delete", "V3")])
        self.assertEqual(run.log, ["view DUMMY scratch: delete view #3"])

    def test_the_last_view_of_the_board_is_not_deleted(self):
        project = FakeProject([node(3, "DUMMY scratch")])
        with self.assertRaises(views.ViewsError):
            views.delete_named(project, BOARD, "DUMMY scratch", dry_run=False)
        self.assertEqual(project.calls, [])

    def test_a_dry_run_deletes_nothing(self):
        project = FakeProject([node(2, "Mine"), node(3, "DUMMY scratch")])
        views.delete_named(project, BOARD, "DUMMY scratch")
        self.assertEqual(project.calls, [])

    def test_a_name_that_is_not_on_the_board_is_refused(self):
        with self.assertRaises(views.ViewsError):
            views.delete_named(FakeProject([node(2, "Mine")]), BOARD, "Nope", dry_run=False)


class ClientTests(unittest.TestCase):
    def test_create_and_delete_use_the_right_calls(self):
        seen = []

        def transport(method, url, headers, body):
            seen.append((method, url, json.loads(body) if body else None))
            return 200, json.dumps({"data": {}}), {}

        client = Client("t", "owner/repo", transport)
        client.create_view(7, {"name": "X"})
        client.delete_view("V1")
        self.assertEqual(seen[0][:2], ("POST", "https://api.github.com/orgs/owner/projectsV2/7/views"))
        self.assertEqual(seen[0][2], {"name": "X"})
        self.assertIn("deleteProjectV2View", seen[1][2]["query"])
        self.assertEqual(seen[1][2]["variables"], {"v": "V1"})

    def test_field_ids_join_graphql_and_rest(self):
        def transport(method, url, headers, body):
            if url.endswith("/graphql"):
                nodes = [{"databaseId": 10, "name": "Updated"}, {}, {"databaseId": 11, "name": "Title"}]
                return 200, json.dumps({"data": {"node": {"fields": {"nodes": nodes}}}}), {}
            return 200, json.dumps([{"id": 11, "name": "Title"}, {"id": 12, "name": "Type"}]), {}

        ids = Client("t", "owner/repo", transport).view_field_ids("P7", 7)
        self.assertEqual(ids, {"Updated": 10, "Title": 11, "Type": 12})


class MainTests(unittest.TestCase):
    def test_it_needs_a_repository(self):
        saved = os.environ.pop("GITHUB_REPOSITORY", None)
        try:
            self.assertEqual(views.main([]), 1)
        finally:
            if saved is not None:
                os.environ["GITHUB_REPOSITORY"] = saved


if __name__ == "__main__":
    unittest.main()
