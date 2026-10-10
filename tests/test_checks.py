import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import advisory  # noqa: E402
import alerts  # noqa: E402
import bypass  # noqa: E402
import changelog  # noqa: E402
import checks  # noqa: E402
import preflight  # noqa: E402
from versions import Version  # noqa: E402

NOW = datetime(2026, 10, 6, 10, 0, 0, tzinfo=timezone.utc)

BASE_LOG = """# Changelog

## V0.2.0 — 2026-10-05 21:24 UTC
### Build 20261005211638 (branch other)
#### #4 — Earlier work
- done.
"""

ENTRY = """# Changelog

## WIP-Version
### Build 20261006090000 (branch feature)
#### #201 — Add CSV export
- export: added.

""" + BASE_LOG.split("\n", 2)[2]


class GitRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Tester")
        self.git("config", "user.email", "t@example.com")
        self.commit({"CHANGELOG.md": BASE_LOG, "a.txt": "a\n", "b.txt": "b\n"}, "start")

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.dir, capture_output=True, text=True, encoding="utf-8")
        return result.returncode, result.stdout.strip()

    def commit(self, files, message):
        for name, content in files.items():
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")[1]

    def head(self):
        return self.git("rev-parse", "HEAD")[1]

    def merge(self, branch, message="Merge", resolve=None):
        """Merge with --no-ff; `resolve` is a dict of files to write when git stops on a conflict or to amend the merge."""
        code, _ = self.git("merge", "--no-ff", "--no-commit", branch)
        for name, content in (resolve or {}).items():
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.head()


class MergeKindTests(GitRepo):
    def test_a_synced_branch_merges_identically(self):
        self.git("switch", "-q", "-c", "feature")
        self.commit({"a.txt": "feature\n"}, "feature work")
        self.git("switch", "-q", "main")
        self.commit({"b.txt": "main\n"}, "main moves")
        self.git("switch", "-q", "feature")
        self.merge("main")  # the sync
        self.git("switch", "-q", "main")
        sha = self.merge("feature")
        self.assertIsNone(checks.merge_kind(self.dir, sha))

    def test_an_unsynced_branch_is_not_identical(self):
        self.git("switch", "-q", "-c", "feature")
        self.commit({"a.txt": "feature\n"}, "feature work")
        self.git("switch", "-q", "main")
        self.commit({"b.txt": "main\n"}, "main moves")
        sha = self.merge("feature")
        self.assertEqual(checks.merge_kind(self.dir, sha), checks.NOT_IDENTICAL)

    def test_a_conflict_resolved_by_hand(self):
        self.git("switch", "-q", "-c", "feature")
        self.commit({"a.txt": "feature\n"}, "feature work")
        self.git("switch", "-q", "main")
        self.commit({"a.txt": "main\n"}, "main edits the same line")
        sha = self.merge("feature", resolve={"a.txt": "both\n"})
        self.assertEqual(checks.merge_kind(self.dir, sha), checks.MANUAL_RESOLUTION)

    def test_extra_edits_in_a_clean_merge_are_manual(self):
        self.git("switch", "-q", "-c", "feature")
        self.commit({"a.txt": "feature\n"}, "feature work")
        self.git("switch", "-q", "main")
        self.commit({"b.txt": "main\n"}, "main moves")
        sha = self.merge("feature", resolve={"c.txt": "sneaked in\n"})
        self.assertEqual(checks.merge_kind(self.dir, sha), checks.MANUAL_RESOLUTION)

    def test_behind_and_manual_merges(self):
        self.git("switch", "-q", "-c", "feature")
        self.commit({"a.txt": "feature\n"}, "feature work")
        self.git("switch", "-q", "main")
        self.commit({"a.txt": "main\n"}, "main edits the same line")
        self.commit({"b.txt": "main\n"}, "main again")
        self.git("switch", "-q", "feature")
        self.assertEqual(checks.behind(self.dir, "main", "feature"), 2)
        self.merge("main", resolve={"a.txt": "both\n"})
        self.assertEqual(checks.behind(self.dir, "main", "feature"), 0)
        self.assertEqual(len(checks.manual_merges(self.dir, "main", "feature")), 1)


