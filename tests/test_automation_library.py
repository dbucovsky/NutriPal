import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import changelog  # noqa: E402
import github_api  # noqa: E402
import versions  # noqa: E402
from versions import Version  # noqa: E402

SAMPLE = """# Changelog

## WIP-Version +s
### WIP-Build
#### #12 — Add the library
- library: added.
#### REF 20261006091500 — no ticket yet
- typo fixed.

## V0.2.0 — 2026-10-05 21:24 UTC
### Build 20261005211638 (branch apply-governance-to-itself)
#### #4 — Add the pull request template
- template: added.
#### #5 — Add AGENTS.md
- AGENTS.md: added.
### Build 20261005200000 (branch apply-governance-to-itself)
#### #4 — Add the pull request template
- template: first draft.
#### AUTO-REF 20261005164000 (tracked as #187)
- Auto-flagged.

## V0.1.0 — 2026-10-05 18:22 UTC
### Build 20261005181657 (branch initial-structure)
#### #1 — Initial structure of the project
- guides/: added.
"""


class VersionTests(unittest.TestCase):
    def test_parse_and_format(self):
        self.assertEqual(str(Version.parse("V2.4.1")), "V2.4.1")
        self.assertEqual(str(Version.parse("V1.25.0-HF1")), "V1.25.0-HF1")
        with self.assertRaises(versions.VersionError):
            Version.parse("2.4.1")

    def test_number(self):
        self.assertEqual(Version.parse("V0.1.0").number(), 10000)
        self.assertEqual(Version.parse("V0.2.0").number(), 20000)
        self.assertEqual(Version.parse("V1.25.3-HF2").number(), 10_000_000 + 250_000 + 30 + 2)

    def test_bump_from_types(self):
        latest = Version(0, 2, 0)
        self.assertEqual(str(versions.next_version(latest, ["Task", "Bug"])), "V0.2.1")
        self.assertEqual(str(versions.next_version(latest, ["Bug", "Feature"])), "V0.3.0")
        self.assertEqual(str(versions.next_version(latest, ["Enhancement"])), "V0.3.0")

    def test_no_typed_tickets_is_a_mod(self):
        latest = Version(1, 4, 2)
        self.assertEqual(str(versions.next_version(latest, [])), "V1.4.3")
        self.assertEqual(str(versions.next_version(latest, ["Version", "Alert"])), "V1.4.3")

    def test_marker_overrides_in_both_directions(self):
        latest = Version(1, 4, 2)
        self.assertEqual(str(versions.next_version(latest, ["Task"], "+s")), "V1.5.0")
        self.assertEqual(str(versions.next_version(latest, ["Feature"], "+m")), "V1.4.3")
        self.assertEqual(str(versions.next_version(latest, ["Task"], "+V")), "V2.0.0")

    def test_major_is_never_automatic(self):
        self.assertEqual(str(versions.next_version(Version(1, 0, 0), ["Feature", "Bug"])), "V1.1.0")

    def test_first_version_ignores_types(self):
        self.assertEqual(str(versions.next_version(None, ["Task"])), "V0.1.0")
        self.assertEqual(str(versions.next_version(None, ["Feature", "Bug"])), "V0.1.0")

    def test_unknown_type_or_marker_is_an_error(self):
        with self.assertRaises(versions.VersionError):
            versions.next_version(Version(1, 0, 0), ["Epic"])
        with self.assertRaises(versions.VersionError):
            versions.next_version(Version(1, 0, 0), [], "+x")

    def test_timestamps_are_utc(self):
        moment = datetime(2026, 10, 5, 14, 32, 45, tzinfo=timezone(timedelta(hours=-4)))
        self.assertEqual(versions.stamp(moment), "20261005183245")
        self.assertEqual(versions.heading_time(moment), "2026-10-05 18:32")


