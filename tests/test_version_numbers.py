import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import finalize  # noqa: E402
import preflight  # noqa: E402
import version_numbers  # noqa: E402
from versions import Version  # noqa: E402


def node(number, version, version_number=None, kind="Task"):
    return {"id": f"I{number}", "content": {"number": number, "issueType": {"name": kind} if kind else None},
            "version": {"text": version} if version is not None else None,
            "number": {"number": version_number} if version_number is not None else None}


class FakeProject:
    repo = "owner/repo"

    def __init__(self, nodes, per_page=100):
        self.nodes, self.per_page, self.sets = nodes, per_page, []

    def graphql(self, query, variables=None):
        start = int(variables["after"] or 0)
        end = start + self.per_page
        return {"node": {"items": {"pageInfo": {"hasNextPage": end < len(self.nodes), "endCursor": str(end)},
                                   "nodes": self.nodes[start:end]}}}

    def set_project_field(self, project_id, item_id, field_id, value):
        self.sets.append((item_id, field_id, value["number"]))


def board():
    fields = {name: {"id": f"F-{name}", "type": kind, "options": {}} for name, (kind, values) in preflight.REQUIRED_FIELDS.items()}
    return preflight.Board("P7", 7, "Governance", fields)


def run_sweep(nodes, dry_run=False, per_page=100):
    run, project = finalize.Runner(dry_run), FakeProject(nodes, per_page)
    version_numbers.sweep(run, project, board())
    return run, project


class SweepTests(unittest.TestCase):
    def test_an_aimed_ticket_gets_the_number_of_its_version(self):
        _, project = run_sweep([node(1, "V2.1.0")])
        self.assertEqual(project.sets, [("I1", "F-Version#", float(Version.parse("V2.1.0").number()))])

    def test_a_hotfix_keeps_its_digit(self):
        _, project = run_sweep([node(1, "V1.25.0-HF1")])
        self.assertEqual(project.sets[0][2], float(Version.parse("V1.25.0-HF1").number()))
        self.assertNotEqual(project.sets[0][2], float(Version.parse("V1.25.0").number()))

    def test_a_ticket_with_the_right_number_is_left_alone(self):
        number = float(Version.parse("V0.7.0").number())
        _, project = run_sweep([node(1, "V0.7.0", number)])
        self.assertEqual(project.sets, [])

    def test_a_wrong_number_is_corrected(self):
        _, project = run_sweep([node(1, "V0.7.0", 12345.0)])
        self.assertEqual(project.sets[0][2], float(Version.parse("V0.7.0").number()))

    def test_a_blank_version_is_skipped(self):
        for blank in (None, "", "  "):
            run, project = run_sweep([node(1, blank, 5.0)])
            self.assertEqual((project.sets, run.log), ([], []))

    def test_text_that_is_not_a_version_is_reported_and_skipped(self):
        run, project = run_sweep([node(1, "next release"), node(2, "V0.7")])
        self.assertEqual(project.sets, [])
        self.assertEqual(len(run.log), 2)
        self.assertIn("is not a version", run.log[0])

    def test_version_and_alert_tickets_are_left_alone(self):
        _, project = run_sweep([node(1, "V0.7.0", kind="Version"), node(2, "V0.7.0", kind="Alert")])
        self.assertEqual(project.sets, [])

    def test_a_ticket_with_no_type_is_a_work_ticket(self):
        _, project = run_sweep([node(1, "V0.7.0", kind=None)])
        self.assertEqual(len(project.sets), 1)

    def test_a_dry_run_changes_nothing_and_says_what_it_would_do(self):
        run, project = run_sweep([node(1, "V2.1.0")], dry_run=True)
        self.assertEqual(project.sets, [])
        self.assertIn("#1: set Version# to 20010000 (from Version V2.1.0)", run.log)

    def test_every_page_of_the_board_is_read(self):
        nodes = [node(n, "V1.0.0") for n in range(1, 6)]
        _, project = run_sweep(nodes, per_page=2)
        self.assertEqual(len(project.sets), 5)

    def test_items_that_are_not_issues_are_skipped(self):
        draft = {"id": "D1", "content": {}, "version": {"text": "V1.0.0"}, "number": None}
        pull_request = {"id": "P1", "content": None, "version": {"text": "V1.0.0"}, "number": None}
        _, project = run_sweep([draft, pull_request, node(1, "V1.0.0")])
        self.assertEqual([s[0] for s in project.sets], ["I1"])

    def test_nothing_else_is_written(self):
        _, project = run_sweep([node(1, "V2.1.0")])
        self.assertEqual({field for _, field, _ in project.sets}, {"F-Version#"})


class MainTests(unittest.TestCase):
    def test_it_needs_a_repository(self):
        saved = os.environ.pop("GITHUB_REPOSITORY", None)
        try:
            self.assertEqual(version_numbers.main([]), 1)
        finally:
            if saved is not None:
                os.environ["GITHUB_REPOSITORY"] = saved


if __name__ == "__main__":
    unittest.main()
