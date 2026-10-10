import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".githooks"))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import changelog  # noqa: E402
import hooks  # noqa: E402

BASE = """# Changelog

## V0.1.0 — 2026-10-05 18:22 UTC
### Build 20261005181657 (branch initial-structure)
#### #1 — Initial structure of the project
- guides/: added.
"""

WIP_ONE = """# Changelog

## WIP-Version
### WIP-Build
#### #204 — Report totals ignore the last day of the month
- report totals: the last day is now included.
- tests: added a test for months of 28 to 31 days.

""" + BASE.split("\n", 2)[2]

WIP_TWO = WIP_ONE.replace("### WIP-Build\n", "### WIP-Build\n#### #205 — Write the user guide\n- guide: written.\n", 1)

WIP_REF = """# Changelog

## WIP-Version
### WIP-Build
#### REF 20261006091500 — no ticket yet (typo in the settings help text)
- settings help text: fixed the spelling of "authentication".

""" + BASE.split("\n", 2)[2]

NOW = datetime(2026, 10, 6, 9, 12, 0, tzinfo=timezone.utc)


def run(*args, cwd, env=None, input=None):
    full = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, **(env or {}))
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=full, input=input)


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        run("init", "-q", "-b", "main", cwd=self.dir)
        for key, value in (("user.name", "Tester"), ("user.email", "t@example.com"), ("core.autocrlf", "false")):
            run("config", key, value, cwd=self.dir)
        write(os.path.join(self.dir, "CHANGELOG.md"), BASE)
        run("add", "-A", cwd=self.dir)
        run("commit", "-q", "-m", "start", cwd=self.dir)
        run("switch", "-q", "-c", "csv-export", cwd=self.dir)

    def edit(self, changelog_text, other=None):
        write(os.path.join(self.dir, "CHANGELOG.md"), changelog_text)
        if other:
            write(os.path.join(self.dir, other), "x\n")
        run("add", "-A", cwd=self.dir)


class DraftTests(unittest.TestCase):
    def builds(self, text):
        return changelog.parse(text.replace("### WIP-Build", "### Build 20261006091200 (branch b)"))[0].builds

    def test_one_ticket_uses_its_title_as_the_summary(self):
        message = hooks.draft_message(self.builds(WIP_ONE))
        self.assertEqual(message, (
            "Report totals ignore the last day of the month\n\n"
            "Ticket #204 — Report totals ignore the last day of the month\n"
            "- report totals: the last day is now included.\n"
            "- tests: added a test for months of 28 to 31 days.\n"))

    def test_several_tickets(self):
        message = hooks.draft_message(self.builds(WIP_TWO))
        self.assertTrue(message.startswith("Multiple tickets\n\nTicket #205 — Write the user guide\n- guide: written.\n\nTicket #204"))

    def test_ref_only_uses_the_first_bullet(self):
        message = hooks.draft_message(self.builds(WIP_REF))
        self.assertTrue(message.startswith('settings help text: fixed the spelling of "authentication".\n\nREF 20261006091500 — no ticket'))

    def test_long_first_bullet_is_shortened(self):
        text = WIP_REF.replace('fixed the spelling of "authentication".', "x" * 30 + " " + "y" * 60)
        summary = hooks.draft_message(self.builds(text)).split("\n")[0]
        self.assertLessEqual(len(summary), 72)
        self.assertTrue(summary.endswith("…"))

    def test_the_same_ticket_in_two_builds_is_one_block(self):
        text = WIP_ONE.replace("## V0.1.0", "### Build 20261006080000 (branch b)\n#### #204 — Report totals ignore the last day of the month\n- earlier work.\n\n## V0.1.0", 1)
        message = hooks.draft_message(self.builds(text))
        self.assertEqual(message.count("Ticket #204"), 1)
        self.assertIn("- earlier work.", message)

    def test_no_blocks_gives_no_draft(self):
        self.assertIsNone(hooks.draft_message([]))

    def test_new_builds_ignores_what_head_already_has(self):
        self.assertEqual(hooks.new_builds(BASE, BASE), [])
        self.assertEqual(len(hooks.new_builds(BASE, None)), 1)


class StampTests(Repo):
    def test_stamps_the_staged_changelog_and_the_working_copy(self):
        self.edit(WIP_ONE)
        self.assertEqual(hooks.stamp_staged(self.dir, NOW), "20261006091200")
        staged = run("show", ":CHANGELOG.md", cwd=self.dir).stdout
        self.assertIn("### Build 20261006091200 (branch csv-export)", staged)
        self.assertNotIn("WIP-Build", staged)
        with open(os.path.join(self.dir, "CHANGELOG.md"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), staged)

    def test_line_endings_stay_lf(self):
        self.edit(WIP_ONE)
        hooks.stamp_staged(self.dir, NOW)
        raw = subprocess.run(["git", "show", ":CHANGELOG.md"], cwd=self.dir, capture_output=True).stdout
        self.assertNotIn(b"\r", raw)

    def test_only_what_is_staged_is_stamped(self):
        self.edit(WIP_ONE)
        write(os.path.join(self.dir, "CHANGELOG.md"), WIP_ONE + "\nan unstaged edit\n")
        hooks.stamp_staged(self.dir, NOW)
        staged = run("show", ":CHANGELOG.md", cwd=self.dir).stdout
        self.assertNotIn("unstaged edit", staged)
        with open(os.path.join(self.dir, "CHANGELOG.md"), encoding="utf-8") as handle:
            working = handle.read()
        self.assertIn("unstaged edit", working)
        self.assertNotIn("WIP-Build", working)

    def test_nothing_to_stamp(self):
        self.assertIsNone(hooks.stamp_staged(self.dir, NOW))


