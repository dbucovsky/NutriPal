import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import preflight  # noqa: E402
import release  # noqa: E402
from github_api import GitHubError  # noqa: E402
from versions import Version  # noqa: E402

NOW = datetime(2026, 10, 7, 9, 30, 0, tzinfo=timezone.utc)
V = Version.parse

LOG_040 = "# Changelog\n\n## V0.4.0 — 2026-10-06 00:47 UTC\n### Build 1 (branch b)\n"
LOG_050 = "# Changelog\n\n## V0.5.0 — 2026-10-06 02:52 UTC\n" + LOG_040.split("\n", 2)[2].replace("Build 1", "Build 20261006025104")
LOG_031 = "## V0.3.1 — 2026-10-06 00:04 UTC\n### Build 20261006000318 (branch b)\n"
LOG = LOG_050.rstrip("\n") + "\n\n" + LOG_031


def node(number, delivery, version, kind="Task"):
    return {"id": f"I{number}", "content": {"number": number, "issueType": {"name": kind} if kind else None},
            "delivery": {"name": delivery} if delivery else None, "version": {"text": version} if version else None}


class FakeProject:
    repo = "owner/repo"

    def __init__(self, nodes, per_page=100):
        self.nodes, self.per_page, self.sets = nodes, per_page, []

    def graphql(self, query, variables=None):
        if "pageInfo" in query:
            start = int(variables["after"] or 0)
            end = start + self.per_page
            return {"node": {"items": {"pageInfo": {"hasNextPage": end < len(self.nodes), "endCursor": str(end)},
                                       "nodes": self.nodes[start:end]}}}
        number = variables["num"]
        return {"repository": {"issue": {"id": f"N{number}", "title": "t", "projectItems": {"nodes": [
            {"id": f"I{number}", "project": {"id": "P7"}, "status": None, "delivery": None, "version": None, "build": None,
             "number": None, "attention": None}]}}}}

    def set_project_field(self, project_id, item_id, field_id, value):
        self.sets.append((item_id, field_id, value["singleSelectOptionId"]))


class FakeRepo:
    repo = "owner/repo"

    def __init__(self, tickets, tags=()):
        self.tickets, self.tags, self.created, self.comments = tickets, set(tags), [], []

    def repo_path(self, path):
        return path

    def request(self, method, path, body=None):
        if "/git/ref/tags/" in path:
            if path.split("/git/ref/tags/")[1] in self.tags:
                return {"ref": "x"}
            raise GitHubError(404, "Not Found")
        return self.tickets

    def create_tag(self, name, sha):
        self.created.append((name, sha))

    def comment(self, number, body):
        self.comments.append((number, body))


def board():
    fields = {name: {"id": f"F-{name}", "type": kind, "options": {v: f"{name}-{v}" for v in (values or [])}}
              for name, (kind, values) in preflight.REQUIRED_FIELDS.items()}
    return preflight.Board("P7", 7, "Governance", fields)


TICKETS = [{"title": "Version 0.5.0", "state": "closed", "number": 31}, {"title": "Version 0.4.0", "state": "open", "number": 30}]


class Folder(unittest.TestCase):
    def folder(self, text=LOG):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, "CHANGELOG.md"), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        self.patch = (release.finalize_commit, release.finalize_commit)
        release.finalize_commit = lambda root, version: "a" * 40
        self.addCleanup(lambda: setattr(release, "finalize_commit", self.patch[0]))
        return tmp.name


