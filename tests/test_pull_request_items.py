"""A pull request is on the board only so that the All view has no gaps in the numbers. A board item whose content is
a pull request (GraphQL returns an empty content for it, because the sweeps ask for issue fields only) or a draft must
be skipped by every sweep."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import dates  # noqa: E402
import conditions  # noqa: E402
import implemented  # noqa: E402
import preflight  # noqa: E402
import version_numbers  # noqa: E402
import watch  # noqa: E402

FIELDS = {"status": {"name": "InProgress"}, "delivery": {"name": "Implemented"}, "version": {"text": "V1.0.0"},
          "waiting": {"name": "Needs input"}, "attention": {"name": "Watch"}, "resolution": {"name": "Done"},
          "start": {"date": "2026-10-01"}, "end": {"date": "2026-10-02"}, "build": {"text": "20261001000000"},
          "updatedAt": "2026-10-01T00:00:00Z"}
PULL_REQUEST = dict(FIELDS, id="PRI", content={})
DRAFT = dict(FIELDS, id="DI", content=None)


class FakeProject:
    repo = "owner/repo"

    def graphql(self, query, variables=None):
        return {"node": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [PULL_REQUEST, DRAFT]}}}


def board():
    fields = {name: {"id": f"F-{name}", "type": kind, "options": {}} for name, (kind, values) in preflight.REQUIRED_FIELDS.items()}
    return preflight.Board("P7", 7, "Governance", fields)


class SweepsSkipItemsThatAreNotIssues(unittest.TestCase):
    def test_the_date_sweep(self):
        self.assertEqual(dates.board_items(FakeProject(), board()), [])

    def test_the_watch_sweep(self):
        self.assertEqual(watch.board_tickets(FakeProject(), board()), [])

    def test_the_refresh_of_the_conditions(self):
        self.assertEqual(conditions.board_tickets(FakeProject(), board()), [])

    def test_the_implemented_sweep(self):
        self.assertEqual(implemented.unattached(FakeProject(), board()), [])

    def test_the_version_number_sweep(self):
        self.assertEqual(version_numbers.board_items(FakeProject(), board()), [])


if __name__ == "__main__":
    unittest.main()