class FlaggedTests(GitRepo):
    def setUp(self):
        super().setUp()
        self.before = self.head()

    def test_a_direct_commit_is_flagged(self):
        sha = self.commit({"a.txt": "x\n"}, "quick fix")
        found = checks.flagged_commits(self.dir, self.before, sha, lambda s: False)
        self.assertEqual([(f.kind, f.subject, f.author) for f in found], [(checks.DIRECT_PUSH, "quick fix", "Tester")])

    def test_a_clean_pull_request_merge_is_not_flagged(self):
        self.git("switch", "-q", "-c", "feature")
        self.commit({"a.txt": "feature\n"}, "feature work")
        self.git("switch", "-q", "main")
        sha = self.merge("feature")
        self.assertEqual(checks.flagged_commits(self.dir, self.before, sha, lambda s: True), [])

    def test_a_merge_with_a_pull_request_but_not_identical_is_flagged(self):
        self.git("switch", "-q", "-c", "feature")
        self.commit({"a.txt": "feature\n"}, "feature work")
        self.git("switch", "-q", "main")
        self.commit({"b.txt": "main\n"}, "main moves")
        self.before = self.head()
        sha = self.merge("feature")
        found = checks.flagged_commits(self.dir, self.before, sha, lambda s: True)
        self.assertEqual([f.kind for f in found], [checks.NOT_IDENTICAL])

    def test_the_automations_version_commit_is_exempt(self):
        sha = self.commit({"CHANGELOG.md": BASE_LOG.replace("0.2.0", "0.3.0")}, "Finalize V0.3.0")
        self.assertEqual(checks.flagged_commits(self.dir, self.before, sha, lambda s: False), [])

    def test_a_finalize_commit_that_touches_other_files_is_not_exempt(self):
        sha = self.commit({"CHANGELOG.md": BASE_LOG + "\n", "a.txt": "x\n"}, "Finalize V0.3.0")
        self.assertEqual(len(checks.flagged_commits(self.dir, self.before, sha, lambda s: False)), 1)

    def test_several_commits_are_all_listed(self):
        self.commit({"a.txt": "1\n"}, "one")
        sha = self.commit({"a.txt": "2\n"}, "two")
        found = checks.flagged_commits(self.dir, self.before, sha, lambda s: False)
        self.assertEqual([f.subject for f in found], ["two", "one"])


class MissingEntriesTests(GitRepo):
    def setUp(self):
        super().setUp()
        self.before = self.head()

    def test_code_without_entries(self):
        sha = self.commit({"a.txt": "x\n"}, "no entry")
        self.assertTrue(checks.missing_entries(self.dir, self.before, sha))

    def test_code_with_a_new_build_entry(self):
        sha = self.commit({"a.txt": "x\n", "CHANGELOG.md": ENTRY}, "with entry")
        self.assertFalse(checks.missing_entries(self.dir, self.before, sha))

    def test_only_the_changelog_changed(self):
        sha = self.commit({"CHANGELOG.md": ENTRY}, "entries only")
        self.assertFalse(checks.missing_entries(self.dir, self.before, sha))

    def test_an_open_heading_left_over_from_before_does_not_count(self):
        self.commit({"CHANGELOG.md": ENTRY}, "entries")
        before = self.head()
        sha = self.commit({"a.txt": "y\n"}, "more code, no new entry")
        self.assertTrue(checks.missing_entries(self.dir, before, sha))

    def test_the_first_push_is_skipped(self):
        self.assertFalse(checks.missing_entries(self.dir, checks.ZEROS, self.head()))


class FakeRepoClient:
    repo = "owner/repo"

    def __init__(self, planned=(), types=None, prs=True):
        self.planned, self.types, self.prs = list(planned), types or {}, prs
        self.created, self.comments_posted, self.existing_comments = [], [], []

    def repo_path(self, path):
        return f"/repos/{self.repo}{path}"

    def issue_type(self, number):
        return self.types.get(number)

    def request(self, method, path, body=None):
        if "/pulls" in path:
            return [{"number": 1}] if self.prs else []
        if "type=Version" in path:
            return self.planned
        if "/comments" in path:
            return self.existing_comments
        return {}

    def create_issue(self, title, body, issue_type=None, labels=(), assignees=()):
        self.created.append((title, body, issue_type, list(labels), list(assignees)))
        return {"number": 90 + len(self.created), "node_id": f"N{len(self.created)}"}

    def comment(self, number, body):
        self.comments_posted.append((number, body))


class FakeProjectClient:
    repo = "owner/repo"

    def __init__(self):
        self.sets = []

    def add_to_project(self, project_id, content_id):
        return f"I-{content_id}"

    def set_project_field(self, project_id, item_id, field_id, value):
        self.sets.append((item_id, field_id, value))


