import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import preflight  # noqa: E402
import retire  # noqa: E402
from github_api import GitHubError  # noqa: E402

MAIN = "# Changelog\n\n## V0.4.0 — 2026-10-06 00:47 UTC\n### Build 20261006004523 (branch old)\n#### #28 — Earlier\n- done.\n"
WORK = ("# Changelog\n\n## WIP-Version\n### Build 20261006090000 (branch {branch})\n#### #201 — Work\n- w.\n#### #205 — More\n- m.\n\n"
        + MAIN.split("\n", 2)[2])


class FakeRepo:
    repo = "owner/repo"

    def __init__(self, tags=(), pulls=()):
        self.tags, self.pulls = set(tags), list(pulls)
        self.created, self.deleted = [], []

    def repo_path(self, path):
        return path

    def request(self, method, path, body=None):
        if "/git/ref/tags/" in path:
            if path.split("/git/ref/tags/")[1] in self.tags:
                return {"ref": "x"}
            raise GitHubError(404, "Not Found")
        if "/pulls" in path:
            return self.pulls
        raise AssertionError(path)

    def create_tag(self, name, sha):
        self.created.append((name, sha))

    def delete_ref(self, ref):
        self.deleted.append(ref)


class FakeProject:
    repo = "owner/repo"

    def __init__(self, delivery="Pushed"):
        self.delivery, self.sets = delivery, []

    def graphql(self, query, variables=None):
        number = variables["num"]
        return {"repository": {"issue": {"id": f"N{number}", "title": "t", "projectItems": {"nodes": [
            {"id": f"I{number}", "project": {"id": "P7"}, "status": None, "delivery": {"name": self.delivery},
             "version": None, "build": None, "number": None, "attention": None}]}}}}

    def set_project_field(self, project_id, item_id, field_id, value):
        self.sets.append((item_id, field_id, value["singleSelectOptionId"]))


def board():
    fields = {name: {"id": f"F-{name}", "type": kind, "options": {v: f"{name}-{v}" for v in (values or [])}}
              for name, (kind, values) in preflight.REQUIRED_FIELDS.items()}
    return preflight.Board("P7", 7, "Governance", fields)


