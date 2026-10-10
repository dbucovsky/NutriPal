import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import condition_comments as cc  # noqa: E402
import conditions  # noqa: E402
import finalize  # noqa: E402
import preflight  # noqa: E402
from test_conditions import FakeProject, ticket  # noqa: E402

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
LONG_AGO = "2026-10-10T00:00:00Z"  # 12 hours before NOW
JUST_NOW = "2026-10-10T11:30:00Z"  # 30 minutes before NOW
LEVELS = conditions.DECIDE_LEVELS


def bot(comment_id, body):
    return {"id": comment_id, "body": body, "user": {"type": "Bot"}}


def person(comment_id, body):
    return {"id": comment_id, "body": body, "user": {"type": "User"}}


def flag(condition="stale", fine=" ", elsewhere=" "):
    return (f"<!-- attention:watch situation=Review/1 -->\n<!-- condition:{condition} -->\nAttention: Watch. Old.\n\n"
            f"- [{fine}] {cc.FINE}\n- [{elsewhere}] {cc.ELSEWHERE}")


class Repo:
    def __init__(self, comments=None):
        self.comments, self.posted, self.edited = comments or [], [], []

    def list_comments(self, number):
        return list(self.comments)

    def comment(self, number, body):
        self.posted.append((number, body))

    def edit_comment(self, comment_id, body):
        self.edited.append((comment_id, body))


def board():
    options = {"Fine": "o-fine", "Acknowledged": "o-ack", "Watch": "o-watch", "Caution": "o-caution", "AtRisk": "o-risk"}
    return preflight.Board("P7", 7, "Governance", {"Fix": {"id": "FX", "type": "TEXT", "options": {}},
                                                   "Attention": {"id": "AT", "type": "SINGLE_SELECT", "options": options}})


def refresh(tickets, comments=None, dry=False):
    project, repo, run = FakeProject(tickets), Repo(comments), finalize.Runner(dry)
    conditions.refresh(run, project, board(), repo, NOW)
    return project, repo, run


class TextTests(unittest.TestCase):
    def test_a_new_comment_has_both_markers_and_two_unticked_boxes(self):
        text = cc.decorate("<!-- attention:watch situation=Review/1 -->\nAttention: Watch. Quiet.", "stale")
        self.assertTrue(text.startswith("<!-- attention:watch situation=Review/1 -->\n<!-- condition:stale -->\n"))
        self.assertEqual(cc.condition_of(text), "stale")
        self.assertEqual(cc.state(text), "open")
        self.assertEqual(text.count("- [ ] "), 2)

    def test_ticking_a_box_changes_the_state(self):
        self.assertEqual(cc.state(flag(fine="x")), "fine")
        self.assertEqual(cc.state(flag(elsewhere="x")), "elsewhere")
        self.assertEqual(cc.state(flag(fine="X")), "fine")

    def test_handled_elsewhere_wins_when_both_are_ticked(self):
        self.assertEqual(cc.state(flag(fine="x", elsewhere="x")), "elsewhere")

    def test_a_comment_whose_box_lines_were_edited_is_damaged_and_counts_as_open(self):
        broken = flag().replace(cc.FINE, "Fine, I think")
        self.assertEqual(cc.state(broken), "damaged")
        self.assertEqual(cc.attention_after([("stale", "damaged")], "Watch", LEVELS), None)

    def test_restoring_puts_back_the_missing_line_unticked_and_notes_it_once(self):
        broken = flag(elsewhere="x").replace(cc.FINE, "Fine, I think")
        restored = cc.restore(broken)
        self.assertIn(f"- [ ] {cc.FINE}", restored)
        self.assertEqual(restored.count(cc.RESTORED), 1)
        self.assertEqual(cc.restore(restored).count(cc.RESTORED), 1)

    def test_a_fix_comment_has_no_boxes_and_is_recognised(self):
        text = cc.fix_comment("issue-open", "it is Completed but its issue is still open")
        self.assertTrue(cc.is_fix_comment(text))
        self.assertEqual(cc.condition_of(text), "issue-open")
        self.assertNotIn("- [ ]", text)
        self.assertTrue(cc.is_fixed(cc.mark_fixed(text, "2026-10-10")))
        self.assertIn("✅ fixed on 2026-10-10", cc.mark_fixed(text, "2026-10-10"))


class AttentionRuleTests(unittest.TestCase):
    def after(self, comments, current):
        return cc.attention_after(comments, current, LEVELS)

    def test_all_ticked_fine_gives_fine(self):
        self.assertEqual(self.after([("stale", "fine")], "Watch"), "Fine")

    def test_any_handled_elsewhere_gives_acknowledged(self):
        self.assertEqual(self.after([("stale", "fine"), ("passed-version", "elsewhere")], "Caution"), "Acknowledged")

    def test_two_open_conditions_need_two_ticks(self):
        self.assertIsNone(self.after([("stale", "fine"), ("waited-too-long", "open")], "Watch"))

    def test_the_highest_open_level_wins_and_can_come_down(self):
        self.assertEqual(self.after([("passed-version", "fine"), ("stale", "open")], "Caution"), "Watch")
        self.assertIsNone(self.after([("passed-version", "open"), ("stale", "open")], "Caution"))

    def test_a_value_set_by_hand_or_at_risk_is_never_changed(self):
        for current in ("Fine", "Acknowledged", "AtRisk", None):
            self.assertIsNone(self.after([("stale", "fine")], current), current)

    def test_no_comments_changes_nothing(self):
        self.assertIsNone(self.after([], "Watch"))


