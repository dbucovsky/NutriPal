import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import checks  # noqa: E402
import condition_comments  # noqa: E402
import preflight  # noqa: E402
import push_step  # noqa: E402

MAIN = """# Changelog

## V0.4.0 — 2026-10-06 00:47 UTC
### Build 20261006004523 (branch old-work)
#### #28 — Earlier work
- done.
"""

EARLIER = "20261006080000"  # a build older than the ones pushed in these tests

ONE = """# Changelog

## WIP-Version
### Build 20261006090000 (branch feature)
#### #201 — Add CSV export
- export: added.

""" + MAIN.split("\n", 2)[2]

TWO = ONE.replace("### Build 20261006090000 (branch feature)", """### Build 20261006100000 (branch feature)
#### #201 — Add CSV export
- export: more.
#### #205 — Write the guide
- guide: written.
#### REF 20261006100500 — no ticket yet
- typo.
### Build 20261006090000 (branch feature)""")


class GitRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "T")
        self.git("config", "user.email", "t@example.com")
        self.commit(MAIN, "start")
        self.git("update-ref", "refs/remotes/origin/main", "main")
        self.git("switch", "-q", "-c", "feature")

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.dir, capture_output=True, text=True, encoding="utf-8")
        return result.stdout.strip()

    def commit(self, text, message):
        with open(os.path.join(self.dir, "CHANGELOG.md"), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")


class NewBuildsTests(GitRepo):
    def test_a_new_branch_is_compared_with_main(self):
        after = self.commit(ONE, "first")
        found = push_step.new_ticket_builds(self.dir, checks.ZEROS, after)
        self.assertEqual(found, {201: ("20261006090000", "feature")})

    def test_a_later_push_only_counts_its_own_builds(self):
        first = self.commit(ONE, "first")
        second = self.commit(TWO, "second")
        found = push_step.new_ticket_builds(self.dir, first, second)
        self.assertEqual(found, {201: ("20261006100000", "feature"), 205: ("20261006100000", "feature")})

    def test_a_push_with_no_new_entries(self):
        first = self.commit(ONE, "first")
        second = self.commit(ONE + "\n", "whitespace")
        self.assertEqual(push_step.new_ticket_builds(self.dir, first, second), {})

    def test_finalized_builds_brought_in_by_a_sync_are_ignored(self):
        first = self.commit(ONE, "first")
        text = ONE.replace("### Build 20261006004523 (branch old-work)", "### Build 20261007000000 (branch other)\n#### #99 — Other\n- x.\n### Build 20261006004523 (branch old-work)")
        synced = self.commit(text, "sync")
        self.assertEqual(push_step.new_ticket_builds(self.dir, first, synced), {})

    def test_no_changelog_at_all(self):
        self.assertEqual(push_step.new_ticket_builds(self.dir, checks.ZEROS, self.git("rev-parse", "main"), base="nowhere"), {})


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


class FakeProject:
    repo = "owner/repo"

    def __init__(self, items):
        self.items, self.sets, self.added = items, [], []

    def graphql(self, query, variables=None):
        number = variables["num"]
        item = self.items.get(number, {})
        node = None
        if item is not None:
            node = {"id": f"I{number}", "project": {"id": "P7"},
                    "status": {"name": item["status"]} if item.get("status") else None,
                    "delivery": {"name": item["delivery"]} if item.get("delivery") else None,
                    "build": {"text": item["build"]} if item.get("build") else None,
                    "attention": {"name": item["attention"]} if item.get("attention") else None}
        return {"repository": {"issue": {"id": f"N{number}", "title": "t", "projectItems": {"nodes": [node] if node else []}}}}

    def add_to_project(self, project_id, content_id):
        self.added.append(content_id)
        return "I-new"

    def set_project_field(self, project_id, item_id, field_id, value):
        self.sets.append((item_id, field_id, value))


class HandlePushTests(GitRepo):
    def push(self, items, text=ONE, dry_run=False):
        after = self.commit(text, "work")
        repo, project = FakeRepo(), FakeProject(items)
        run = push_step.handle_push(self.dir, repo, project, board(), checks.ZEROS, after, dry_run)
        sets = {(item, field): value for item, field, value in project.sets}
        return run, repo, project, sets

    def test_a_todo_ticket_becomes_pushed_and_inprogress(self):
        _, repo, _, sets = self.push({201: {"status": "ToDo"}})
        self.assertEqual(sets[("I201", "F-Delivery")], {"singleSelectOptionId": "Delivery-Pushed"})
        self.assertEqual(sets[("I201", "F-Status")], {"singleSelectOptionId": "Status-InProgress"})
        self.assertEqual(sets[("I201", "F-Build")], {"text": "20261006090000"})
        self.assertNotIn(("I201", "F-Attention"), sets)
        self.assertEqual(repo.comments, [])

    def test_ondeck_also_advances(self):
        _, _, _, sets = self.push({201: {"status": "OnDeck"}})
        self.assertIn(("I201", "F-Status"), sets)

    def test_inprogress_is_left_alone(self):
        _, _, _, sets = self.push({201: {"status": "InProgress", "delivery": "Pushed", "build": "20261006090000"}})
        self.assertEqual(sets, {})

    def test_new_work_on_a_finished_ticket_raises_caution_once(self):
        for status in ("Completed", "Abandoned", "Review", "Suspended"):
            _, repo, _, sets = self.push({201: {"status": status, "delivery": "Merged", "build": EARLIER}}, text=ONE + status)
            self.assertEqual(sets[("I201", "F-Attention")], {"singleSelectOptionId": "Attention-Caution"})
            self.assertNotIn(("I201", "F-Status"), sets)  # never moved out of its state
            self.assertEqual(sets[("I201", "F-Delivery")], {"singleSelectOptionId": "Delivery-Pushed"})
            self.assertIn(f"which is {status}: build 20261006090000 (branch feature)", repo.comments[0][1])
            self.assertIn("<!-- condition:new-work-on-finished-ticket -->", repo.comments[0][1])
            self.assertEqual(condition_comments.state(repo.comments[0][1]), "open")

    def test_the_first_push_of_a_finished_ticket_raises_nothing(self):
        # A ticket moved to Review before its first push is the normal flow: no earlier work was delivered.
        for delivery in (None, "Committed"):
            for status in ("Completed", "Abandoned", "Review", "Suspended"):
                _, repo, _, sets = self.push({201: {"status": status, "delivery": delivery}}, text=ONE + status + str(delivery))
                self.assertNotIn(("I201", "F-Attention"), sets)
                self.assertEqual(repo.comments, [])
                self.assertEqual(sets[("I201", "F-Delivery")], {"singleSelectOptionId": "Delivery-Pushed"})

    def test_every_delivered_value_counts_as_earlier_work(self):
        for delivery in ("Pushed", "Merged", "Implemented", "Released", "Dropped"):
            _, repo, _, sets = self.push({201: {"status": "Review", "delivery": delivery, "build": EARLIER}}, text=ONE + delivery)
            self.assertIn(("I201", "F-Attention"), sets, delivery)

    def test_a_delivery_set_by_hand_with_no_build_is_a_first_push(self):
        # The case behind the false Caution: Delivery Pushed written by hand just before the push step ran.
        for delivery in ("Pushed", "Merged", "Released", "Dropped"):
            _, repo, _, sets = self.push({201: {"status": "Review", "delivery": delivery}}, text=ONE + delivery)
            self.assertNotIn(("I201", "F-Attention"), sets, delivery)
            self.assertEqual(repo.comments, [])

    def test_a_build_that_is_not_older_raises_nothing(self):
        # Equal: the same push handled twice. Newer: an older-stamped build pushed later.
        for build in ("20261006090000", "20261006100000"):
            _, repo, _, sets = self.push({201: {"status": "Review", "delivery": "Pushed", "build": build}}, text=ONE + build)
            self.assertNotIn(("I201", "F-Attention"), sets, build)
            self.assertEqual(repo.comments, [])

    def test_a_build_that_is_not_a_stamp_counts_as_none(self):
        for build in ("hand-set", "2026-10-06", "2026100608000"):
            _, repo, _, sets = self.push({201: {"status": "Review", "delivery": "Pushed", "build": build}}, text=ONE + build)
            self.assertNotIn(("I201", "F-Attention"), sets, build)

    def test_an_implemented_ticket_counts_as_earlier_work_without_a_build(self):
        for status in ("Completed", "Review"):
            _, repo, _, sets = self.push({201: {"status": status, "delivery": "Implemented"}}, text=ONE + status)
            self.assertEqual(sets[("I201", "F-Attention")], {"singleSelectOptionId": "Attention-Caution"})
            self.assertEqual(len(repo.comments), 1)

    def test_an_open_flag_is_not_raised_again(self):
        for flag in ("Caution", "AtRisk"):
            _, repo, _, sets = self.push({201: {"status": "Review", "attention": flag, "delivery": "Pushed", "build": EARLIER}})
            self.assertNotIn(("I201", "F-Attention"), sets)
            self.assertEqual(repo.comments, [])

    def test_a_closed_flag_is_raised_again_for_new_work(self):
        for value in ("Fine", "Acknowledged", "Watch"):
            _, repo, _, sets = self.push({201: {"status": "Review", "attention": value, "delivery": "Pushed", "build": EARLIER}})
            self.assertIn(("I201", "F-Attention"), sets)
            self.assertEqual(len(repo.comments), 1)

    def test_several_tickets_and_a_ref(self):
        _, repo, project, sets = self.push({201: {"status": "ToDo"}, 205: {"status": "Completed", "delivery": "Merged", "build": EARLIER}}, text=TWO)
        self.assertEqual(sets[("I201", "F-Build")], {"text": "20261006100000"})
        self.assertIn(("I205", "F-Attention"), sets)
        self.assertEqual([c[0] for c in repo.comments], [205])

    def test_a_ticket_not_on_the_board_is_added(self):
        _, _, project, _ = self.push({201: None})
        self.assertEqual(project.added, ["N201"])

    def test_dry_run_changes_nothing(self):
        run, repo, project, sets = self.push({201: {"status": "Review"}}, dry_run=True)
        self.assertEqual((sets, repo.comments, project.added), ({}, [], []))
        self.assertTrue(any("set Delivery to Pushed" in line for line in run.log))

    def test_no_new_entries(self):
        after = self.git("rev-parse", "HEAD")
        run = push_step.handle_push(self.dir, FakeRepo(), FakeProject({}), board(), after, after)
        self.assertEqual(run.log, ["no new changelog entries for a ticket in this push"])

    def test_no_board(self):
        after = self.commit(ONE, "work")
        run = push_step.handle_push(self.dir, FakeRepo(), None, None, checks.ZEROS, after)
        self.assertIn("board steps skipped", run.log[0])


if __name__ == "__main__":
    unittest.main()
