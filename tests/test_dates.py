import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import dates  # noqa: E402
import finalize  # noqa: E402
import preflight  # noqa: E402

TODAY = "2026-10-06"


def node(number, status, start=None, end=None, kind="Task"):
    return {"id": f"I{number}", "content": {"number": number, "issueType": {"name": kind} if kind else None},
            "status": {"name": status} if status else None,
            "start": {"date": start} if start else None,
            "end": {"date": end} if end else None}


class FakeProject:
    repo = "owner/repo"

    def __init__(self, nodes, per_page=100):
        self.nodes, self.per_page, self.sets, self.cleared, self.queries = nodes, per_page, [], [], 0

    def graphql(self, query, variables=None):
        start = int(variables["after"] or 0)
        self.queries += 1
        end = start + self.per_page
        return {"node": {"items": {"pageInfo": {"hasNextPage": end < len(self.nodes), "endCursor": str(end)},
                                   "nodes": self.nodes[start:end]}}}

    def set_project_field(self, project_id, item_id, field_id, value):
        self.sets.append((item_id, field_id, value["date"]))

    def clear_project_field(self, project_id, item_id, field_id):
        self.cleared.append((item_id, field_id))


def board():
    fields = {name: {"id": f"F-{name}", "type": kind, "options": {}} for name, (kind, values) in preflight.REQUIRED_FIELDS.items()}
    return preflight.Board("P7", 7, "Governance", fields)


def run_sweep(nodes, dry_run=False):
    run, project = finalize.Runner(dry_run), FakeProject(nodes)
    dates.sweep(run, project, board(), TODAY)
    return run, project


class SweepTests(unittest.TestCase):
    def test_start_date_is_set_for_every_started_status(self):
        for status in ("InProgress", "Review", "Completed", "Suspended", "Abandoned"):
            _, project = run_sweep([node(1, status)])
            self.assertIn(("I1", "F-Start date", TODAY), project.sets, status)

    def test_nothing_before_the_work_starts(self):
        for status in ("ToDo", "OnDeck", None):
            _, project = run_sweep([node(1, status)])
            self.assertEqual((project.sets, project.cleared), ([], []), status)

    def test_end_date_for_completed_and_abandoned_only(self):
        for status in ("Completed", "Abandoned"):
            _, project = run_sweep([node(1, status, start="2026-10-01")])
            self.assertEqual(project.sets, [("I1", "F-End date", TODAY)])
        _, project = run_sweep([node(1, "Review", start="2026-10-01")])
        self.assertEqual(project.sets, [])

    def test_dates_already_there_are_never_overwritten(self):
        _, project = run_sweep([node(1, "Completed", start="2026-09-01", end="2026-09-05")])
        self.assertEqual((project.sets, project.cleared), ([], []))

    def test_end_date_is_cleared_when_the_ticket_is_open_again_and_set_again_later(self):
        run, project = run_sweep([node(1, "InProgress", start="2026-10-01", end="2026-10-03")])
        self.assertEqual((project.sets, project.cleared), ([], [("I1", "F-End date")]))
        self.assertIn("seen open again at InProgress", run.log[0])
        _, project = run_sweep([node(1, "Completed", start="2026-10-01")])
        self.assertEqual(project.sets, [("I1", "F-End date", TODAY)])

    def test_version_and_alert_tickets_have_no_dates(self):
        _, project = run_sweep([node(1, "Completed", kind="Version"), node(2, "Review", kind="Alert")])
        self.assertEqual((project.sets, project.cleared), ([], []))

    def test_a_ticket_with_no_type_is_treated_as_work(self):
        _, project = run_sweep([node(1, "Review", kind=None)])
        self.assertEqual(project.sets, [("I1", "F-Start date", TODAY)])

    def test_draft_items_are_skipped(self):
        _, project = run_sweep([{"id": "D1", "content": {}, "status": {"name": "InProgress"}, "start": None, "end": None}])
        self.assertEqual(project.sets, [])

    def test_a_direct_abandon_gets_both_dates_on_the_same_day(self):
        _, project = run_sweep([node(1, "Abandoned")])
        self.assertEqual(sorted(field for _, field, _ in project.sets), ["F-End date", "F-Start date"])

    def test_dry_run_changes_nothing(self):
        run, project = run_sweep([node(1, "Completed"), node(2, "InProgress", start="2026-10-01", end="2026-10-03")], dry_run=True)
        self.assertEqual((project.sets, project.cleared), ([], []))
        self.assertEqual(len(run.log), 3)

    def test_every_page_of_the_board_is_read(self):
        project = FakeProject([node(n, "ToDo") for n in range(1, 230)] + [node(500, "Review")])
        found = dates.board_items(project, board())
        self.assertEqual(len(found), 230)
        self.assertEqual(project.queries, 3)

    def test_running_the_sweep_again_after_it_has_set_the_dates_does_nothing(self):
        _, project = run_sweep([node(1, "Completed", start=TODAY, end=TODAY)])
        self.assertEqual((project.sets, project.cleared), ([], []))


if __name__ == "__main__":
    unittest.main()