class ReleaseTests(Folder):
    def run_release(self, nodes, version=None, tickets=TICKETS, tags=(), dry_run=False, root_text=LOG):
        repo, project = FakeRepo(tickets, tags), FakeProject(nodes)
        run = release.release(self.folder(root_text), repo, project, board(), version, NOW, dry_run)
        return run, repo, project

    def test_releases_the_latest_version_by_default(self):
        run, repo, project = self.run_release([node(1, "Merged", "V0.5.0")])
        self.assertEqual(repo.created, [("released/V0.5.0", "a" * 40)])
        self.assertEqual(repo.comments, [(31, "Released 2026-10-07 09:30 UTC. Tag: `released/V0.5.0`.")])
        self.assertIn(("I31", "F-Delivery", "Delivery-Released"), project.sets)  # the Version ticket
        self.assertIn(("I1", "F-Delivery", "Delivery-Released"), project.sets)

    def test_merged_and_implemented_tickets_at_or_below_the_version_are_released(self):
        _, _, project = self.run_release([node(1, "Merged", "V0.5.0"), node(2, "Implemented", "V0.3.1"), node(3, "Merged", "V0.1.0")])
        released = {item for item, _, _ in project.sets}
        self.assertTrue({"I1", "I2", "I3"} <= released)

    def test_newer_versions_pushed_work_and_other_tickets_are_left_alone(self):
        nodes = [node(1, "Merged", "V0.6.0"), node(2, "Pushed", "V0.5.0"), node(3, "Released", "V0.4.0"), node(4, None, "V0.4.0"),
                 node(5, "Merged", "V0.4.0", kind="Version"), node(6, "Merged", "V0.4.0", kind="Alert"), node(7, "Merged", "soon"),
                 node(8, "Dropped", "V0.4.0")]
        _, _, project = self.run_release(nodes)
        self.assertEqual({item for item, _, _ in project.sets}, {"I31"})

    def test_an_earlier_version_can_be_released(self):
        tickets = [{"title": "Version 0.4.0", "state": "closed", "number": 30}]
        run, repo, project = self.run_release([node(1, "Merged", "V0.5.0"), node(2, "Merged", "V0.4.0")], V("V0.4.0"), tickets)
        self.assertEqual(repo.created[0][0], "released/V0.4.0")
        self.assertEqual({item for item, _, _ in project.sets}, {"I30", "I2"})  # V0.5.0 work is not in it

    def test_a_version_that_is_not_finalized_cannot_be_released(self):
        with self.assertRaises(release.ReleaseError) as caught:
            self.run_release([], V("V0.9.0"))
        self.assertIn("not a finalized version", str(caught.exception))

    def test_a_trial_makes_its_tag_under_test_and_leaves_the_real_one_alone(self):
        repo, project = FakeRepo(TICKETS, ["released/V0.5.0"]), FakeProject([node(1, "Merged", "V0.5.0")])
        run = release.release(self.folder(LOG), repo, project, board(), None, NOW, False, trial=True)
        self.assertEqual([name for name, _ in repo.created], ["test/released/V0.5.0"])  # a real tag of the version does not block it
        self.assertIn("Tag: `test/released/V0.5.0`", repo.comments[0][1])

    def test_a_run_without_the_trial_input_makes_the_real_tag_even_for_a_trial_version(self):
        repo, project = FakeRepo(TICKETS, ["test/released/V0.5.0"]), FakeProject([node(1, "Merged", "V0.5.0")])
        release.release(self.folder(LOG), repo, project, board(), None, NOW, False)
        self.assertEqual([name for name, _ in repo.created], ["released/V0.5.0"])

    def test_the_trial_input_is_read_from_the_environment(self):
        for value, expected in (("true", True), ("True", True), ("false", False), ("", False), ("1", False)):
            self.assertEqual(release.is_trial({"TRIAL": value}), expected, value)
        self.assertFalse(release.is_trial({}))

    def test_a_version_has_at_most_one_release_tag(self):
        with self.assertRaises(release.ReleaseError) as caught:
            self.run_release([], tags=["released/V0.5.0"])
        self.assertIn("already has the release tag", str(caught.exception))

    def test_the_version_needs_a_finalized_version_ticket(self):
        for tickets in ([], [{"title": "Version 0.5.0", "state": "open", "number": 31}]):
            with self.assertRaises(release.ReleaseError):
                self.run_release([], tickets=tickets)

    def test_no_changelog_version_and_no_finalize_commit(self):
        with self.assertRaises(release.ReleaseError):
            self.run_release([], root_text="# Changelog\n")
        folder = self.folder()
        release.finalize_commit = lambda root, version: None
        with self.assertRaises(release.ReleaseError):
            release.release(folder, FakeRepo(TICKETS), FakeProject([]), board(), None, NOW)

    def test_dry_run_changes_nothing(self):
        run, repo, project = self.run_release([node(1, "Merged", "V0.5.0")], dry_run=True)
        self.assertEqual((repo.created, repo.comments, project.sets), ([], [], []))
        self.assertTrue(any("tag aaaaaaa" in line for line in run.log))

    def test_no_board_still_tags_and_comments(self):
        repo = FakeRepo(TICKETS)
        run = release.release(self.folder(), repo, None, None, None, NOW)
        self.assertEqual(len(repo.created), 1)
        self.assertTrue(any("board steps skipped" in line for line in run.log))
        self.assertEqual(len(repo.comments), 1)

    def test_every_page_of_the_board_is_read(self):
        nodes = [node(n, "ToDo", "V0.5.0") for n in range(1, 230)] + [node(500, "Merged", "V0.5.0")]
        found = release.releasable_tickets(FakeProject(nodes), board(), V("V0.5.0"))
        self.assertEqual([number for number, _ in found], [500])


class FinalizeCommitTests(unittest.TestCase):
    def test_it_is_the_commit_where_the_heading_first_appears(self):
        with tempfile.TemporaryDirectory() as folder:
            def git(*args):
                return subprocess.run(["git", *args], cwd=folder, capture_output=True, text=True, encoding="utf-8").stdout.strip()

            def write(text):
                with open(os.path.join(folder, "CHANGELOG.md"), "w", encoding="utf-8", newline="") as handle:
                    handle.write(text)
                git("add", "-A")
                git("commit", "-q", "-m", "x")
                return git("rev-parse", "HEAD")

            git("init", "-q", "-b", "main")
            git("config", "user.name", "T")
            git("config", "user.email", "t@example.com")
            write("# Changelog\n\n## WIP-Version\n### Build 1 (branch b)\n")
            finalized = write("# Changelog\n\n## V0.5.0 — 2026-10-06 02:52 UTC\n### Build 1 (branch b)\n")
            write("# Changelog\n\n## V0.5.0 — 2026-10-06 02:52 UTC\n### Build 1 (branch b)\n#### #1 — x\n")
            write("# Changelog\n\n## WIP-Version\n### Build 2 (branch c)\n\n## V0.5.0 — 2026-10-06 02:52 UTC\n### Build 1 (branch b)\n")
            self.assertEqual(release.finalize_commit(folder, V("V0.5.0")), finalized)
            self.assertIsNone(release.finalize_commit(folder, V("V0.6.0")))


if __name__ == "__main__":
    unittest.main()
