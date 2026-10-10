import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import fields  # noqa: E402
import finalize  # noqa: E402
import preflight  # noqa: E402
from github_api import Client  # noqa: E402


def full_board(without=(), drop=None, retype=None):
    """A board that has every required field, unless told otherwise."""
    found = {}
    for name, (kind, values) in preflight.REQUIRED_FIELDS.items():
        if name in without:
            continue
        options = {v: f"{name}-{v}" for v in (values or []) if v != drop}
        found[name] = {"id": f"F-{name}", "type": retype.get(name, kind) if retype else kind, "options": options}
    return preflight.Board("P7", 7, "Governance", found)


class FakeProject:
    repo = "owner/repo"

    def __init__(self):
        self.created = []

    def create_field(self, project_id, name, data_type, options=()):
        self.created.append((project_id, name, data_type, list(options)))


class PlanTests(unittest.TestCase):
    def test_a_complete_board_needs_nothing(self):
        self.assertEqual(fields.plan(full_board()), ([], []))

    def test_a_missing_text_field_is_planned_without_values(self):
        self.assertEqual(fields.plan(full_board(without=("Fix",))), ([("Fix", "TEXT", [])], []))

    def test_a_missing_single_select_field_is_planned_with_all_its_values_in_order(self):
        missing, differing = fields.plan(full_board(without=("Size",)))
        self.assertEqual(missing, [("Size", "SINGLE_SELECT", ["XS", "S", "M", "L", "XL"])])
        self.assertEqual(differing, [])

    def test_several_missing_fields_keep_the_order_of_the_table(self):
        missing, _ = fields.plan(full_board(without=("Build", "Origin", "Fix")))
        self.assertEqual([m[0] for m in missing], ["Origin", "Build", "Fix"])

    def test_a_field_of_the_wrong_type_or_lacking_a_value_is_reported_and_never_changed(self):
        missing, differing = fields.plan(full_board(drop="Wishlist", retype={"Build": "NUMBER"}))
        self.assertEqual(missing, [])
        text = " ".join(differing)
        self.assertIn("field Build is NUMBER, expected TEXT", text)
        self.assertIn("field Priority lacks the values Wishlist", text)

    def test_the_built_in_status_field_is_never_created(self):
        missing, differing = fields.plan(full_board(without=("Status",)))
        self.assertEqual(missing, [])
        self.assertIn("built-in field Status", differing[0])


class CreateTests(unittest.TestCase):
    def test_a_dry_run_creates_nothing_and_says_what_it_would(self):
        project, run = FakeProject(), finalize.Runner(True)
        names = fields.create(run, project, full_board(), [("Fix", "TEXT", [])])
        self.assertEqual((names, project.created), (["Fix"], []))
        self.assertEqual(run.log, ["create the field Fix (TEXT)"])

    def test_a_real_run_creates_each_field_with_the_guides_colours(self):
        project, run = FakeProject(), finalize.Runner(False)
        missing = [("Fix", "TEXT", []), ("Attention", "SINGLE_SELECT", ["Fine", "Acknowledged", "Watch", "Caution", "AtRisk"]),
                   ("Size", "SINGLE_SELECT", ["XS", "S"])]
        fields.create(run, project, full_board(), missing)
        self.assertEqual(project.created[0], ("P7", "Fix", "TEXT", []))
        colours = dict(project.created[1][3])
        self.assertEqual(colours, {"Fine": "GREEN", "Acknowledged": "PURPLE", "Watch": "YELLOW", "Caution": "ORANGE", "AtRisk": "RED"})
        self.assertEqual(project.created[2][3], [("XS", "GRAY"), ("S", "GRAY")])
        self.assertIn("create the field Size (SINGLE_SELECT: XS, S)", run.log)


class ClientTests(unittest.TestCase):
    def client(self):
        self.sent = []

        def transport(method, url, headers, body):
            self.sent.append(json.loads(body.decode("utf-8")))
            return 200, json.dumps({"data": {"createProjectV2Field": {"projectV2Field": {"id": "F1", "name": "x"}}}}), {}

        return Client("t", "owner/repo", transport=transport)

    def test_a_text_field_is_created_without_options(self):
        client = self.client()
        self.assertEqual(client.create_field("P7", "Fix", "TEXT"), {"id": "F1", "name": "x"})
        sent = self.sent[0]
        self.assertIn("createProjectV2Field", sent["query"])
        self.assertEqual(sent["variables"], {"p": "P7", "n": "Fix", "t": "TEXT"})

    def test_a_single_select_field_is_created_with_a_name_a_colour_and_a_description_per_option(self):
        client = self.client()
        client.create_field("P7", "Waiting", "SINGLE_SELECT", [("Needs input", "GRAY")])
        self.assertEqual(self.sent[0]["variables"]["o"], [{"name": "Needs input", "color": "GRAY", "description": ""}])


class MainTests(unittest.TestCase):
    def test_main_needs_the_repository(self):
        saved = os.environ.pop("GITHUB_REPOSITORY", None)
        try:
            self.assertEqual(fields.main([]), 1)
        finally:
            if saved is not None:
                os.environ["GITHUB_REPOSITORY"] = saved


if __name__ == "__main__":
    unittest.main()