class ChangelogTests(unittest.TestCase):
    def test_parse_sections(self):
        sections = changelog.parse(SAMPLE)
        self.assertEqual([s.kind for s in sections], ["wip", "final", "final"])
        wip = changelog.open_section(sections)
        self.assertEqual(wip.marker, "+s")
        self.assertEqual(wip.ticket_numbers(), [12])
        self.assertEqual(str(changelog.latest_final(sections).version), "V0.2.0")

    def test_blocks_and_builds(self):
        sections = changelog.parse(SAMPLE)
        wip, v2, _ = sections
        self.assertEqual([b.kind for b in wip.blocks()], ["ticket", "ref"])
        self.assertEqual(wip.blocks()[0].body, ["- library: added."])
        self.assertEqual(wip.blocks()[1].token, "20261006091500")
        self.assertEqual(wip.last_build(), None)
        self.assertEqual(v2.ticket_numbers(), [4, 5])
        self.assertEqual(v2.last_build(), "20261005211638")
        self.assertEqual(v2.blocks()[-1].kind, "autoref")
        self.assertEqual(v2.blocks()[-1].number, 187)

    def test_no_open_heading(self):
        sections = changelog.parse(SAMPLE.replace("## WIP-Version +s", "## V0.3.0 — 2026-10-06 10:00 UTC"))
        self.assertIsNone(changelog.open_section(sections))

    def test_rename_open_heading(self):
        text = changelog.rename_open_heading(SAMPLE, Version(0, 3, 0), "2026-10-06 10:00")
        self.assertIn("## V0.3.0 — 2026-10-06 10:00 UTC\n### WIP-Build", text)
        self.assertNotIn("WIP-Version", text)
        self.assertEqual(str(changelog.latest_final(changelog.parse(text)).version), "V0.3.0")

    def test_rename_without_open_heading_is_an_error(self):
        with self.assertRaises(changelog.ChangelogError):
            changelog.rename_open_heading("# Changelog\n\n## V0.1.0 — 2026-10-05 18:22 UTC\n", Version(0, 2, 0), "x")

    def test_stamp_wip_build(self):
        text = changelog.stamp_wip_build(SAMPLE, "20261006101112", "my-branch")
        self.assertIn("### Build 20261006101112 (branch my-branch)", text)
        self.assertNotIn("### WIP-Build", text)
        with self.assertRaises(changelog.ChangelogError):
            changelog.stamp_wip_build(text, "20261006101113", "my-branch")

    def test_windows_line_endings_are_read_and_kept(self):
        crlf = SAMPLE.replace("\n", "\r\n")
        sections = changelog.parse(crlf)
        self.assertEqual(changelog.open_section(sections).ticket_numbers(), [12])
        stamped = changelog.stamp_wip_build(crlf, "20261006101112", "b")
        self.assertIn("### Build 20261006101112 (branch b)\r\n", stamped)
        renamed = changelog.rename_open_heading(crlf, Version(0, 3, 0), "2026-10-06 10:00")
        self.assertIn("## V0.3.0 \u2014 2026-10-06 10:00 UTC\r\n", renamed)
        self.assertEqual(renamed.count("\r\n"), crlf.count("\r\n"))

    def test_text_after_wip_version_is_an_error(self):
        with self.assertRaises(changelog.ChangelogError):
            changelog.parse(SAMPLE.replace("## WIP-Version +s", "## WIP-Version +x"))
        with self.assertRaises(changelog.ChangelogError):
            changelog.parse(SAMPLE.replace("## WIP-Version +s", "## WIP-Version soon"))

    def test_two_open_headings_are_an_error(self):
        with self.assertRaises(changelog.ChangelogError):
            changelog.parse(SAMPLE.replace("## V0.2.0 — 2026-10-05 21:24 UTC", "## WIP-Version"))

    def test_unrecognized_headings_are_errors(self):
        with self.assertRaises(changelog.ChangelogError):
            changelog.parse(SAMPLE.replace("### Build 20261005181657 (branch initial-structure)", "### Build today"))
        with self.assertRaises(changelog.ChangelogError):
            changelog.parse(SAMPLE.replace("#### #1 — Initial structure of the project", "#### ticket one"))

    def test_the_repository_changelog_parses(self):
        with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as handle:
            sections = changelog.parse(handle.read())
        final = {str(s.version): s for s in sections if s.kind == "final"}
        self.assertEqual(final["V0.1.0"].version.number(), 10000)
        self.assertEqual(final["V0.14.2"].version.number(), 140020)
        self.assertEqual(final["V0.14.2"].ticket_numbers(), [])  # its change had no ticket: a REF block
        self.assertEqual(final["V0.14.1"].last_build(), "20260911184736")  # the UTC time of commit b6f5c5b
        self.assertEqual(final["V0.1.0"].ticket_numbers(), [46, 47, 48])


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, json.loads(body) if body else None))
        return self.responses.pop(0)