def board():
    fields = {name: {"id": f"F-{name}", "type": kind, "options": {v: f"{name}-{v}" for v in (values or [])}}
              for name, (kind, values) in preflight.REQUIRED_FIELDS.items()}
    return preflight.Board("P7", 7, "Governance", fields)


class AlertTextTests(unittest.TestCase):
    def test_bypass_alert(self):
        findings = [checks.Finding("abc1234def", checks.NOT_IDENTICAL, "Merge pull request #3", "Sam")]
        title, body = alerts.bypass_alert(findings, False, Version(2, 4, 1), "f" * 40, "2026-10-05 16:40")
        self.assertEqual(title, "Merge to main not identical to its branch (V2.4.1)")
        self.assertIn("`abc1234` Merge pull request #3 (not-identical, by Sam)", body)
        self.assertIn("**To do.**", body)

    def test_direct_push_outranks_the_others_in_the_title(self):
        findings = [checks.Finding("a" * 40, checks.NOT_IDENTICAL, "m", "S"), checks.Finding("b" * 40, checks.DIRECT_PUSH, "d", "S")]
        self.assertTrue(alerts.bypass_alert(findings, False, Version(1, 0, 1), "c" * 40, "t")[0].startswith("Direct push to main"))

    def test_no_entries_alert_mentions_the_created_version(self):
        title, body = alerts.bypass_alert([], True, Version(0, 2, 1), "c" * 40, "t")
        self.assertTrue(title.startswith("Merge to main without changelog entries"))
        self.assertIn("created the version", body)

    def test_stale_alert_text(self):
        title, body = alerts.stale_alert(Version(2, 4, 1), [(130, "Version 2.4.0")])
        self.assertEqual(title, "Stale planned Version tickets after V2.4.1")
        self.assertIn("#130 Version 2.4.0", body)

    def test_changelog_error_alert(self):
        title, body = alerts.changelog_error_alert("line 3: unexpected text", "d" * 40, "t")
        self.assertIn("no version finalized", title)
        self.assertIn("line 3: unexpected text", body)

    def test_stale_planned_finds_lower_numbers_only(self):
        planned = [{"title": "Version 2.4.0", "number": 130}, {"title": "Version 2.4.2", "number": 131},
                   {"title": "Version 2.3.9", "number": 120}, {"title": "Something else", "number": 5}]
        found = alerts.stale_planned(FakeRepoClient(planned), Version(2, 4, 1))
        self.assertEqual(found, [(120, "Version 2.3.9"), (130, "Version 2.4.0")])
        self.assertEqual(alerts.stale_planned(FakeRepoClient(planned), Version(2, 4, 1, 1)), [])


class AutoRefTests(unittest.TestCase):
    def test_goes_in_a_new_build_at_the_top_of_the_open_version(self):
        text = alerts.add_autoref(ENTRY, "20261006100000", 187, "a direct push.", False)
        wip = changelog.open_section(changelog.parse(text))
        self.assertEqual([b.stamp for b in wip.builds], ["20261006100000", "20261006090000"])
        block = wip.builds[0].blocks[0]
        self.assertEqual((block.kind, block.number, block.token), ("autoref", 187, "20261006100000"))
        self.assertIn("Issue #187 opened automatically", block.body[0])

    def test_creates_the_version_when_there_is_none(self):
        text = alerts.add_autoref(BASE_LOG, "20261006100000", 187, "no entries.", True)
        sections = changelog.parse(text)
        self.assertEqual([s.kind for s in sections], ["wip", "final"])
        self.assertIn("created automatically", sections[0].blocks()[0].body[0])
        self.assertTrue(text.startswith("# Changelog\n\n## WIP-Version\n"))


