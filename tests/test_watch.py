import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import finalize  # noqa: E402
import preflight  # noqa: E402
import condition_comments  # noqa: E402
import watch  # noqa: E402

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


def ago(days, hours=0):
    return (NOW - timedelta(days=days, hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ticket(number, status, quiet_days, waiting=None, attention=None, build="", kind="Task", comments=()):
    """A board ticket whose board item was last changed `quiet_days` ago."""
    return {"id": f"I{number}", "updatedAt": ago(quiet_days),
            "content": {"number": number, "issueType": {"name": kind} if kind else None, "comments": {"nodes": list(comments)}},
            "status": {"name": status} if status else None,
            "waiting": {"name": waiting} if waiting else None,
            "attention": {"name": attention} if attention else None,
            "build": {"text": build} if build else None}


def comment(days, body="a person wrote this"):
    return {"createdAt": ago(days), "body": body}


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
        self.sets.append((item_id, field_id, value["singleSelectOptionId"]))


class FakeRepo:
    repo = "owner/repo"

    def __init__(self):
        self.comments = []

    def comment(self, number, body):
        self.comments.append((number, body))


def board():
    fields = {name: {"id": f"F-{name}", "type": kind, "options": {v: f"{name}-{v}" for v in (values or [])}}
              for name, (kind, values) in preflight.REQUIRED_FIELDS.items()}
    return preflight.Board("P7", 7, "Governance", fields)


def sweep(nodes, dry_run=False):
    run, repo, project = finalize.Runner(dry_run), FakeRepo(), FakeProject(nodes)
    flagged = watch.sweep(run, repo, project, board(), NOW)
    return run, repo, project, flagged


class ThresholdTests(unittest.TestCase):
    def test_each_stage_has_its_own_limit(self):
        cases = (("Review", 7), ("OnDeck", 30), ("InProgress", 30), ("Suspended", 182))
        for status, limit in cases:
            _, _, project, flagged = sweep([ticket(1, status, limit - 1, build="")])
            self.assertEqual(flagged, [], f"{status} just under the limit")
            _, repo, project, flagged = sweep([ticket(1, status, limit)])
            self.assertEqual(flagged, [1], f"{status} at the limit")
            self.assertEqual(project.sets, [("I1", "F-Attention", "Attention-Watch")])
            self.assertIn(f"no activity at {status} for {limit} days", repo.comments[0][1])

    def test_stages_with_no_limit_are_never_flagged(self):
        for status in ("ToDo", "Completed", "Abandoned", None):
            self.assertEqual(sweep([ticket(1, status, 400)])[3], [], status)

    def test_waiting_for_input_for_two_weeks(self):
        _, repo, _, flagged = sweep([ticket(1, "InProgress", 14, waiting="Needs input")])
        self.assertEqual(flagged, [1])
        self.assertIn("waiting for input for 14 days", repo.comments[0][1])
        self.assertEqual(sweep([ticket(1, "InProgress", 13, waiting="Needs input")])[3], [])
        self.assertEqual(sweep([ticket(1, "ToDo", 20, waiting="Needs input")])[3], [1])
        self.assertEqual(sweep([ticket(1, "Completed", 20, waiting="Needs input")])[3], [])

    def test_a_ticket_not_waiting_is_judged_by_its_stage_only(self):
        self.assertEqual(sweep([ticket(1, "InProgress", 20)])[3], [])


class ActivityTests(unittest.TestCase):
    def test_a_recent_comment_is_activity(self):
        self.assertEqual(sweep([ticket(1, "Review", 30, comments=[comment(2)])])[3], [])

    def test_the_automations_own_flag_comments_do_not_count(self):
        flag = comment(1, "<!-- attention:caution -->\nAttention: Caution. New work arrived.")
        self.assertEqual(sweep([ticket(1, "Review", 30, comments=[flag])])[3], [1])

    def test_a_recent_build_is_activity(self):
        stamp = (NOW - timedelta(days=2)).strftime("%Y%m%d%H%M%S")
        self.assertEqual(sweep([ticket(1, "Review", 30, build=stamp)])[3], [])
        old = (NOW - timedelta(days=20)).strftime("%Y%m%d%H%M%S")
        self.assertEqual(sweep([ticket(1, "Review", 30, build=old)])[3], [1])

    def test_a_board_change_is_activity(self):
        self.assertEqual(sweep([ticket(1, "Review", 3)])[3], [])


class FlagRulesTests(unittest.TestCase):
    def test_only_blank_fine_or_acknowledged_tickets_are_flagged(self):
        for attention in (None, "Fine", "Acknowledged"):
            self.assertEqual(sweep([ticket(1, "Review", 10, attention=attention)])[3], [1], attention)
        for attention in ("Watch", "Caution", "AtRisk"):
            self.assertEqual(sweep([ticket(1, "Review", 10, attention=attention)])[3], [], attention)

    def test_not_raised_again_for_the_same_situation_after_a_person_closed_it(self):
        raised = comment(5, "<!-- attention:watch situation=Review/20261001000000 -->\nAttention: Watch. ...")
        stale = ticket(1, "Review", 10, attention="Fine", build="20261001000000", comments=[raised])
        self.assertEqual(sweep([stale])[3], [])

    def test_raised_again_when_the_stage_changes(self):
        raised = comment(5, "<!-- attention:watch situation=InProgress/20261001000000 -->\nAttention: Watch. ...")
        stale = ticket(1, "Review", 10, attention="Fine", build="20261001000000", comments=[raised])
        self.assertEqual(sweep([stale])[3], [1])

    def test_raised_again_when_new_work_arrives(self):
        raised = comment(15, "<!-- attention:watch situation=Review/20260901000000 -->\nAttention: Watch. ...")
        stale = ticket(1, "Review", 10, attention="Acknowledged", build="20260915000000", comments=[raised])
        self.assertEqual(sweep([stale])[3], [1])

    def test_version_and_alert_tickets_have_no_attention(self):
        self.assertEqual(sweep([ticket(1, "Review", 50, kind="Version"), ticket(2, "Review", 50, kind="Alert")])[3], [])

    def test_the_comment_carries_the_marker_and_says_what_to_do(self):
        _, repo, _, _ = sweep([ticket(1, "Review", 10, build="20261001000000", comments=[comment(10)])])
        text = repo.comments[0][1]
        self.assertTrue(text.startswith("<!-- attention:watch situation=Review/20261001000000 -->\n"))
        self.assertIn("then tick a box below", text)
        self.assertIn("<!-- condition:stale -->", text)
        self.assertEqual(condition_comments.state(text), "open")
        self.assertTrue(watch.SITUATION.search(text))

    def test_one_comment_per_flagged_ticket(self):
        _, repo, project, flagged = sweep([ticket(1, "Review", 10), ticket(2, "InProgress", 40), ticket(3, "Review", 1)])
        self.assertEqual(flagged, [1, 2])
        self.assertEqual([number for number, _ in repo.comments], [1, 2])
        self.assertEqual(len(project.sets), 2)

    def test_dry_run_changes_nothing(self):
        run, repo, project, _ = sweep([ticket(1, "Review", 10)], dry_run=True)
        self.assertEqual((repo.comments, project.sets), ([], []))
        self.assertEqual(len(run.log), 2)

    def test_every_page_is_read_and_draft_items_skipped(self):
        nodes = [ticket(n, "ToDo", 1) for n in range(1, 230)] + [ticket(500, "Review", 10), {"id": "D", "updatedAt": ago(1), "content": {}}]
        self.assertEqual(sweep(nodes)[3], [500])


if __name__ == "__main__":
    unittest.main()