def ok(payload, status=200):
    return status, json.dumps(payload)


class ClientTests(unittest.TestCase):
    def client(self, *responses):
        transport = FakeTransport(*responses)
        return github_api.Client("token", "owner/repo", transport), transport

    def test_request_sends_auth_and_body(self):
        client, transport = self.client(ok({"number": 7}))
        client.create_issue("Title", "Body", issue_type="Version", labels=["process"], assignees=["me"])
        method, url, headers, body = transport.calls[0]
        self.assertEqual((method, url), ("POST", "https://api.github.com/repos/owner/repo/issues"))
        self.assertEqual(headers["Authorization"], "Bearer token")
        self.assertEqual(body["type"], "Version")
        self.assertEqual(body["labels"], ["process"])

    def test_errors_carry_the_status_and_message(self):
        client, _ = self.client(ok({"message": "Not Found"}, 404))
        with self.assertRaises(github_api.GitHubError) as caught:
            client.issue(1)
        self.assertEqual(caught.exception.status, 404)
        self.assertIn("Not Found", str(caught.exception))

    def test_issue_type(self):
        client, _ = self.client(ok({"type": {"name": "Task"}}), ok({"type": None}))
        self.assertEqual(client.issue_type(4), "Task")
        self.assertIsNone(client.issue_type(5))

    def test_sub_issue_looks_up_the_child_id(self):
        client, transport = self.client(ok({"id": 999}), ok({}))
        client.add_sub_issue(11, 4)
        self.assertEqual(transport.calls[1][1], "https://api.github.com/repos/owner/repo/issues/11/sub_issues")
        self.assertEqual(transport.calls[1][3], {"sub_issue_id": 999})

    def test_close_issue_and_tag(self):
        client, transport = self.client(ok({}), ok({}))
        client.close_issue(3)
        client.create_tag("archived/2026-10-05_branch", "abc123")
        self.assertEqual(transport.calls[0][3], {"state": "closed", "state_reason": "completed"})
        self.assertEqual(transport.calls[1][3], {"ref": "refs/tags/archived/2026-10-05_branch", "sha": "abc123"})

    def test_variable_is_created_when_missing(self):
        client, transport = self.client(ok({"message": "Not Found"}, 404), ok({}, 201))
        client.set_variable("BOARD_NUMBER", "7")
        self.assertEqual([c[0] for c in transport.calls], ["PATCH", "POST"])

    def test_get_variable(self):
        client, _ = self.client(ok({"value": "7"}), ok({"message": "Not Found"}, 404))
        self.assertEqual(client.get_variable("BOARD_NUMBER"), "7")
        self.assertIsNone(client.get_variable("BOARD_NUMBER"))

    def test_graphql_errors_raise(self):
        client, _ = self.client(ok({"errors": [{"message": "bad field"}]}))
        with self.assertRaises(github_api.GitHubError):
            client.graphql("{ viewer { login } }")

    def test_token_expiry_comes_from_the_response_header(self):
        header = {"github-authentication-token-expiration": "2026-11-04 17:15:13 UTC"}
        client, _ = self.client((200, json.dumps({"login": "me"}), header))
        self.assertIsNone(client.token_expiry())
        client.request("GET", "/user")
        self.assertEqual(client.token_expiry(), datetime(2026, 11, 4, 17, 15, 13, tzinfo=timezone.utc))
        client, _ = self.client(ok({}))
        client.request("GET", "/user")
        self.assertIsNone(client.token_expiry())

    def test_set_project_field(self):
        client, transport = self.client(ok({"data": {"updateProjectV2ItemFieldValue": {}}}))
        client.set_project_field("P", "I", "F", {"text": "V0.3.0"})
        variables = transport.calls[0][3]["variables"]
        self.assertEqual(variables, {"p": "P", "i": "I", "f": "F", "v": {"text": "V0.3.0"}})


if __name__ == "__main__":
    unittest.main()
