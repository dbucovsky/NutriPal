import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import reenable_schedule  # noqa: E402
from github_api import Client, GitHubError  # noqa: E402

WORKFLOW = os.path.join(ROOT, ".github", "workflows", "reenable-schedule.yml")


def client(state, enable_status=204):
    calls = []

    def transport(method, url, headers, body):
        calls.append((method, url.split("/repos/owner/repo")[1]))
        if method == "GET":
            return 200, '{"state": "%s"}' % state, {}
        return enable_status, "" if enable_status < 300 else '{"message": "no"}', {}

    made = Client("t", "owner/repo", transport=transport)
    made.calls = calls
    return made


class DecideTests(unittest.TestCase):
    def test_only_an_inactivity_disable_is_turned_back_on(self):
        self.assertEqual(reenable_schedule.decide("disabled_inactivity"), "enable")
        for state in ("active", "disabled_manually", "disabled_fork", "deleted"):
            self.assertEqual(reenable_schedule.decide(state), "leave", state)


class RunTests(unittest.TestCase):
    def test_enables_a_workflow_disabled_for_inactivity(self):
        api = client("disabled_inactivity")
        lines = reenable_schedule.run(api)
        self.assertIn(("PUT", "/actions/workflows/versioning.yml/enable"), api.calls)
        self.assertIn("enabled it", lines[0])

    def test_dry_run_reports_and_changes_nothing(self):
        api = client("disabled_inactivity")
        lines = reenable_schedule.run(api, dry_run=True)
        self.assertEqual([m for m, _ in api.calls], ["GET"])
        self.assertIn("would enable", lines[0])

    def test_leaves_a_workflow_a_person_disabled(self):
        api = client("disabled_manually")
        lines = reenable_schedule.run(api)
        self.assertEqual([m for m, _ in api.calls], ["GET"])
        self.assertIn("nothing to do", lines[0])

    def test_an_active_workflow_is_left_alone(self):
        api = client("active")
        reenable_schedule.run(api)
        self.assertEqual([m for m, _ in api.calls], ["GET"])

    def test_a_refused_enable_raises_so_the_run_fails(self):
        with self.assertRaises(GitHubError):
            reenable_schedule.run(client("disabled_inactivity", enable_status=403))


class WorkflowFileTests(unittest.TestCase):
    def setUp(self):
        with open(WORKFLOW, encoding="utf-8") as handle:
            self.text = handle.read()

    def test_has_no_schedule_so_github_never_disables_it(self):
        self.assertNotIn("schedule:", self.text)

    def test_runs_on_every_push(self):
        self.assertRegex(self.text, r"push:\n    branches:\n      - '\*\*'")

    def test_asks_only_for_the_actions_right(self):
        self.assertRegex(self.text, r"(?m)^permissions:\n  actions: write\n\njobs:")

    def test_the_script_it_runs_exists(self):
        for script in re.findall(r"python3 (\.github/scripts/\w+\.py)", self.text):
            self.assertTrue(os.path.exists(os.path.join(ROOT, script)), script)

    def test_no_tabs_and_no_colon_space_in_step_names(self):
        for number, line in enumerate(self.text.split("\n"), 1):
            self.assertNotIn("\t", line, f"tab on line {number}")
            stripped = line.strip()
            if stripped.startswith("- name:") or stripped.startswith("name:"):
                value = stripped.split("name:", 1)[1].strip()
                if not value.startswith(("'", '"')):
                    self.assertNotIn(": ", value, f"line {number}")

    def test_the_workflow_it_turns_on_is_the_one_with_the_schedule(self):
        with open(os.path.join(ROOT, ".github", "workflows", reenable_schedule.WORKFLOW), encoding="utf-8") as handle:
            self.assertIn("schedule:", handle.read())


if __name__ == "__main__":
    unittest.main()
