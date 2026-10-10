import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import preflight  # noqa: E402
from github_api import GitHubError  # noqa: E402


def board_fields(missing=(), drop_value=None):
    nodes = []
    for index, (name, (kind, values)) in enumerate(preflight.REQUIRED_FIELDS.items()):
        if name in missing:
            continue
        node = {"id": f"F{index}", "name": name, "dataType": kind}
        if kind == preflight.SELECT:
            node["options"] = [{"id": f"{name}-{v}", "name": v} for v in values if v != drop_value]
        nodes.append(node)
    nodes.append({})  # a field type the query does not select comes back empty
    return nodes


GOOD_SETTINGS = {"permissions": {"push": True}, "allow_merge_commit": True, "allow_squash_merge": False,
                 "allow_rebase_merge": False, "delete_branch_on_merge": False, "default_branch": "main",
                 "has_issues": True, "has_projects": True, "has_wiki": True}
GOOD_PROTECTION = {"required_pull_request_reviews": {"required_approving_review_count": 0},
                   "required_status_checks": {"strict": True, "contexts": ["advisory"]},
                   "enforce_admins": {"enabled": False}}


class FakeRepoClient:
    repo = "owner/repo"
    token = "t"

    def __init__(self, info=None, error=None):
        self.info, self.error = ({"permissions": {"push": True}} if info is None else info), error

    def request(self, method, path, body=None):
        if self.error:
            raise self.error
        return self.info


class FakeProjectClient:
    repo = "owner/repo"

    def __init__(self, token="p", boards=None, variable=None, fields=None, viewer_error=None, store_error=None, expiry=None,
                 push=True, request_error=None, protection=None):
        self.token, self.expiry, self.push, self.request_error = token, expiry, push, request_error
        self.protection = GOOD_PROTECTION if protection is None else protection
        self.asked_protection = False
        self.boards = [{"id": "P7", "number": 7, "title": "Governance"}] if boards is None else boards
        self.variable, self.fields = variable, fields if fields is not None else board_fields()
        self.viewer_error, self.store_error = viewer_error, store_error
        self.stored = {}

    def graphql(self, query, variables=None):
        if "viewer" in query:
            if self.viewer_error:
                raise self.viewer_error
            return {"viewer": {"login": "admin"}}
        if "projectsV2" in query:
            return {"repository": {"projectsV2": {"nodes": self.boards}}}
        return {"node": {"fields": {"nodes": self.fields}}}

    def request(self, method, path, body=None):
        if path.endswith("/protection"):
            self.asked_protection = True
            if isinstance(self.protection, Exception):
                raise self.protection
            return self.protection
        if self.request_error:
            raise self.request_error
        return {"permissions": {"push": self.push}}

    def token_expiry(self):
        return self.expiry

    def get_variable(self, name):
        return self.variable

    def set_variable(self, name, value):
        if self.store_error:
            raise self.store_error
        self.stored[name] = value


def quiet_project(**kwargs):
    """A project client whose token has a distant expiry, so that no token warning gets in the way."""
    return FakeProjectClient(expiry=datetime.now(timezone.utc) + timedelta(days=90), **kwargs)