class RefreshCommentTests(unittest.TestCase):
    def test_a_ticked_box_clears_the_flag(self):
        project, repo, _ = refresh([ticket(number=4, status="Review", attention="Watch")], [bot(1, flag(fine="x"))])
        self.assertEqual(project.sets, [("I1", "AT", {"singleSelectOptionId": "o-fine"})])
        self.assertEqual((repo.posted, repo.edited), ([], []))

    def test_handled_elsewhere_sets_acknowledged(self):
        project, _, _ = refresh([ticket(number=4, status="Review", attention="Watch")], [bot(1, flag(elsewhere="x"))])
        self.assertEqual(project.sets, [("I1", "AT", {"singleSelectOptionId": "o-ack"})])

    def test_an_unticked_comment_leaves_the_flag(self):
        project, _, _ = refresh([ticket(number=4, status="Review", attention="Watch")], [bot(1, flag())])
        self.assertEqual(project.sets, [])

    def test_a_person_cannot_fake_a_condition_comment(self):
        project, _, _ = refresh([ticket(number=4, status="Review", attention="Watch")], [person(1, flag(fine="x"))])
        self.assertEqual(project.sets, [])

    def test_damaged_boxes_are_put_back_and_the_flag_stays(self):
        project, repo, _ = refresh([ticket(number=4, status="Review", attention="Watch")],
                                   [bot(1, flag().replace(cc.FINE, "Fine, I think"))])
        self.assertEqual(project.sets, [])
        self.assertEqual(len(repo.edited), 1)
        self.assertEqual(repo.edited[0][0], 1)
        self.assertIn(f"- [ ] {cc.FINE}", repo.edited[0][1])

    def test_a_flag_set_by_hand_is_not_raised_again_by_an_unticked_comment(self):
        project, _, _ = refresh([ticket(number=4, status="Review", attention="Fine")], [bot(1, flag())])
        self.assertEqual(project.sets, [])

    def test_a_dry_run_edits_and_sets_nothing(self):
        project, repo, run = refresh([ticket(number=4, status="Review", attention="Watch")], [bot(1, flag(fine="x"))], dry=True)
        self.assertEqual((project.sets, repo.posted, repo.edited), ([], [], []))
        self.assertIn("set Attention to Fine", run.log[0])

    def test_a_ticket_with_nothing_to_look_at_reads_no_comments(self):
        class Strict(Repo):
            def list_comments(self, number):
                raise AssertionError("comments were read")

        project, run = FakeProject([ticket(number=4)]), finalize.Runner(False)
        conditions.refresh(run, project, board(), Strict(), NOW)

    def test_without_a_repo_client_comments_are_never_touched(self):
        project, run = FakeProject([ticket(number=4, status="Completed", resolution=None, item_updated=LONG_AGO)]), finalize.Runner(False)
        conditions.refresh(run, project, board())
        self.assertEqual(len(project.sets), 1)


class FixCommentTests(unittest.TestCase):
    broken = dict(number=9, status="Completed", resolution=None, delivery="Merged", version="V0.1.0", state="CLOSED")

    def test_a_rule_broken_for_two_hours_gets_one_comment(self):
        _, repo, _ = refresh([ticket(fix="completed-without-done", item_updated=LONG_AGO, **self.broken)])
        self.assertEqual(len(repo.posted), 1)
        number, body = repo.posted[0]
        self.assertEqual(number, 9)
        self.assertEqual(cc.condition_of(body), "completed-without-done")
        self.assertTrue(cc.is_fix_comment(body))

    def test_a_recent_change_waits(self):
        _, repo, _ = refresh([ticket(item_updated=JUST_NOW, **self.broken)])
        self.assertEqual(repo.posted, [])

    def test_an_open_comment_is_not_posted_twice(self):
        existing = bot(5, cc.fix_comment("completed-without-done", "x"))
        _, repo, _ = refresh([ticket(fix="completed-without-done", item_updated=LONG_AGO, **self.broken)], [existing])
        self.assertEqual((repo.posted, repo.edited), ([], []))

    def test_a_rule_put_right_marks_its_comment_fixed(self):
        existing = bot(5, cc.fix_comment("completed-without-done", "x"))
        fixed = dict(self.broken, resolution="Done")
        _, repo, _ = refresh([ticket(fix="completed-without-done", item_updated=LONG_AGO, **fixed)], [existing])
        self.assertEqual(len(repo.edited), 1)
        self.assertEqual(repo.edited[0][0], 5)
        self.assertIn("✅ fixed on 2026-10-10", repo.edited[0][1])
        self.assertTrue(repo.edited[0][1].startswith(existing["body"]))  # only appended to: the rest is kept

    def test_a_rule_that_breaks_again_after_being_fixed_gets_a_new_comment(self):
        fixed_before = bot(5, cc.mark_fixed(cc.fix_comment("completed-without-done", "x"), "2026-10-01"))
        _, repo, _ = refresh([ticket(fix="completed-without-done", item_updated=LONG_AGO, **self.broken)], [fixed_before])
        self.assertEqual(len(repo.posted), 1)
        self.assertEqual(repo.edited, [])


if __name__ == "__main__":
    unittest.main()