class WarningTests(Repo):
    def test_no_warning_for_a_commit_with_an_entry(self):
        self.edit(WIP_ONE, "code.txt")
        self.assertEqual(hooks.pre_commit(self.dir, NOW), [])

    def test_warns_when_files_change_without_the_changelog(self):
        write(os.path.join(self.dir, "code.txt"), "x\n")
        run("add", "-A", cwd=self.dir)
        self.assertIn("not CHANGELOG.md", hooks.pre_commit(self.dir, NOW)[0])

    def test_warns_when_the_changelog_has_no_new_build(self):
        self.edit(BASE + "\nsome note\n", "code.txt")
        self.assertIn("no new build", hooks.pre_commit(self.dir, NOW)[0])

    def test_warns_about_a_broken_changelog(self):
        self.edit(WIP_ONE.replace("#### #204 —", "#### ticket"), "code.txt")
        self.assertIn("CHANGELOG.md has a problem", hooks.pre_commit(self.dir, NOW)[0])

    def test_merge_in_progress_reminds_to_recompile(self):
        run("switch", "-q", "main", cwd=self.dir)
        write(os.path.join(self.dir, "m.txt"), "m\n")
        run("add", "-A", cwd=self.dir)
        run("commit", "-q", "-m", "main moves", cwd=self.dir)
        run("switch", "-q", "csv-export", cwd=self.dir)
        run("merge", "--no-commit", "--no-ff", "main", cwd=self.dir)
        warnings = hooks.pre_commit(self.dir, NOW)
        self.assertIn("recompile", warnings[0])
        self.assertEqual(len(warnings), 1)

    def test_pre_push_warns_when_behind_main(self):
        run("switch", "-q", "main", cwd=self.dir)
        write(os.path.join(self.dir, "m.txt"), "m\n")
        run("add", "-A", cwd=self.dir)
        run("commit", "-q", "-m", "main moves", cwd=self.dir)
        run("update-ref", "refs/remotes/origin/main", "main", cwd=self.dir)
        run("switch", "-q", "csv-export", cwd=self.dir)
        sha = run("rev-parse", "HEAD", cwd=self.dir).stdout.strip()
        warnings = hooks.pre_push([f"refs/heads/csv-export {sha} refs/heads/csv-export {hooks.ZEROS}"], self.dir)
        self.assertIn("1 commit(s) behind main", warnings[0])

    def test_pre_push_warns_about_a_leftover_placeholder(self):
        run("update-ref", "refs/remotes/origin/main", "main", cwd=self.dir)
        write(os.path.join(self.dir, "CHANGELOG.md"), WIP_ONE)
        run("add", "-A", cwd=self.dir)
        run("commit", "-q", "-m", "skipped hooks", cwd=self.dir)
        sha = run("rev-parse", "HEAD", cwd=self.dir).stdout.strip()
        warnings = hooks.pre_push([f"refs/heads/csv-export {sha} refs/heads/csv-export {hooks.ZEROS}"], self.dir)
        self.assertTrue(any("placeholder" in w for w in warnings))

    def test_pre_push_ignores_deletes_and_garbage(self):
        self.assertEqual(hooks.pre_push([f"(delete) {hooks.ZEROS} refs/heads/x abc", "nonsense"], self.dir), [])


class EntryScriptTests(Repo):
    """The real entry scripts, driven by real git."""

    def commit(self, text, other="code.txt"):
        run("config", "core.hooksPath", os.path.join(ROOT, ".githooks"), cwd=self.dir)
        self.edit(text, other)
        return run("commit", "-q", cwd=self.dir, env={"GIT_EDITOR": "true"})

    def test_a_commit_is_stamped_and_its_message_drafted(self):
        result = self.commit(WIP_ONE)
        self.assertEqual(result.returncode, 0, result.stderr)
        message = run("log", "-1", "--format=%B", cwd=self.dir).stdout
        self.assertTrue(message.startswith("Report totals ignore the last day of the month\n\nTicket #204 — Report totals"))
        committed = run("show", "HEAD:CHANGELOG.md", cwd=self.dir).stdout
        self.assertNotIn("WIP-Build", committed)
        self.assertRegex(committed, r"### Build \d{14} \(branch csv-export\)")

    def test_a_commit_without_an_entry_still_goes_through_with_a_warning(self):
        result = self.commit(BASE)
        self.assertEqual(result.returncode, 1)  # git: nothing to commit, only the file code.txt was added
        write(os.path.join(self.dir, "code2.txt"), "y\n")
        run("add", "-A", cwd=self.dir)
        result = run("commit", "-q", "-m", "no entry", cwd=self.dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not CHANGELOG.md", result.stderr)

    def test_the_entry_scripts_are_executable_in_the_index(self):
        listing = run("ls-files", "-s", ".githooks", cwd=ROOT).stdout
        for name in ("pre-commit", "prepare-commit-msg", "pre-push"):
            self.assertIn("100755", [line.split()[0] for line in listing.splitlines() if line.endswith(name)][0])


if __name__ == "__main__":
    unittest.main()