class Repo(unittest.TestCase):
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
        self.commit(MAIN, "start")
        self.git("push", "-q", "-u", "origin", "main")

    def git(self, *args, env=None):
        result = subprocess.run(["git", *args], cwd=self.dir, capture_output=True, text=True, encoding="utf-8",
                                env=dict(os.environ, **(env or {})))
        return result.stdout.strip()

    def commit(self, text, message, date="2026-10-05T23:30:00-04:00"):
        with open(os.path.join(self.dir, "CHANGELOG.md"), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, env={"GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date})
        return self.git("rev-parse", "HEAD")

    def branch(self, name, merged=False, base="main", text=None):
        self.git("switch", "-q", "-c", name, base)
        sha = self.commit(text or WORK.format(branch=name), f"work on {name}")
        self.git("push", "-q", "-u", "origin", name)
        if merged:
            self.git("switch", "-q", "main")
            self.git("merge", "-q", "--no-ff", "-m", f"merge {name}", name)
            self.git("push", "-q", "origin", "main")
        self.git("switch", "-q", "main")
        return sha

    def retire(self, branch, outcome, confirm=None, comment="", repo=None, project=None, dry_run=False):
        repo, project = repo or FakeRepo(), project or FakeProject()
        run = retire.retire(self.dir, repo, project, board(), branch, outcome, branch if confirm is None else confirm, comment, dry_run)
        return run, repo, project


class RetireTests(Repo):
    def test_a_merged_branch_is_archived_with_the_utc_date_of_its_last_commit(self):
        sha = self.branch("csv-export", merged=True)
        run, repo, _ = self.retire("csv-export", "archived")
        self.assertEqual(repo.created, [("archived/2026-10-06_csv-export", sha)])  # 23:30 at -04:00 is the 6th in UTC
        self.assertEqual(repo.deleted, ["heads/csv-export"])
        self.assertTrue(run.log[0].startswith("tag") and run.log[1].startswith("delete"))  # tag first, delete second

    def test_a_trial_tags_under_test_and_a_real_run_does_not(self):
        sha = self.branch("dummy-retire-test")
        repo = FakeRepo()
        retire.retire(self.dir, repo, FakeProject(), board(), "dummy-retire-test", "abandoned", "dummy-retire-test", "dummy-test", False, True)
        self.assertEqual(repo.created, [("test/abandoned/2026-10-06_dummy-retire-test_dummy-test", sha)])
        self.assertEqual(retire.tag_for("archived", "x", __import__("datetime").datetime(2026, 10, 6)), "archived/2026-10-06_x")

    def test_a_finished_trial_hotfix_is_deleted_without_a_tag_too(self):
        self.branch("hotfix-v1-25-0-fix-sensor", text=WORK.format(branch="hotfix"))
        self.git("tag", "test/released/V1.25.0-HF1", "origin/hotfix-v1-25-0-fix-sensor")
        _, repo, _ = self.retire("hotfix-v1-25-0-fix-sensor", "archived")
        self.assertEqual((repo.created, repo.deleted), ([], ["heads/hotfix-v1-25-0-fix-sensor"]))

    def test_a_comment_is_added_to_the_tag(self):
        self.branch("old-idea")
        _, repo, _ = self.retire("old-idea", "suspended", comment="waiting-for-hardware")
        self.assertEqual(repo.created[0][0], "suspended/2026-10-06_old-idea_waiting-for-hardware")

    def test_an_abandoned_branch_drops_its_tickets(self):
        self.branch("dead-end")
        _, repo, project = self.retire("dead-end", "abandoned", comment="superseded")
        self.assertEqual(repo.created[0][0], "abandoned/2026-10-06_dead-end_superseded")
        self.assertEqual(sorted(item for item, _, _ in project.sets), ["I201", "I205"])
        self.assertEqual({option for _, _, option in project.sets}, {"Delivery-Dropped"})

    def test_a_dropped_ticket_is_left_alone(self):
        self.branch("dead-end")
        _, _, project = self.retire("dead-end", "abandoned", project=FakeProject("Dropped"))
        self.assertEqual(project.sets, [])

    def test_a_suspended_branch_keeps_its_tickets(self):
        self.branch("later")
        _, _, project = self.retire("later", "suspended")
        self.assertEqual(project.sets, [])

    def test_a_finished_hotfix_is_deleted_without_a_retirement_tag(self):
        self.branch("hotfix-v1-25-0-fix-sensor", text=WORK.format(branch="hotfix"))
        self.git("tag", "released/V1.25.0-HF1", "origin/hotfix-v1-25-0-fix-sensor")
        run, repo, _ = self.retire("hotfix-v1-25-0-fix-sensor", "archived")
        self.assertEqual(repo.created, [])
        self.assertEqual(repo.deleted, ["heads/hotfix-v1-25-0-fix-sensor"])
        self.assertTrue(any("finished hotfix" in line for line in run.log))

    def test_dry_run_changes_nothing(self):
        self.branch("dead-end")
        run, repo, project = self.retire("dead-end", "abandoned", dry_run=True)
        self.assertEqual((repo.created, repo.deleted, project.sets), ([], [], []))
        self.assertTrue(any("tag " in line for line in run.log))

    def test_no_board_still_tags_and_deletes(self):
        self.branch("dead-end")
        repo = FakeRepo()
        run = retire.retire(self.dir, repo, None, None, "dead-end", "abandoned", "dead-end")
        self.assertEqual((len(repo.created), len(repo.deleted)), (1, 1))
        self.assertTrue(any("board steps skipped" in line for line in run.log))


class RefusalTests(Repo):
    def refused(self, text, *args, **kwargs):
        with self.assertRaises(retire.RetireError) as caught:
            self.retire(*args, **kwargs)
        self.assertIn(text, str(caught.exception))

    def test_main_is_never_retired(self):
        self.refused("main is never retired", "main", "archived")

    def test_the_confirmation_must_be_the_branch_name(self):
        self.branch("csv-export", merged=True)
        self.refused("typed again", "csv-export", "archived", confirm="csv")

    def test_the_outcome_must_be_one_of_the_three(self):
        self.refused("outcome must be one of", "csv-export", "dropped")

    def test_the_branch_must_be_on_the_remote(self):
        self.refused("is not on the remote", "ghost", "abandoned")

    def test_an_archived_branch_must_be_merged(self):
        self.branch("not-merged")
        self.refused("must be fully merged", "not-merged", "archived")

    def test_a_branch_that_is_not_a_finished_hotfix_is_not_archived_for_free(self):
        self.branch("hotfix-v1-25-0-unfinished", text=WORK.format(branch="hotfix"))
        self.refused("must be fully merged", "hotfix-v1-25-0-unfinished", "archived")

    def test_a_branch_with_an_open_pull_request_is_not_suspended_or_abandoned(self):
        self.branch("open-pr")
        for outcome in ("suspended", "abandoned"):
            self.refused("open pull request", "open-pr", outcome, repo=FakeRepo(pulls=[{"number": 5}]))

    def test_a_tag_that_exists_is_refused(self):
        self.branch("csv-export", merged=True)
        self.refused("already exists", "csv-export", "archived", repo=FakeRepo(tags=["archived/2026-10-06_csv-export"]))

    def test_the_tag_comment_must_be_kebab_case(self):
        self.branch("later")
        self.refused("kebab-case", "later", "suspended", comment="Waiting For It")

    def test_nothing_is_done_when_refused(self):
        self.branch("not-merged")
        repo = FakeRepo()
        with self.assertRaises(retire.RetireError):
            self.retire("not-merged", "archived", repo=repo)
        self.assertEqual((repo.created, repo.deleted), ([], []))


if __name__ == "__main__":
    unittest.main()