class PreflightTests(unittest.TestCase):
    def test_everything_passes_and_the_board_number_is_stored(self):
        project = FakeProjectClient()
        report = preflight.run(FakeRepoClient(), project)
        self.assertTrue(report.ok, report.render())
        self.assertEqual(project.stored, {"BOARD_NUMBER": "7"})
        self.assertEqual(report.board.number, 7)
        self.assertEqual(report.board.fields["Status"]["options"]["Review"], "Status-Review")
        self.assertIn("preflight: passed", report.render())

    def test_a_token_close_to_expiry_gives_a_warning(self):
        soon = datetime.now(timezone.utc) + timedelta(days=5, hours=1)
        report = preflight.run(FakeRepoClient(), FakeProjectClient(expiry=soon))
        self.assertTrue(report.ok)
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("expires in 5 day(s)", report.warnings[0])
        self.assertIn("[warning]", report.render())

    def test_a_token_with_a_distant_expiry_gives_no_warning(self):
        later = datetime.now(timezone.utc) + timedelta(days=90)
        report = preflight.run(FakeRepoClient(), FakeProjectClient(expiry=later))
        self.assertEqual(report.warnings, [])
        self.assertIn("expires", report.checks[1].message)

    def test_a_token_with_no_expiry_gives_a_warning(self):
        report = preflight.run(FakeRepoClient(), FakeProjectClient())
        self.assertIn("no expiry date", report.warnings[0])

    def test_the_variable_is_not_rewritten_when_it_already_matches(self):
        project = FakeProjectClient(variable="7")
        preflight.run(FakeRepoClient(), project)
        self.assertEqual(project.stored, {})

    def test_no_store_leaves_the_variable_alone(self):
        project = FakeProjectClient()
        self.assertTrue(preflight.run(FakeRepoClient(), project, store=False).ok)
        self.assertEqual(project.stored, {})

    def test_repository_unreachable(self):
        report = preflight.run(FakeRepoClient(error=GitHubError(404, "Not Found")), FakeProjectClient())
        self.assertFalse(report.ok)
        self.assertIn("cannot reach owner/repo", report.checks[0].message)

    def test_the_workflow_token_does_not_report_write_access_but_the_project_token_does(self):
        # The case of the first real run: GitHub reports no push right for the workflow's own token.
        for info in ({"permissions": {"push": False}}, {}):
            report = preflight.run(FakeRepoClient(info), FakeProjectClient())
            self.assertTrue(report.ok, report.render())
            self.assertIn("confirmed through the project token", report.checks[0].message)

    def test_no_token_reports_write_access(self):
        report = preflight.run(FakeRepoClient({"permissions": {"push": False}}), FakeProjectClient(push=False))
        self.assertFalse(report.checks[0].ok)
        self.assertIn("neither the workflow token nor the project token", report.checks[0].message)

    def test_write_access_cannot_be_confirmed_without_a_project_token(self):
        report = preflight.run(FakeRepoClient({}), FakeProjectClient(token=""))
        self.assertFalse(report.checks[0].ok)
        self.assertIn("no project token to confirm it", report.checks[0].message)

    def test_an_error_from_the_project_token_is_not_write_access(self):
        project = FakeProjectClient(request_error=GitHubError(401, "Bad credentials"))
        report = preflight.run(FakeRepoClient({}), project)
        self.assertFalse(report.checks[0].ok)

    def test_missing_token_skips_the_board_checks(self):
        report = preflight.run(FakeRepoClient(), FakeProjectClient(token=""))
        self.assertEqual([c.skipped for c in report.checks], [False, False, True, True])
        self.assertIn("PROJECT_TOKEN is not set", report.checks[1].message)
        self.assertIsNone(report.board)

    def test_token_that_does_not_work(self):
        project = FakeProjectClient(viewer_error=GitHubError(401, "Bad credentials"))
        report = preflight.run(FakeRepoClient(), project)
        self.assertIn("Bad credentials", report.checks[1].message)
        self.assertTrue(report.checks[2].skipped)

    def test_no_board_stops_at_the_board_step(self):
        report = preflight.run(FakeRepoClient(), FakeProjectClient(boards=[]))
        self.assertIn("no linked board", report.checks[2].message)
        self.assertTrue(report.checks[3].skipped)

    def test_two_boards_ask_the_administrator(self):
        boards = [{"id": "A", "number": 3, "title": "One"}, {"id": "B", "number": 7, "title": "Two"}]
        report = preflight.run(FakeRepoClient(), FakeProjectClient(boards=boards))
        message = report.checks[2].message
        self.assertIn("2 linked boards", message)
        self.assertIn("BOARD_NUMBER", message)
        self.assertTrue(report.checks[3].skipped)

    def test_two_boards_with_the_variable_set_use_that_one(self):
        boards = [{"id": "A", "number": 3, "title": "One"}, {"id": "B", "number": 7, "title": "Two"}]
        report = preflight.run(FakeRepoClient(), FakeProjectClient(boards=boards, variable="7"))
        self.assertTrue(report.ok, report.render())
        self.assertEqual(report.board.id, "B")

    def test_storing_the_variable_can_fail(self):
        project = FakeProjectClient(store_error=GitHubError(403, "Resource not accessible"))
        report = preflight.run(FakeRepoClient(), project)
        self.assertIn("could not store BOARD_NUMBER", report.checks[2].message)

    def test_missing_field_and_value_are_named(self):
        report = preflight.run(FakeRepoClient(), FakeProjectClient(fields=board_fields(missing=["Attention"], drop_value="Merged")))
        message = report.checks[-1].message
        self.assertIn("missing field Attention", message)
        self.assertIn("field Delivery lacks the values Merged", message)
        self.assertIsNone(report.board)

    def test_wrong_field_type_is_named(self):
        fields = board_fields()
        for node in fields:
            if node.get("name") == "Build":
                node["dataType"] = preflight.NUMBER
        report = preflight.run(FakeRepoClient(), FakeProjectClient(fields=fields))
        self.assertIn("field Build is NUMBER, expected TEXT", report.checks[-1].message)

    def test_settings_that_match_the_guide_give_no_warning(self):
        project = quiet_project()
        report = preflight.run(FakeRepoClient(dict(GOOD_SETTINGS)), project)
        self.assertTrue(report.ok, report.render())
        self.assertEqual(report.warnings, [])
        self.assertTrue(project.asked_protection)

    def test_each_setting_that_differs_gives_its_own_warning(self):
        for key, wanted in (("allow_merge_commit", False), ("allow_squash_merge", True), ("allow_rebase_merge", True),
                            ("delete_branch_on_merge", True), ("has_issues", False), ("has_projects", False)):
            info = dict(GOOD_SETTINGS)
            info[key] = wanted
            report = preflight.run(FakeRepoClient(info), quiet_project())
            self.assertTrue(report.ok, key)  # a warning never fails the preflight
            self.assertEqual(len(report.warnings), 1, key)
            self.assertIn(key, report.warnings[0])
            self.assertIn("bootstrap guide, section 3", report.warnings[0])

    def test_a_setting_the_response_lacks_is_skipped(self):
        report = preflight.run(FakeRepoClient({"permissions": {"push": True}}), quiet_project())
        self.assertEqual(report.warnings, [])

    def test_another_default_branch_gives_a_warning(self):
        info = dict(GOOD_SETTINGS, default_branch="master")
        report = preflight.run(FakeRepoClient(info), quiet_project())
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("master", report.warnings[0])

    def test_the_wiki_is_checked_only_when_the_repository_syncs_to_it(self):
        import tempfile

        info = dict(GOOD_SETTINGS, has_wiki=False)
        with tempfile.TemporaryDirectory() as root:
            report = preflight.run(FakeRepoClient(info), quiet_project(), root=root)
            self.assertEqual(report.warnings, [])
            os.makedirs(os.path.join(root, ".github", "workflows"))
            with open(os.path.join(root, preflight.WIKI_SYNC_WORKFLOW), "w", encoding="utf-8") as handle:
                handle.write("name: wiki\n")
            report = preflight.run(FakeRepoClient(info), quiet_project(), root=root)
            self.assertEqual(len(report.warnings), 1)
            self.assertIn("has_wiki", report.warnings[0])

    def test_a_branch_without_protection_gives_a_warning(self):
        report = preflight.run(FakeRepoClient(dict(GOOD_SETTINGS)), quiet_project(protection=GitHubError(404, "Branch not protected")))
        self.assertTrue(report.ok)
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("no protection", report.warnings[0])

    def test_protection_that_cannot_be_read_is_skipped(self):
        for error in (GitHubError(403, "Resource not accessible"), GitHubError(500, "boom")):
            report = preflight.run(FakeRepoClient(dict(GOOD_SETTINGS)), quiet_project(protection=error))
            self.assertEqual(report.warnings, [], error)

    def test_protection_that_differs_from_the_guide_names_each_difference(self):
        weak = {"required_status_checks": {"strict": False}, "enforce_admins": {"enabled": True}}
        report = preflight.run(FakeRepoClient(dict(GOOD_SETTINGS)), quiet_project(protection=weak))
        self.assertTrue(report.ok)
        text = " ".join(report.warnings)
        self.assertIn("does not require a pull request", text)
        self.assertIn("up to date", text)
        self.assertIn("administrators too", text)
        self.assertEqual(len(report.warnings), 3)

    def test_an_unrecognised_protection_answer_is_skipped_and_no_token_asks_nothing(self):
        report = preflight.run(FakeRepoClient(dict(GOOD_SETTINGS)), quiet_project(protection={"something": "else"}))
        self.assertEqual(report.warnings, [])
        project = quiet_project(token="")
        preflight.run(FakeRepoClient(dict(GOOD_SETTINGS)), project)
        self.assertFalse(project.asked_protection)

    def test_the_settings_show_in_the_rendered_report(self):
        info = dict(GOOD_SETTINGS, allow_squash_merge=True)
        report = preflight.run(FakeRepoClient(info), quiet_project())
        self.assertIn("[warning] repository setting allow_squash_merge is on", report.render())
        self.assertIn("preflight: passed", report.render())

    def test_main_needs_the_repository(self):
        saved = os.environ.pop("GITHUB_REPOSITORY", None)
        try:
            self.assertEqual(preflight.main([]), 1)
        finally:
            if saved is not None:
                os.environ["GITHUB_REPOSITORY"] = saved


if __name__ == "__main__":
    unittest.main()
