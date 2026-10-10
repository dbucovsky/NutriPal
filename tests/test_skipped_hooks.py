import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import changelog  # noqa: E402
import checks  # noqa: E402
import skipped_hooks  # noqa: E402

MAIN = """# Changelog

## V0.4.0 — 2026-10-06 00:47 UTC
### Build 20261006004523 (branch old-work)
#### #28 — Earlier work
- done.
"""

SKIPPED = """# Changelog

## WIP-Version
### WIP-Build
#### #201 — Add CSV export
- export: added.
#### #205 — Write the guide
- guide: written.

""" + MAIN.split("\n", 2)[2]

STAMPED = SKIPPED.replace("### WIP-Build", "### Build 20261006090000 (branch feature)")


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
        self.git("switch", "-q", "-c", "feature")

    def git(self, *args, env=None):
        full = dict(os.environ, **(env or {}))
        result = subprocess.run(["git", *args], cwd=self.dir, capture_output=True, text=True, encoding="utf-8", env=full)
        return result.stdout.strip()

    def commit(self, text, message, date="2026-10-06T09:00:00+00:00"):
        with open(os.path.join(self.dir, "CHANGELOG.md"), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, env={"GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date})
        return self.git("rev-parse", "HEAD")

    def changelog(self):
        with open(os.path.join(self.dir, "CHANGELOG.md"), encoding="utf-8") as handle:
            return handle.read()


class RepairTests(Repo):
    def test_a_skipped_hook_commit_gets_its_heading_note_and_commit(self):
        sha = self.commit(SKIPPED, "work, hooks skipped")
        run = skipped_hooks.repair(self.dir, checks.ZEROS, sha, "feature", push=False)
        text = self.changelog()
        self.assertNotIn("### WIP-Build", text)
        self.assertIn(f"### Build 20261006090000 (branch feature, commit {sha[:7]})", text)
        self.assertEqual(self.git("log", "-1", "--format=%s"), f"Fill in a build heading (hooks skipped on {sha[:7]})")
        wip = changelog.open_section(changelog.parse(text))
        self.assertEqual(wip.builds[0].commit, sha[:7])
        self.assertEqual(wip.ticket_numbers(), [201, 205])
        first = wip.builds[0].blocks[0]
        self.assertIn(f"Note from the automation: this commit ({sha[:7]}", first.body[0])
        self.assertEqual(len(wip.builds[0].blocks), 2)
        self.assertTrue(run.log)

    def test_the_commit_is_pushed_to_the_branch(self):
        self.git("push", "-q", "-u", "origin", "feature")
        sha = self.commit(SKIPPED, "work, hooks skipped")
        before = self.git("rev-parse", "origin/feature")
        self.git("push", "-q", "origin", "feature")
        self.git("checkout", "-q", "--detach", sha)  # as the workflow checks out the pushed commit
        run = skipped_hooks.repair(self.dir, before, sha, "feature")
        remote_head = subprocess.run(["git", "log", "-1", "--format=%s", "feature"], cwd=self.remote, capture_output=True, text=True).stdout.strip()
        self.assertEqual(remote_head, f"Fill in a build heading (hooks skipped on {sha[:7]})")
        self.assertFalse(any("could not be pushed" in line for line in run.log))

    def test_a_push_that_cannot_be_fast_forwarded_is_reported(self):
        self.git("push", "-q", "-u", "origin", "feature")
        before = self.git("rev-parse", "HEAD")
        sha = self.commit(SKIPPED, "work, hooks skipped")
        # someone else moved the remote branch on in the meantime
        other = os.path.join(self.tmp.name, "other")
        subprocess.run(["git", "clone", "-q", "-b", "main", self.remote, other], check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=O", "-c", "user.email=o@example.com", "commit", "-q", "--allow-empty", "-m", "elsewhere"],
                       cwd=other, check=True, capture_output=True)
        subprocess.run(["git", "push", "-q", "origin", "HEAD:refs/heads/feature"], cwd=other, check=True, capture_output=True)
        run = skipped_hooks.repair(self.dir, before, sha, "feature")
        self.assertTrue(any("could not be pushed" in line for line in run.log))

    def test_nothing_to_do_without_a_placeholder(self):
        sha = self.commit(STAMPED, "work, hooks used")
        run = skipped_hooks.repair(self.dir, checks.ZEROS, sha, "feature", push=False)
        self.assertEqual(run.log, ["no build placeholder in the pushed changelog"])
        self.assertEqual(self.changelog(), STAMPED)

    def test_a_placeholder_already_in_the_branch_is_left_alone(self):
        earlier = self.commit(SKIPPED, "earlier, hooks skipped")
        with open(os.path.join(self.dir, "code.txt"), "w", encoding="utf-8") as handle:
            handle.write("x")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "code only")
        tip = self.git("rev-parse", "HEAD")
        run = skipped_hooks.repair(self.dir, earlier, tip, "feature", push=False)
        self.assertIn("already in the branch", run.log[0])

    def test_dry_run_changes_nothing(self):
        sha = self.commit(SKIPPED, "work, hooks skipped")
        head = self.git("rev-parse", "HEAD")
        run = skipped_hooks.repair(self.dir, checks.ZEROS, sha, "feature", dry_run=True)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.changelog(), SKIPPED)
        self.assertTrue(any("fill in the build heading" in line for line in run.log))

    def test_the_newest_commit_with_the_placeholder_is_the_one_named(self):
        self.commit(SKIPPED, "first, hooks skipped", date="2026-10-06T09:00:00+00:00")
        sha = self.commit(SKIPPED.replace("guide: written.", "guide: rewritten."), "second, hooks skipped", date="2026-10-06T11:30:00+00:00")
        skipped_hooks.repair(self.dir, checks.ZEROS, sha, "feature", push=False)
        self.assertIn(f"### Build 20261006113000 (branch feature, commit {sha[:7]})", self.changelog())


class ChangelogSupportTests(unittest.TestCase):
    def test_a_commit_heading_is_read_and_a_plain_one_has_none(self):
        text = STAMPED.replace("(branch feature)", "(branch feature, commit 1a2b3c4)")
        self.assertEqual(changelog.open_section(changelog.parse(text)).builds[0].commit, "1a2b3c4")
        self.assertEqual(changelog.open_section(changelog.parse(STAMPED)).builds[0].commit, "")

    def test_a_bad_commit_heading_is_an_error(self):
        with self.assertRaises(changelog.ChangelogError):
            changelog.parse(STAMPED.replace("(branch feature)", "(branch feature, commit xyz)"))

    def test_add_note_needs_an_entry(self):
        with self.assertRaises(changelog.ChangelogError):
            changelog.add_note(STAMPED, "20269999999999", "note")


if __name__ == "__main__":
    unittest.main()
