import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import hotfix  # noqa: E402
import preflight  # noqa: E402
from github_api import GitHubError  # noqa: E402
from versions import Version  # noqa: E402

NOW = datetime(2026, 10, 7, 11, 5, 0, tzinfo=timezone.utc)
V = Version.parse
BRANCH = "hotfix-v1-25-0-fix-sensor-timeout"

RELEASED = "# Changelog\n\n## V1.25.0 — 2026-09-01 10:00 UTC\n### Build 20260901100000 (branch old)\n#### #200 — Old work\n- done.\n"
HOTFIX = ("# Changelog\n\n## WIP-Version{marker}\n### Build 20261007100000 (branch " + BRANCH + ")\n"
          "#### #301 — Fix the sensor timeout\n- timeout: fixed.\n#### #302 — Document the fix\n- doc: written.\n\n"
          + RELEASED.split("\n", 2)[2])


class FakeRepo:
    repo = "owner/repo"

    def __init__(self, tags=(), tickets=()):
        self.tags, self.tickets = set(tags), list(tickets)
        self.created_tags, self.comments, self.issues, self.subs, self.closed = [], [], [], [], []

    def repo_path(self, path):
        return path

    def request(self, method, path, body=None):
        if "/git/ref/tags/" in path:
            if path.split("/git/ref/tags/")[1] in self.tags:
                return {"ref": "x"}
            raise GitHubError(404, "Not Found")
        return self.tickets

    def issue_type(self, number):
        return "Bug"

    def create_tag(self, name, sha):
        self.created_tags.append((name, sha))

    def create_issue(self, title, body, issue_type=None, labels=(), assignees=()):
        self.issues.append((title, body, issue_type))
        return {"number": 90, "node_id": "N90"}

    def add_sub_issue(self, parent, child):
        self.subs.append((parent, child))

    def close_issue(self, number, reason="completed"):
        self.closed.append(number)

    def comment(self, number, body):
        self.comments.append((number, body))


class FakeProject:
    repo = "owner/repo"

    def __init__(self):
        self.sets, self.added = [], []

    def graphql(self, query, variables=None):
        number = variables["num"]
        return {"repository": {"issue": {"id": f"N{number}", "title": "t", "projectItems": {"nodes": [
            {"id": f"I{number}", "project": {"id": "P7"}, "status": {"name": "Review"}, "delivery": {"name": "Pushed"},
             "version": None, "build": None, "number": None, "attention": None}]}}}}

    def add_to_project(self, project_id, content_id):
        self.added.append(content_id)
        return "I90"

    def set_project_field(self, project_id, item_id, field_id, value):
        self.sets.append((item_id, field_id, value))


def board():
    fields = {name: {"id": f"F-{name}", "type": kind, "options": {v: f"{name}-{v}" for v in (values or [])}}
              for name, (kind, values) in preflight.REQUIRED_FIELDS.items()}
    return preflight.Board("P7", 7, "Governance", fields)


class HotfixRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.remote = os.path.join(self.tmp.name, "remote.git")
        self.dir = os.path.join(self.tmp.name, "work")
        os.makedirs(self.dir)
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Dev")
        self.git("config", "user.email", "dev@example.com")
        self.git("remote", "add", "origin", self.remote)
        self.commit(RELEASED, "the release")
        self.git("tag", "released/V1.25.0")
        self.commit(RELEASED + "\nmore on main\n", "main moves on")

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.dir, capture_output=True, text=True, encoding="utf-8")
        return result.stdout.strip()

    def commit(self, text, message):
        with open(os.path.join(self.dir, "CHANGELOG.md"), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def start(self, text=HOTFIX.format(marker=""), base="released/V1.25.0", branch=BRANCH):
        self.git("switch", "-q", "-c", branch, base)
        self.commit(text, "the fix")

    def finish(self, version="V1.25.0-HF1", branch=BRANCH, repo=None, project=None, dry_run=False, with_board=True):
        repo, project = repo or FakeRepo(), project or FakeProject()
        run = hotfix.finish(self.dir, repo, project if with_board else None, board() if with_board else None, V(version), branch, NOW, dry_run)
        return run, repo, project

    def heading(self):
        with open(os.path.join(self.dir, "CHANGELOG.md"), encoding="utf-8") as handle:
            return handle.read().split("\n")[2]


class FinishTests(HotfixRepo):
    def test_the_hotfix_is_finished(self):
        self.start()
        run, repo, project = self.finish()
        self.assertEqual(self.heading(), "## V1.25.0-HF1 — 2026-10-07 11:05 UTC")
        self.assertEqual(self.git("log", "-1", "--format=%s"), "Finalize V1.25.0-HF1")
        head = self.git("rev-parse", "HEAD")
        remote_head = subprocess.run(["git", "rev-parse", BRANCH], cwd=self.remote, capture_output=True, text=True).stdout.strip()
        self.assertEqual(remote_head, head)
        self.assertEqual(repo.created_tags, [("released/V1.25.0-HF1", head)])
        title, body, kind = repo.issues[0]
        self.assertEqual((title, kind), ("Version 1.25.0-HF1", "Version"))
        self.assertIn(f"from the hotfix branch {BRANCH}", body)
        self.assertIn("hotfix of V1.25.0", body)
        self.assertEqual(repo.subs, [(90, 301), (90, 302)])
        self.assertEqual(repo.closed, [90])
        self.assertIn("Tag: `released/V1.25.0-HF1`", repo.comments[0][1])

    def test_the_tickets_go_straight_to_released_with_the_hotfix_version(self):
        self.start()
        _, _, project = self.finish()
        sets = {(item, field): value for item, field, value in project.sets}
        self.assertEqual(sets[("I301", "F-Delivery")], {"singleSelectOptionId": "Delivery-Released"})
        self.assertEqual(sets[("I301", "F-Version")], {"text": "V1.25.0-HF1"})
        self.assertEqual(sets[("I301", "F-Version#")], {"number": float(V("V1.25.0-HF1").number())})
        self.assertEqual(sets[("I301", "F-Build")], {"text": "20261007100000"})
        self.assertNotIn("Delivery-Merged", [v.get("singleSelectOptionId") for v in sets.values()])
        self.assertEqual(sets[("I90", "F-Delivery")], {"singleSelectOptionId": "Delivery-Released"})  # the Version ticket

    def test_a_trial_hotfix_starts_from_the_trial_base_tag_and_tags_under_test(self):
        self.git("tag", "test/released/V1.25.0", "released/V1.25.0")
        self.git("tag", "-d", "released/V1.25.0")
        self.start(base="test/released/V1.25.0")
        repo, project = FakeRepo(), FakeProject()
        hotfix.finish(self.dir, repo, project, board(), V("V1.25.0-HF1"), BRANCH, NOW, False, trial=True)
        self.assertEqual([name for name, _ in repo.created_tags], ["test/released/V1.25.0-HF1"])
        self.assertIn("Tag: `test/released/V1.25.0-HF1`", repo.comments[-1][1])

    def test_a_trial_hotfix_needs_the_trial_base_tag(self):
        self.start()  # the real base tag exists, the trial one does not
        with self.assertRaises(hotfix.HotfixError) as caught:
            hotfix.finish(self.dir, FakeRepo(), FakeProject(), board(), V("V1.25.0-HF1"), BRANCH, NOW, True, trial=True)
        self.assertIn("test/released/V1.25.0", str(caught.exception))

    def test_a_second_hotfix_starts_from_the_first(self):
        self.start()
        self.finish()
        self.git("tag", "released/V1.25.0-HF1")
        self.git("switch", "-q", "-c", "hotfix-v1-25-0-another", "released/V1.25.0-HF1")
        with open(os.path.join(self.dir, "CHANGELOG.md"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("## V1.25.0-HF1", text)  # the first hotfix's finalized heading is part of this branch
        opened = ("## WIP-Version\n### Build 20261007120000 (branch hotfix-v1-25-0-another)\n"
                  "#### #311 — Another fix\n- fixed again.\n\n")
        self.commit(text.replace("## V1.25.0-HF1", opened + "## V1.25.0-HF1", 1), "the second fix")
        run, repo, _ = self.finish("V1.25.0-HF2", "hotfix-v1-25-0-another", repo=FakeRepo(tags=["released/V1.25.0-HF1"]))
        self.assertEqual(repo.created_tags[0][0], "released/V1.25.0-HF2")

    def test_dry_run_changes_nothing(self):
        self.start()
        head = self.git("rev-parse", "HEAD")
        run, repo, project = self.finish(dry_run=True)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual((repo.created_tags, repo.issues, project.sets), ([], [], []))
        self.assertTrue(any("tag the finalizing commit" in line for line in run.log))

    def test_no_board_still_finishes_the_version(self):
        self.start()
        run, repo, _ = self.finish(with_board=False)
        self.assertEqual(len(repo.created_tags), 1)
        self.assertTrue(any("board steps skipped" in line for line in run.log))


class RefusalTests(HotfixRepo):
    def refused(self, text, **kwargs):
        with self.assertRaises(hotfix.HotfixError) as caught:
            self.finish(**kwargs)
        self.assertIn(text, str(caught.exception))
        self.assertEqual(self.git("log", "-1", "--format=%s"), "the fix")  # nothing was committed

    def test_the_hotfix_number_must_be_one_to_nine(self):
        self.start()
        for version in ("V1.25.0", "V1.25.0-HF10"):
            with self.assertRaises(hotfix.HotfixError):
                self.finish(version)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "the fix")

    def test_the_branch_must_be_named_for_the_release(self):
        self.start(branch="hotfix-v1-24-0-fix")
        self.refused("is not named for this release", branch="hotfix-v1-24-0-fix")

    def test_a_marker_is_not_allowed(self):
        self.start(HOTFIX.format(marker=" +s"))
        self.refused("markers are not allowed")

    def test_the_changelog_needs_an_open_version_with_tickets(self):
        self.start(RELEASED + "\na note\n")
        self.refused("no open WIP-Version heading")
        self.git("reset", "-q", "--hard", "released/V1.25.0")
        self.git("switch", "-q", "main")
        self.git("branch", "-q", "-D", BRANCH)
        self.start("# Changelog\n\n## WIP-Version\n### Build 20261007100000 (branch b)\n#### REF 20261007100000 — x\n- y.\n\n" + RELEASED.split("\n", 2)[2])
        self.refused("no ticket entry")

    def test_a_version_that_is_already_finalized_or_tagged(self):
        self.start()
        self.refused("already has the release tag", repo=FakeRepo(tags=["released/V1.25.0-HF1"]))

    def test_the_base_tag_must_exist_and_be_in_the_branch(self):
        self.git("tag", "-d", "released/V1.25.0")
        self.git("switch", "-q", "-c", BRANCH, "main")
        self.commit(HOTFIX.format(marker=""), "the fix")
        self.refused("is not in this clone")
        self.git("tag", "released/V1.25.0", "main~1")  # the tag exists, but the branch started from the tip of main
        self.git("switch", "-q", "main")
        self.git("branch", "-q", "-D", BRANCH)
        self.git("switch", "-q", "-c", BRANCH, "main")  # main is after the tag, so it contains it
        self.commit(HOTFIX.format(marker=""), "the fix")
        self.git("tag", "-f", "released/V1.25.0", "main")  # now the tag is ahead of the branch's parent... but not an ancestor
        self.git("switch", "-q", "main")
        self.commit(RELEASED + "\nanother main commit\n", "main moves again")
        self.git("tag", "-f", "released/V1.25.0", "main")
        self.git("switch", "-q", BRANCH)
        self.refused("does not contain released/V1.25.0")

    def test_the_second_hotfix_needs_the_first_ones_tag(self):
        self.start()
        self.refused("released/V1.25.0-HF1 is not in this clone", version="V1.25.0-HF2")


if __name__ == "__main__":
    unittest.main()
