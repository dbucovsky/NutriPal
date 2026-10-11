"""The colour and description of every board option (a project addition: doc/2026-10-10_board-option-colors.md)."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import fields  # noqa: E402
import finalize  # noqa: E402
import github_api  # noqa: E402
import option_styles  # noqa: E402
import preflight  # noqa: E402

COLORS = {"GRAY", "BLUE", "GREEN", "YELLOW", "ORANGE", "RED", "PINK", "PURPLE"}


def required_options():
    return [(field, value) for field, (kind, values) in preflight.REQUIRED_FIELDS.items() if values for value in values]


def board(extra=None):
    found = {}
    for name, (kind, values) in preflight.REQUIRED_FIELDS.items():
        options = {v: f"{name}-{v}" for v in (values or [])}
        if extra and name == extra[0]:
            options[extra[1]] = "OLD"
        found[name] = {"id": f"F-{name}", "type": kind, "options": options}
    return preflight.Board("P7", 7, "Governance", found)


class Tables(unittest.TestCase):
    def test_every_required_option_has_a_known_colour_and_a_description(self):
        for field, value in required_options():
            with self.subTest(field=field, value=value):
                self.assertIn(preflight.OPTION_COLORS.get(value), COLORS)
                self.assertTrue(preflight.OPTION_DESCRIPTIONS.get(value, "").strip())

    def test_option_names_are_unique_across_fields_and_the_tables_hold_nothing_else(self):
        names = [value for _, value in required_options()]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(preflight.OPTION_COLORS))
        self.assertEqual(set(names), set(preflight.OPTION_DESCRIPTIONS))

    def test_the_attention_colours_are_the_standards(self):
        got = {v: preflight.OPTION_COLORS[v] for v in preflight.REQUIRED_FIELDS["Attention"][1]}
        self.assertEqual(got, {"Fine": "GREEN", "Acknowledged": "PURPLE", "Watch": "YELLOW", "Caution": "ORANGE", "AtRisk": "RED"})


class Plan(unittest.TestCase):
    def test_each_option_is_sent_with_its_id_colour_and_description(self):
        by_field = {name: options for name, _, options in option_styles.plan(board())}
        self.assertEqual(set(by_field), {f for f, (k, v) in preflight.REQUIRED_FIELDS.items() if k == preflight.SELECT})
        self.assertEqual(by_field["Size"][0], ("Size-XS", "XS", preflight.OPTION_COLORS["XS"], preflight.OPTION_DESCRIPTIONS["XS"]))

    def test_an_option_not_in_the_tables_is_kept(self):
        options = dict((n, o) for n, _, o in option_styles.plan(board(("Size", "XXL"))))["Size"]
        self.assertIn(("OLD", "XXL", "GRAY", ""), options)

    def test_a_field_missing_from_the_board_is_skipped(self):
        b = board()
        del b.fields["Size"]
        self.assertNotIn("Size", [n for n, _, _ in option_styles.plan(b)])


class Calls(unittest.TestCase):
    class Project:
        def __init__(self):
            self.calls = []

        def set_options(self, field_id, options):
            self.calls.append((field_id, options))

    def test_a_dry_run_changes_nothing(self):
        project, run = self.Project(), finalize.Runner(True)
        option_styles.apply(run, project, board())
        self.assertEqual(project.calls, [])
        self.assertEqual(len(run.log), 10)

    def test_apply_sets_every_field(self):
        project, run = self.Project(), finalize.Runner(False)
        option_styles.apply(run, project, board())
        self.assertEqual(len(project.calls), 10)

    def test_a_new_field_gets_the_colours_and_descriptions(self):
        class Client:
            def __init__(self):
                self.created = []

            def create_field(self, project_id, name, data_type, options=()):
                self.created.append(list(options))

        client, run = Client(), finalize.Runner(False)
        fields.create(run, client, board(), [("Waiting", "SINGLE_SELECT", ["Needs input"])])
        self.assertEqual(client.created, [[("Needs input", "ORANGE", preflight.OPTION_DESCRIPTIONS["Needs input"])]])


class Mutation(unittest.TestCase):
    def test_existing_options_are_sent_with_their_id(self):
        sent = []

        def transport(method, url, headers, body):
            import json
            sent.append(json.loads(body))
            return 200, json.dumps({"data": {}}), {}

        github_api.Client("t", "o/r", transport).set_options("F1", [("OPT1", "A", "RED", "first"), (None, "B", "BLUE", "second")])
        options = sent[0]["variables"]["o"]
        self.assertEqual(options[0], {"id": "OPT1", "name": "A", "color": "RED", "description": "first"})
        self.assertNotIn("id", options[1])


if __name__ == "__main__":
    unittest.main()
