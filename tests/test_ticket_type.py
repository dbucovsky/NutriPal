"""The ticket Type of a personal repository lives in the board's `Ticket type` field (a project departure from
the standard: the repository has no issue types). These tests cover only that departure."""
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import dates  # noqa: E402
import finalize  # noqa: E402
import github_api  # noqa: E402
import preflight  # noqa: E402
import release  # noqa: E402
import version_numbers  # noqa: E402
import watch  # noqa: E402
from github_api import GitHubError  # noqa: E402


class Transport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, json.loads(body) if body else None))
        status, payload = self.responses.pop(0)
        return status, json.dumps(payload)


class Pager:
    """A project client that returns one page of board items."""

    def __init__(self, nodes):
        self.nodes = nodes

    def graphql(self, query, variables=None):
        assert "Ticket type" in query, "the query must read the Ticket type field"
        return {"node": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": self.nodes}}}


def board():
    fields = {name: {"id": f"F-{name}", "type": kind, "options": {}} for name, (kind, values) in preflight.REQUIRED_FIELDS.items()}
    return preflight.Board("P7", 7, "Governance", fields)


class BoardReaders(unittest.TestCase):
    def test_the_required_fields_include_ticket_type(self):
        kind, values = preflight.REQUIRED_FIELDS["Ticket type"]
        self.assertEqual(kind, preflight.SELECT)
        self.assertEqual(values, ["Feature", "Enhancement", "Change", "Bug", "Refactor", "Task", "Version", "Alert"])

    def test_dates_read_the_board_field(self):
        node = {"id": "I1", "content": {"number": 1, "issueType": None}, "ticketType": {"name": "Version"},
                "status": None, "start": None, "end": None}
        self.assertEqual(dates.board_items(Pager([node]), board())[0]["type"], "Version")

    def test_the_board_field_wins_over_the_issue_type(self):
        node = {"id": "I1", "content": {"number": 1, "issueType": {"name": "Task"}}, "ticketType": {"name": "Bug"},
                "version": None, "number": None}
        self.assertEqual(version_numbers.board_items(Pager([node]), board())[0]["type"], "Bug")

    def test_the_issue_type_is_the_fallback(self):
        node = {"id": "I1", "content": {"number": 1, "issueType": {"name": "Task"}}, "ticketType": None,
                "version": None, "number": None}
        self.assertEqual(version_numbers.board_items(Pager([node]), board())[0]["type"], "Task")

    def test_watch_reads_the_board_field(self):
        node = {"id": "I1", "updatedAt": "2026-10-01T00:00:00Z", "content": {"number": 1, "issueType": None, "comments": {"nodes": []}},
                "ticketType": {"name": "Alert"}, "status": None, "waiting": None, "attention": None, "build": None}
        self.assertEqual(watch.board_tickets(Pager([node]), board())[0]["type"], "Alert")

    def test_release_skips_version_tickets_marked_on_the_board(self):
        node = {"id": "I1", "content": {"number": 1, "issueType": None}, "ticketType": {"name": "Version"},
                "delivery": {"name": "Merged"}, "version": {"text": "V0.1.0"}}
        self.assertEqual(release.releasable_tickets(Pager([node]), board(), release.Version.parse("V0.1.0")), [])


class FakeRepo:
    def __init__(self, types):
        self.types = types

    def issue_type(self, number):
        return self.types.get(number)


class FakeProject:
    repo = "owner/repo"

    def __init__(self, types, fail=False):
        self.types, self.fail = types, fail

    def graphql(self, query, variables=None):
        if self.fail:
            raise GitHubError(502, "Bad gateway")
        kind = self.types.get(variables["num"])
        node = {"id": "I", "project": {"id": "P7"}, "ticketType": {"name": kind} if kind else None}
        return {"repository": {"issue": {"id": "N", "title": "t", "projectItems": {"nodes": [node]}}}}


class BoardTypes(unittest.TestCase):
    def test_the_board_field_is_read_first(self):
        source = finalize.BoardTypes(FakeRepo({1: "Task"}), FakeProject({1: "Feature"}), board())
        self.assertEqual(source.issue_type(1), "Feature")

    def test_the_issue_type_is_the_fallback(self):
        source = finalize.BoardTypes(FakeRepo({1: "Task"}), FakeProject({}), board())
        self.assertEqual(source.issue_type(1), "Task")

    def test_without_a_board_only_the_issue_type_is_used(self):
        self.assertEqual(finalize.BoardTypes(FakeRepo({1: "Bug"})).issue_type(1), "Bug")
        self.assertIsNone(finalize.BoardTypes(FakeRepo({})).issue_type(1))

    def test_a_board_error_falls_back(self):
        source = finalize.BoardTypes(FakeRepo({1: "Task"}), FakeProject({}, fail=True), board())
        self.assertEqual(source.issue_type(1), "Task")


class Client(unittest.TestCase):
    def test_an_issue_is_created_without_a_type_the_repository_refuses(self):
        transport = Transport((422, {"message": "Validation Failed"}), (201, {"number": 9}))
        created = github_api.Client("t", "me/repo", transport).create_issue("T", "B", "Version")
        self.assertEqual(created["number"], 9)
        self.assertIn("type", transport.calls[0][2])
        self.assertNotIn("type", transport.calls[1][2])

    def test_other_errors_still_raise(self):
        transport = Transport((500, {"message": "boom"}))
        with self.assertRaises(GitHubError):
            github_api.Client("t", "me/repo", transport).create_issue("T", "B", "Version")

    def test_the_project_paths_follow_the_owner(self):
        personal = github_api.Client("t", "me/repo", Transport((200, {"type": "User", "id": 42})))
        self.assertEqual(personal.project_base(), "/users/me")
        organization = github_api.Client("t", "org/repo", Transport((200, {"type": "Organization", "id": 7})))
        self.assertEqual(organization.project_base(), "/orgs/org")


if __name__ == "__main__":
    unittest.main()
