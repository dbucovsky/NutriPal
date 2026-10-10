import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import bypass  # noqa: E402
from versions import Version  # noqa: E402

PATH = os.path.join(ROOT, ".github", "workflows", "versioning.yml")


def workflow():
    with open(PATH, encoding="utf-8") as handle:
        return handle.read()


class WorkflowTests(unittest.TestCase):
    """Structure checks. The workflow itself is proven by a real run (see the level-1 proof)."""

    def test_no_step_name_has_a_colon_followed_by_a_space(self):
        # An unquoted "key: value" inside a name makes the whole file invalid YAML (GitHub reports a workflow file issue).
        for number, line in enumerate(workflow().split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("- name:") or stripped.startswith("name:"):
                value = stripped.split("name:", 1)[1].strip()
                if not value.startswith(("'", '"')):
                    self.assertNotIn(": ", value, f"line {number}")

    def test_no_tabs(self):
        for number, line in enumerate(workflow().split("\n"), 1):
            self.assertNotIn("\t", line, f"tab on line {number}")

    def test_triggers(self):
        text = workflow()
        for trigger in ("pull_request:", "push:", "workflow_dispatch:", "- '**'"):
            self.assertIn(trigger, text)

    def test_it_also_starts_on_issue_events_and_comments(self):
        text = workflow()
        self.assertRegex(text, r"(?m)^  issues:\n    types: \[edited, closed, reopened, assigned, labeled\]\n")
        self.assertRegex(text, r"(?m)^  issue_comment:\n    types: \[created, edited\]\n")

    def job(self, name, next_name):
        text = workflow()
        return text[text.index(f"\n  {name}:\n"):text.index(f"\n  {next_name}:\n")]

    def folded(self, job):
        """The folded `if: >-` expression of a job as one line, and the indents of its lines."""
        lines = job.split("\n")
        start = next(i for i, line in enumerate(lines) if line.startswith("    if: >-"))
        block = []
        for line in lines[start + 1:]:
            if not line.startswith("      "):
                break
            block.append(line)
        return " ".join(line.strip() for line in block), block

    def test_the_team_job_decides_who_may_start_the_refresh_by_the_senders_permission(self):
        job = self.job("team", "advisory")
        expression, block = self.folded(job)
        self.assertEqual({len(line) - len(line.lstrip()) for line in block}, {6})  # one indent, so the block folds into one line
        self.assertEqual(expression.count("("), expression.count(")"))
        self.assertEqual(expression.count("'") % 2, 0)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.mode == 'conditions'", expression)
        self.assertIn("github.event_name == 'issues'", expression)
        self.assertIn("github.event_name == 'issue_comment' && !github.event.issue.pull_request", expression)
        # the person is asked about by permission, never by the association in the payload (it hides private members)
        self.assertIn('gh api "repos/$REPOSITORY/collaborators/$SENDER/permission"', job)
        self.assertIn("admin|write)", job)
        self.assertNotIn("author_association ==", job)
        self.assertNotIn("contains(", job)
        # it prints the association the payload carried, so the cause of a refusal can be read in the log
        self.assertIn("ASSOCIATION: ${{ github.event.issue.author_association }}", job)
        self.assertIn("association in the payload", job)
        # no secret but the workflow token, and no concurrency group (a stranger's run must not take a real run's place)
        self.assertNotIn("PROJECT_TOKEN", job)
        self.assertNotIn("concurrency:", job)
        self.assertEqual(job.count("secrets."), 1)
        self.assertIn("allowed: ${{ steps.who.outputs.allowed }}", job)

    def test_the_conditions_job_runs_only_when_the_team_job_allowed_it(self):
        job = self.job("conditions", "release")
        expression, _ = self.folded(job) if "if: >-" in job else (None, None)
        self.assertIsNone(expression)
        self.assertIn("    needs: team\n", job)
        self.assertIn("    if: ${{ always() && needs.team.outputs.allowed == 'true' }}\n", job)
        # the secrets are on the steps that use them, not on the job, and the checkout needs none
        header = job[:job.index("    steps:")]
        self.assertNotIn("PROJECT_TOKEN", header)
        self.assertNotIn("secrets.", header)
        steps = job[job.index("    steps:"):]
        self.assertEqual(steps.count("PROJECT_TOKEN: ${{ secrets.PROJECT_TOKEN }}"), 4)

    def test_no_other_job_starts_on_an_issue_event(self):
        text = workflow()
        for job in ("advisory", "branch", "main", "scheduled", "conditions", "release", "hotfix", "retire"):
            body = text[text.index(f"\n  {job}:\n"):]
            condition = body[:body.index("\n    runs-on:")]
            self.assertNotIn("'issues'", condition, job)
            self.assertNotIn("'issue_comment'", condition, job)

    def test_no_event_text_reaches_a_shell_command(self):
        lines = workflow().split("\n")
        for number, line in enumerate(lines):
            if re.match(r"\s+run:", line):
                indent = len(line) - len(line.lstrip())
                body = [line]
                for later in lines[number + 1:]:
                    if later.strip() and len(later) - len(later.lstrip()) <= indent:
                        break
                    body.append(later)
                for text in body:
                    self.assertNotIn("github.event.", text, f"line {number + 1}")
                    self.assertNotIn("github.head_ref", text, f"line {number + 1}")

    def test_no_script_writes_a_comment_or_an_issue_with_the_personal_token(self):
        # an event started by the personal token would start the workflow again: a loop. The workflow token starts none.
        scripts = os.path.join(ROOT, ".github", "scripts")
        pattern = re.compile(r"project_client\.(comment|close_issue|create_issue|add_sub_issue|edit_comment)\b"
                             r"|project_client\.request\(\s*[\"'](POST|PATCH|PUT|DELETE)[\"'][^)]*(issues|comments)")
        for name in sorted(os.listdir(scripts)):
            if name.endswith(".py"):
                with open(os.path.join(scripts, name), encoding="utf-8") as handle:
                    self.assertIsNone(pattern.search(handle.read()), name)

    def test_every_job_that_writes_to_the_board_ends_with_the_status_step(self):
        text = workflow()
        for job, nxt in (("main", "scheduled"), ("scheduled", "conditions"), ("conditions", "release")):
            body = text[text.index(f"\n  {job}:\n"):text.index(f"\n  {nxt}:\n")]
            self.assertIn("board_status.py", body, job)
            self.assertGreater(body.index("board_status.py"), body.index("conditions.py"), job)
            step = body[body.index("End red if a board write failed"):]
            self.assertIn("if: always()", step.split("run:")[0], job)
            self.assertIn('--job-status "${{ job.status }}"', step, job)
            self.assertEqual(step.count("- name:"), 0, f"{job}: it is the last step")

    def test_the_trial_input_is_explicit_off_by_default_and_reaches_the_three_manual_runs(self):
        text = workflow()
        self.assertRegex(text, r"(?m)^      trial:\n        description: '[^\n]*test/[^\n]*'\n        type: boolean\n        default: false\n")
        for job, nxt in (("release", "hotfix"), ("hotfix", "retire"), ("retire", None)):
            start = text.index(f"\n  {job}:\n")
            body = text[start:text.index(f"\n  {nxt}:\n")] if nxt else text[start:]
            self.assertIn("TRIAL: ${{ inputs.trial }}", body, job)

    def test_declares_its_own_permissions(self):
        text = workflow()
        self.assertRegex(text, r"(?m)^permissions:\n  contents: write\n  issues: write\n  pull-requests: write\n")

    def test_every_script_it_runs_exists(self):
        scripts = re.findall(r"python3 (\.github/scripts/\w+\.py)", workflow())
        self.assertTrue(scripts)
        for script in scripts:
            self.assertTrue(os.path.exists(os.path.join(ROOT, script)), script)

    def test_the_preflight_runs_before_the_other_steps(self):
        text = workflow()
        main = text[text.index("\n  main:"):]
        self.assertLess(main.index("preflight.py"), main.index("bypass.py"))
        self.assertLess(main.index("bypass.py"), main.index("finalize.py"))
        self.assertLess(main.index("finalize.py"), main.index("bypass.py stale"))
        self.assertLess(main.index("bypass.py stale"), main.index("version_numbers.py"))
        self.assertLess(main.index("version_numbers.py"), main.index("dates.py"))
        self.assertLess(main.index("dates.py"), main.index("watch.py"))
        self.assertLess(main.index("watch.py"), main.index("conditions.py"))
        self.assertNotIn("field_rules.py", main)

    def test_uses_the_project_token_and_skips_its_own_commits(self):
        text = workflow()
        self.assertIn("secrets.PROJECT_TOKEN", text)
        self.assertIn("startsWith(github.event.head_commit.message, 'Finalize ')", text)
        self.assertIn("startsWith(github.event.head_commit.message, 'Flag bypass')", text)

    def test_the_commit_messages_it_skips_are_the_ones_the_scripts_write(self):
        import finalize
        import inspect
        self.assertIn('f"Finalize {version}', inspect.getsource(finalize.commit_heading))
        self.assertIn('f"Flag bypass (Alert', inspect.getsource(bypass.commit_entry))

    def test_branch_pushes_run_the_push_step_after_the_preflight(self):
        text = workflow()
        branch = text[text.index("  branch:"):text.index("  main:")]
        self.assertLess(branch.index("preflight.py"), branch.index("skipped_hooks.py"))
        self.assertLess(branch.index("skipped_hooks.py"), branch.index("push_step.py"))
        self.assertIn("AFTER_SHA=$(git rev-parse HEAD)", branch)  # the push step reads the repaired changelog
        self.assertIn("github.ref != 'refs/heads/main'", branch)
        self.assertIn("!github.event.deleted", branch)
        self.assertIn("- '**'", text)

    def test_the_main_job_only_runs_for_main(self):
        text = workflow()
        main = text[text.index("  main:"):]
        self.assertIn("github.ref == 'refs/heads/main'", main)

    def test_a_pull_request_is_put_on_the_board_before_the_advisory_check_and_cannot_fail_the_run(self):
        text = workflow()
        advisory = text[text.index("\n  advisory:\n"):text.index("\n  branch:\n")]
        step = advisory[advisory.index("Put the pull request on the board"):advisory.index("Advisory check")]
        self.assertIn("continue-on-error: true", step)
        self.assertIn("board_pull_requests.py", step)
        self.assertIn("PULL_REQUEST_NODE_ID: ${{ github.event.pull_request.node_id }}", step)
        self.assertIn("PROJECT_TOKEN: ${{ secrets.PROJECT_TOKEN }}", step)

    def test_the_scheduled_job_is_scheduled_and_can_be_started_by_hand(self):
        text = workflow()
        self.assertRegex(text, r"schedule:\n    - cron: '\d+ \d+ \* \* \*'")
        self.assertEqual(re.findall(r"- cron: '(\d+ \d+) \* \* \*'", text), ["17 8", "17 16", "17 20"])
        self.assertIn("mode:", text)
        self.assertIn("- finalize", text)
        self.assertIn("- scheduled", text)
        scheduled = text[text.index("  scheduled:"):text.index("  conditions:")]
        self.assertIn("github.event_name == 'schedule'", scheduled)
        self.assertIn("inputs.mode == 'scheduled'", scheduled)

    def test_the_scheduled_job_runs_the_checks_in_order_and_never_commits(self):
        text = workflow()
        scheduled = text[text.index("  scheduled:"):text.index("  conditions:")]
        order = ["preflight.py", "implemented.py", "version_numbers.py", "dates.py", "watch.py", "conditions.py"]
        positions = [scheduled.index(name) for name in order]
        self.assertEqual(positions, sorted(positions))
        for forbidden in ("git push", "git commit", "finalize.py", "bypass.py"):
            self.assertNotIn(forbidden, scheduled)
        self.assertIn("--dry-run", scheduled)

    def test_the_main_and_scheduled_jobs_share_one_concurrency_group_and_never_cancel_a_run(self):
        text = workflow()
        for job in (text[text.index("  main:"):text.index("  scheduled:")], text[text.index("  scheduled:"):text.index("  conditions:")],
                    text[text.index("  conditions:"):text.index("  release:")]):
            self.assertIn("concurrency:\n      group: versioning-board\n      cancel-in-progress: false\n", job)
        self.assertEqual(text.count("group: versioning-board"), 3)

    def test_the_conditions_are_refreshed_after_a_merge_on_the_schedule_and_on_request(self):
        text = workflow()
        main = text[text.index("  main:"):text.index("  scheduled:")]
        self.assertLess(main.index("watch.py"), main.index("conditions.py"))  # after finalize and every sweep
        self.assertIn("- conditions", text)
        job = text[text.index("  conditions:"):text.index("  release:")]
        self.assertIn("needs: team", job)  # a start on request is allowed by the job team, which allows mode conditions
        self.assertLess(job.index("preflight.py"), job.index("implemented.py"))  # a ticket waiting for its Version is attached first
        self.assertLess(job.index("implemented.py"), job.index("conditions.py"))
        self.assertIn("DRY_RUN: ${{ inputs.dry_run }}", job)
        for forbidden in ("git push", "git commit", "finalize.py", "bypass.py"):
            self.assertNotIn(forbidden, job)

    def test_the_finalize_job_only_runs_for_its_own_mode(self):
        text = workflow()
        main = text[text.index("  main:"):text.index("  scheduled:")]
        self.assertIn("inputs.mode == 'finalize'", main)

    def jobs(self):
        text = workflow()
        return (text[text.index("  release:"):text.index("  hotfix:")],
                text[text.index("  hotfix:"):text.index("  retire:")],
                text[text.index("  retire:"):])

    def test_release_hotfix_and_retire_are_modes_of_a_manual_start(self):
        text = workflow()
        for mode in ("release", "hotfix", "retire"):
            self.assertIn(f"          - {mode}", text)
        release, hotfix, retire = self.jobs()
        for job, mode in ((release, "release"), (hotfix, "hotfix"), (retire, "retire")):
            self.assertIn(f"github.event_name == 'workflow_dispatch' && inputs.mode == '{mode}'", job)
            self.assertLess(job.index("preflight.py"), job.index(f"{mode}.py"))
            self.assertIn("--dry-run", job)
            self.assertIn("DRY_RUN: ${{ inputs.dry_run }}", job)

    def test_the_inputs_of_the_three_steps_reach_their_scripts(self):
        release, hotfix, retire = self.jobs()
        self.assertIn("VERSION: ${{ inputs.version }}", release)
        self.assertIn("VERSION: ${{ inputs.version }}", hotfix)
        self.assertIn("BRANCH: ${{ github.ref_name }}", hotfix)  # a hotfix is finished from its own branch
        self.assertIn("github.ref_type == 'branch'", hotfix)
        for name in ("BRANCH: ${{ inputs.branch }}", "OUTCOME: ${{ inputs.outcome }}", "CONFIRM: ${{ inputs.confirm }}",
                     "COMMENT: ${{ inputs.comment }}"):
            self.assertIn(name, retire)

    def test_release_and_retire_use_the_ref_they_were_started_from_and_the_hotfix_its_branch_with_tags(self):
        release, hotfix, retire = self.jobs()
        for job in (release, retire):
            self.assertNotIn("ref:", job.split("steps:")[1])  # the default checkout: the ref of the manual start
        self.assertIn("ref: ${{ github.ref_name }}", hotfix)
        self.assertIn("fetch-tags: true", hotfix)
        for job in (release, hotfix, retire):
            self.assertIn("fetch-depth: 0", job)

    def test_only_the_hotfix_job_makes_a_commit_and_the_others_never_push_with_git(self):
        release, hotfix, retire = self.jobs()
        self.assertIn("git config user.name", hotfix)
        for job in (release, retire):
            self.assertNotIn("git config", job)
            self.assertNotIn("git push", job)

    def test_the_default_manual_start_is_still_a_dry_run_of_finalize(self):
        text = workflow()
        self.assertRegex(text, r"mode:\n(?:.*\n)*?\s+default: finalize")

    def test_manual_runs_are_dry_runs_by_default(self):
        self.assertRegex(workflow(), r"dry_run:\n(?:.*\n)*?\s+default: true")


class FakeRepo:
    repo = "owner/repo"

    def __init__(self, planned):
        self.planned, self.created = planned, []

    def repo_path(self, path):
        return path

    def request(self, method, path, body=None):
        return self.planned

    def create_issue(self, title, body, issue_type=None, labels=(), assignees=()):
        self.created.append(title)
        return {"number": 1, "node_id": "N"}


class StaleCommandTests(unittest.TestCase):
    def run_command(self, changelog_text, planned):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "CHANGELOG.md"), "w", encoding="utf-8") as handle:
                handle.write(changelog_text)
            repo = FakeRepo(planned)
            return bypass.stale_command(folder, repo, None, None), repo

    def test_raises_the_alert_for_the_topmost_version(self):
        _, repo = self.run_command("# Changelog\n\n## V0.2.0 — 2026-10-05 21:24 UTC\n", [{"title": "Version 0.1.5", "number": 9}])
        self.assertEqual(repo.created, ["Stale planned Version tickets after V0.2.0"])

    def test_nothing_planned(self):
        _, repo = self.run_command("# Changelog\n\n## V0.2.0 — 2026-10-05 21:24 UTC\n", [])
        self.assertEqual(repo.created, [])

    def test_no_finalized_version(self):
        run, repo = self.run_command("# Changelog\n", [])
        self.assertEqual(run.log, ["no finalized version"])


if __name__ == "__main__":
    unittest.main()
