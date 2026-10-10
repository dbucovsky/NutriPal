import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import board_status  # noqa: E402
import failures  # noqa: E402
from github_api import Client  # noqa: E402


class Out(io.StringIO):
    def reconfigure(self, **kwargs):
        pass


class Project:
    def __init__(self):
        self.calls = []

    def set_project_description(self, project_id, text):
        self.calls.append((project_id, text))


class Board:
    id = "P1"


class FailureTraceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.file = os.path.join(self.dir.name, "trace.txt")

    def test_outside_a_workflow_run_nothing_is_recorded(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(failures.path())
            self.assertFalse(failures.record("lost"))
            self.assertEqual(failures.recorded(), [])

    def test_lines_are_kept_in_order_on_one_line_each(self):
        with mock.patch.dict(os.environ, {"BOARD_FAILURES_FILE": self.file}, clear=True):
            self.assertTrue(failures.record("first\nwith a break"))
            failures.record("second")
            self.assertEqual(failures.recorded(), ["first with a break", "second"])

    def test_the_runner_temp_directory_is_used_when_no_file_is_named(self):
        with mock.patch.dict(os.environ, {"RUNNER_TEMP": self.dir.name}, clear=True):
            failures.record("x")
            self.assertTrue(os.path.exists(os.path.join(self.dir.name, failures.NAME)))


class BoardStatusTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.file = os.path.join(self.dir.name, "trace.txt")
        patcher = mock.patch.dict(os.environ, {"BOARD_FAILURES_FILE": self.file, "GITHUB_REPOSITORY": "o/r"}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, args):
        out = Out()
        with redirect_stdout(out):
            code = board_status.main(args)
        return code, out.getvalue()

    def test_a_recorded_failure_ends_the_run_red_and_names_it(self):
        failures.record("Watch sweep stopped: GitHub returned 502: Bad Gateway")
        code, out = self.run_main([])
        self.assertEqual(code, 1)
        self.assertIn("::error title=The board was not updated::Watch sweep stopped", out)

    def test_a_failed_job_is_not_stamped(self):
        code, out = self.run_main(["--job-status", "failure"])
        self.assertEqual(code, 0)
        self.assertIn("not stamped", out)

    def test_the_description_is_the_time_of_the_check(self):
        text = board_status.description(datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc))
        self.assertTrue(text.startswith("Board checked 2026-10-09"), text)
        self.assertTrue(text.endswith("UTC"), text)

    def test_stamp_writes_unless_it_is_a_dry_run(self):
        project, now = Project(), datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc)
        board_status.stamp(project, Board(), now, dry_run=True)
        self.assertEqual(project.calls, [])
        text = board_status.stamp(project, Board(), now)
        self.assertEqual(project.calls, [("P1", text)])

    def test_the_description_mutation_is_sent_with_the_project_and_text(self):
        sent = []

        def transport(method, url, headers, body):
            sent.append((method, url, body))
            return 200, '{"data":{"updateProjectV2":{"projectV2":{"id":"P1","shortDescription":"t"}}}}'

        Client("t", "o/r", transport=transport).set_project_description("P1", "Board checked now")
        self.assertIn(b"updateProjectV2", sent[0][2])
        self.assertIn(b"Board checked now", sent[0][2])

    def test_no_stamp_option_does_nothing_when_all_went_well(self):
        code, _ = self.run_main(["--no-stamp"])
        self.assertEqual(code, 0)


class EverySweepRecordsItsFailureTests(unittest.TestCase):
    def test_each_place_that_carries_on_after_a_board_error_also_records_it(self):
        scripts = os.path.join(ROOT, ".github", "scripts")
        for name in ("conditions", "dates", "implemented", "version_numbers", "watch", "finalize"):
            with open(os.path.join(scripts, name + ".py"), encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("import failures", text, name)
            self.assertIn("failures.record(", text, name)


if __name__ == "__main__":
    unittest.main()
