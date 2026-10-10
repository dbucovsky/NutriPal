import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

import board_pull_requests  # noqa: E402
import finalize  # noqa: E402
import preflight  # noqa: E402


class FakeProject:
    repo = "owner/repo"

    def __init__(self, numbers=()):
        self.numbers, self.added, self.asked = set(numbers), [], []

    def graphql(self, query, variables=None):
        self.asked.append(variables["num"])
        items = [{"project": {"id": "P7"}}, {"project": {"id": "OTHER"}}] if variables["num"] in self.numbers else [{"project": {"id": "OTHER"}}]
        return {"repository": {"pullRequest": {"projectItems": {"nodes": items}}}}

    def add_to_project(self, project_id, content_id):
        self.added.append(content_id)
        return "item"


class FakeRepo:
    repo = "owner/repo"

    def __init__(self, count):
        self.pulls = [{"number": n, "node_id": f"PR{n}"} for n in range(1, count + 1)]
        self.paths = []

    def repo_path(self, path):
        return path

    def request(self, method, path, body=None):
        self.paths.append(path)
        page = int(path.split("&page=")[1])
        size = board_pull_requests.PER_PAGE
        return self.pulls[(page - 1) * size:page * size]


def board():
    fields = {name: {"id": f"F-{name}", "type": kind, "options": {}} for name, (kind, values) in preflight.REQUIRED_FIELDS.items()}
    return preflight.Board("P7", 7, "Governance", fields)


def add(project, pulls, dry_run=False):
    run = finalize.Runner(dry_run)
    board_pull_requests.add(run, project, board(), pulls)
    return run


class AddTests(unittest.TestCase):
    def test_a_pull_request_that_is_not_on_the_board_is_added(self):
        project = FakeProject()
        run = add(project, [(68, "PR68")])
        self.assertEqual(project.added, ["PR68"])
        self.assertEqual(run.log, ["#68: add the pull request to the board"])

    def test_one_that_is_already_there_is_left_alone(self):
        project = FakeProject([68])
        run = add(project, [(68, "PR68"), (64, "PR64")])
        self.assertEqual(project.added, ["PR64"])
        self.assertIn("#68: the pull request is already on the board", run.log)

    def test_a_second_run_adds_nothing(self):
        project = FakeProject([2, 10])
        add(project, [(2, "PR2"), (10, "PR10")])
        self.assertEqual(project.added, [])

    def test_a_dry_run_changes_nothing(self):
        project = FakeProject()
        run = add(project, [(2, "PR2")], dry_run=True)
        self.assertEqual(project.added, [])
        self.assertEqual(run.log, ["#2: add the pull request to the board"])

    def test_each_pull_request_is_asked_about_itself(self):
        project = FakeProject([5])
        add(project, [(5, "PR5"), (9, "PR9")])
        self.assertEqual(project.asked, [5, 9])
        self.assertEqual(project.added, ["PR9"])

    def test_an_item_in_another_board_does_not_count(self):
        project = FakeProject()
        add(project, [(1, "PR1")])
        self.assertEqual(project.added, ["PR1"])

    def test_a_pull_request_the_api_does_not_know_is_added(self):
        project = FakeProject()
        project.graphql = lambda query, variables=None: {"repository": {"pullRequest": None}}
        add(project, [(3, "PR3")])
        self.assertEqual(project.added, ["PR3"])

    def test_the_pull_requests_are_added_in_number_order(self):
        project = FakeProject()
        add(project, [(10, "PR10"), (2, "PR2")])
        self.assertEqual(project.added, ["PR2", "PR10"])


class ListingTests(unittest.TestCase):
    def test_every_page_of_pull_requests_is_read(self):
        repo = FakeRepo(250)
        pulls = board_pull_requests.all_pull_requests(repo)
        self.assertEqual(len(pulls), 250)
        self.assertEqual(pulls[0], (1, "PR1"))
        self.assertEqual(len(repo.paths), 3)

    def test_a_repository_without_pull_requests(self):
        self.assertEqual(board_pull_requests.all_pull_requests(FakeRepo(0)), [])

    def test_exactly_one_full_page_asks_for_the_next(self):
        repo = FakeRepo(board_pull_requests.PER_PAGE)
        self.assertEqual(len(board_pull_requests.all_pull_requests(repo)), 100)
        self.assertEqual(len(repo.paths), 2)


class MainTests(unittest.TestCase):
    def run_main(self, args, env):
        saved = {key: os.environ.get(key) for key in ("GITHUB_REPOSITORY", "PULL_REQUEST", "PULL_REQUEST_NODE_ID")}
        try:
            for key in saved:
                os.environ.pop(key, None)
            os.environ.update(env)
            return board_pull_requests.main(args)
        finally:
            for key, value in saved.items():
                os.environ.pop(key, None)
                if value is not None:
                    os.environ[key] = value

    def test_it_needs_a_repository(self):
        self.assertEqual(self.run_main([], {}), 1)

    def test_it_needs_a_pull_request_or_all(self):
        self.assertEqual(self.run_main([], {"GITHUB_REPOSITORY": "owner/repo"}), 1)


if __name__ == "__main__":
    unittest.main()