class HandlePushTests(GitRepo):
    def setUp(self):
        super().setUp()
        self.before = self.head()

    def test_a_direct_push_raises_one_alert_and_one_autoref(self):
        sha = self.commit({"a.txt": "x\n"}, "quick fix")
        repo, project = FakeRepoClient(prs=False), FakeProjectClient()
        run = bypass.handle_push(self.dir, repo, project, board(), self.before, sha, "sam", NOW, push=False)
        title, body, kind, labels, assignees = repo.created[0]
        self.assertEqual((kind, labels, assignees), ("Alert", ["process"], ["sam"]))
        self.assertTrue(title.startswith("Direct push to main (V0.2.1)"))
        fields = {field: value for _, field, value in project.sets}
        self.assertEqual(fields["F-Priority"], {"singleSelectOptionId": "Priority-Critical"})
        self.assertEqual(fields["F-Status"], {"singleSelectOptionId": "Status-ToDo"})
        with open(os.path.join(self.dir, "CHANGELOG.md"), encoding="utf-8") as handle:
            text = handle.read()
        wip = changelog.open_section(changelog.parse(text))
        self.assertEqual(wip.blocks()[0].kind, "autoref")
        self.assertEqual(self.git("log", "-1", "--format=%s")[1], "Flag bypass (Alert #91)")
        self.assertTrue(run.log)

    def test_a_clean_push_does_nothing(self):
        sha = self.commit({"a.txt": "x\n", "CHANGELOG.md": ENTRY}, "with entry")
        repo = FakeRepoClient(prs=True)
        run = bypass.handle_push(self.dir, repo, None, None, self.before, sha, "sam", NOW, push=False)
        self.assertEqual(repo.created, [])
        self.assertEqual(run.log, ["no bypass detected"])

    def test_dry_run_changes_nothing(self):
        sha = self.commit({"a.txt": "x\n"}, "quick fix")
        repo = FakeRepoClient(prs=False)
        head = self.head()
        run = bypass.handle_push(self.dir, repo, None, None, self.before, sha, "sam", NOW, dry_run=True)
        self.assertEqual(repo.created, [])
        self.assertEqual(self.head(), head)
        self.assertTrue(any("AUTO-REF" in line for line in run.log))

    def test_a_malformed_changelog_raises_a_changelog_alert(self):
        sha = self.commit({"CHANGELOG.md": ENTRY.replace("## WIP-Version", "## WIP-Version soon")}, "bad heading")
        repo = FakeRepoClient(prs=True)
        run = bypass.handle_push(self.dir, repo, None, None, self.before, sha, "sam", NOW, push=False)
        self.assertIn("no version finalized", repo.created[0][0])
        self.assertIn("no version can be finalized", run.log[-1])

    def test_stale_planned_versions_raise_an_unassigned_alert(self):
        repo = FakeRepoClient([{"title": "Version 0.1.5", "number": 12}])
        bypass.raise_stale_alert(repo, None, None, Version(0, 2, 1))
        title, body, kind, labels, assignees = repo.created[0]
        self.assertEqual((title, kind, assignees), ("Stale planned Version tickets after V0.2.1", "Alert", []))
        quiet = FakeRepoClient([])
        bypass.raise_stale_alert(quiet, None, None, Version(0, 2, 1))
        self.assertEqual(quiet.created, [])


class AdvisoryTests(GitRepo):
    def test_behind_fails_and_comments_once(self):
        self.git("switch", "-q", "-c", "feature")
        self.commit({"a.txt": "feature\n"}, "feature work")
        self.git("switch", "-q", "main")
        self.commit({"b.txt": "main\n"}, "main moves")
        self.git("switch", "-q", "feature")
        repo = FakeRepoClient()
        passed, text = advisory.run_check(self.dir, repo, 7, base="main", head="feature")
        self.assertFalse(passed)
        self.assertIn("1 commit(s) behind `main`", text)
        self.assertEqual(len(repo.comments_posted), 1)
        repo.existing_comments = [{"body": advisory.MARKER + " earlier"}]
        advisory.run_check(self.dir, repo, 7, base="main", head="feature")
        self.assertEqual(len(repo.comments_posted), 1)

    def test_up_to_date_passes_silently(self):
        self.git("switch", "-q", "-c", "feature")
        self.commit({"a.txt": "feature\n"}, "feature work")
        repo = FakeRepoClient()
        passed, text = advisory.run_check(self.dir, repo, 7, base="main", head="feature")
        self.assertTrue(passed)
        self.assertIsNone(text)
        self.assertEqual(repo.comments_posted, [])

    def test_a_manual_merge_is_listed_but_does_not_fail(self):
        self.git("switch", "-q", "-c", "feature")
        self.commit({"a.txt": "feature\n"}, "feature work")
        self.git("switch", "-q", "main")
        self.commit({"a.txt": "main\n"}, "main edits the same line")
        self.git("switch", "-q", "feature")
        self.merge("main", resolve={"a.txt": "both\n"})
        passed, text = advisory.run_check(self.dir, FakeRepoClient(), None, base="main", head="feature")
        self.assertTrue(passed)
        self.assertIn("manual conflict resolution", text)


if __name__ == "__main__":
    unittest.main()
