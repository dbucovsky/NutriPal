"""A small GitHub client: REST and GraphQL calls for issues, sub-issues, project fields,
tags and repository variables. It needs only the standard library.

Token permissions each call needs:
- issues, sub-issues, comments: issues write (the workflow's own token)
- tags: contents write (the workflow's own token)
- repository variables: the project token (repo scope)
- project fields and views: the project token (project scope)
"""
import json
from datetime import datetime, timezone
import urllib.error
import urllib.request

API = "https://api.github.com"


class GitHubError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(f"GitHub returned {status}: {message}")
        self.status = status


def _urllib_transport(method, url, headers, body):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read().decode("utf-8"), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8"), dict(error.headers)


class Client:
    """`transport(method, url, headers, body) -> (status, text[, response headers])` can be replaced in tests."""

    def __init__(self, token, repo, transport=None, api=API):
        self.token, self.repo, self.api = token, repo, api
        self.transport = transport or _urllib_transport
        self.last_headers = {}

    def request(self, method, path, body=None):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "versioning-automation",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        result = self.transport(method, self.api + path, headers, data)
        status, text = result[0], result[1]
        self.last_headers = {k.lower(): v for k, v in (result[2] if len(result) > 2 else {}).items()}
        payload = json.loads(text) if text.strip() else None
        if status >= 300:
            message = payload.get("message") if isinstance(payload, dict) else text
            raise GitHubError(status, message)
        return payload

    def token_expiry(self):
        """When the token expires, from the header of the latest response (None if it never does)."""
        text = self.last_headers.get("github-authentication-token-expiration")
        if not text:
            return None
        return datetime.strptime(text.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

    def graphql(self, query, variables=None):
        payload = self.request("POST", "/graphql", {"query": query, "variables": variables or {}})
        if payload.get("errors"):
            raise GitHubError(200, "; ".join(error["message"] for error in payload["errors"]))
        return payload["data"]

    def repo_path(self, path):
        return f"/repos/{self.repo}{path}"

    # Issues
    def issue(self, number):
        return self.request("GET", self.repo_path(f"/issues/{number}"))

    def issue_type(self, number):
        issue_type = self.issue(number).get("type")
        return issue_type["name"] if issue_type else None

    def create_issue(self, title, body, issue_type=None, labels=(), assignees=()):
        data = {"title": title, "body": body, "labels": list(labels), "assignees": list(assignees)}
        if issue_type:
            data["type"] = issue_type
        return self.request("POST", self.repo_path("/issues"), data)

    def close_issue(self, number, reason="completed"):
        return self.request("PATCH", self.repo_path(f"/issues/{number}"), {"state": "closed", "state_reason": reason})

    def comment(self, number, body):
        return self.request("POST", self.repo_path(f"/issues/{number}/comments"), {"body": body})

    def add_sub_issue(self, parent, child):
        child_id = self.issue(child)["id"]
        return self.request("POST", self.repo_path(f"/issues/{parent}/sub_issues"), {"sub_issue_id": child_id})

    # Tags
    def create_tag(self, name, sha):
        return self.request("POST", self.repo_path("/git/refs"), {"ref": f"refs/tags/{name}", "sha": sha})

    def delete_ref(self, ref):
        """Delete a branch or tag by its full name, for example `heads/old-work` or `tags/released/V9.9.9`."""
        return self.request("DELETE", self.repo_path(f"/git/refs/{ref}"))

    # Repository variables
    def set_variable(self, name, value):
        try:
            return self.request("PATCH", self.repo_path(f"/actions/variables/{name}"), {"name": name, "value": value})
        except GitHubError as error:
            if error.status != 404:
                raise
        return self.request("POST", self.repo_path("/actions/variables"), {"name": name, "value": value})

    def get_variable(self, name):
        try:
            return self.request("GET", self.repo_path(f"/actions/variables/{name}"))["value"]
        except GitHubError as error:
            if error.status == 404:
                return None
            raise

    # Project (board) fields
    def add_to_project(self, project_id, content_id):
        query = ("mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c})"
                 "{item{id}}}")
        return self.graphql(query, {"p": project_id, "c": content_id})["addProjectV2ItemById"]["item"]["id"]

    def set_project_field(self, project_id, item_id, field_id, value):
        """`value` is one of {"singleSelectOptionId": ...}, {"text": ...}, {"number": ...}, {"date": ...}."""
        query = ("mutation($p:ID!,$i:ID!,$f:ID!,$v:ProjectV2FieldValue!){updateProjectV2ItemFieldValue("
                 "input:{projectId:$p,itemId:$i,fieldId:$f,value:$v}){projectV2Item{id}}}")
        return self.graphql(query, {"p": project_id, "i": item_id, "f": field_id, "v": value})

    def clear_project_field(self, project_id, item_id, field_id):
        query = ("mutation($p:ID!,$i:ID!,$f:ID!){clearProjectV2ItemFieldValue("
                 "input:{projectId:$p,itemId:$i,fieldId:$f}){projectV2Item{id}}}")
        return self.graphql(query, {"p": project_id, "i": item_id, "f": field_id})

    def create_field(self, project_id, name, data_type, options=()):
        """Create a board field of `data_type` (TEXT, NUMBER, DATE or SINGLE_SELECT); `options` is [(name, color)]
        for a single-select field. Returns the new field's id and name."""
        query = ("mutation($p:ID!,$n:String!,$t:ProjectV2CustomFieldType!,$o:[ProjectV2SingleSelectFieldOptionInput!]){"
                 "createProjectV2Field(input:{projectId:$p,name:$n,dataType:$t,singleSelectOptions:$o})"
                 "{projectV2Field{... on ProjectV2Field{id name} ... on ProjectV2SingleSelectField{id name}}}}")
        variables = {"p": project_id, "n": name, "t": data_type}
        if data_type == "SINGLE_SELECT":
            variables["o"] = [{"name": option, "color": color, "description": ""} for option, color in options]
        return self.graphql(query, variables)["createProjectV2Field"]["projectV2Field"]

    def set_project_description(self, project_id, text):
        """Set the project's short description (the board's "last checked" stamp lives there)."""
        query = ("mutation($p:ID!,$d:String!){updateProjectV2(input:{projectId:$p,shortDescription:$d})"
                 "{projectV2{id shortDescription}}}")
        return self.graphql(query, {"p": project_id, "d": text})["updateProjectV2"]["projectV2"]

    def list_comments(self, number):
        """The comments of an issue, oldest first, as GitHub returns them (id, body, user, created_at)."""
        found, page = [], 1
        while True:
            chunk = self.request("GET", self.repo_path(f"/issues/{number}/comments?per_page=100&page={page}"))
            found += chunk
            if len(chunk) < 100:
                return found
            page += 1

    def edit_comment(self, comment_id, body):
        return self.request("PATCH", self.repo_path(f"/issues/comments/{comment_id}"), {"body": body})

    # Project (board) views
    def project_views(self, project_id):
        """The board's views as GraphQL returns them: id, number, name, layout, filter, grouping, sorting, visible fields."""
        query = ("query($id:ID!){node(id:$id){... on ProjectV2{views(first:50){nodes{id number name layout filter "
                 "groupByFields(first:5){nodes{... on ProjectV2FieldCommon{name}}} "
                 "verticalGroupByFields(first:5){nodes{... on ProjectV2FieldCommon{name}}} "
                 "sortByFields(first:5){nodes{field{... on ProjectV2FieldCommon{name}} direction}} "
                 "visibleFields(first:50){nodes{... on ProjectV2FieldCommon{name}}}}}}}}")
        return self.graphql(query, {"id": project_id})["node"]["views"]["nodes"]

    def view_field_ids(self, project_id, number):
        """{field name: numeric id} for creating views. GraphQL lists Created, Updated and Closed and REST lists Type, so both are read."""
        query = "query($id:ID!){node(id:$id){... on ProjectV2{fields(first:50){nodes{... on ProjectV2FieldCommon{databaseId name}}}}}}"
        ids = {f["name"]: f["databaseId"] for f in self.graphql(query, {"id": project_id})["node"]["fields"]["nodes"]
               if f and f.get("name") and f.get("databaseId")}
        owner = self.repo.split("/")[0]
        for f in self.request("GET", f"/orgs/{owner}/projectsV2/{number}/fields?per_page=100") or []:
            ids.setdefault(f["name"], f["id"])
        return ids

    def create_view(self, number, body):
        """Create a view (REST). `body`: name, layout, filter and, as numeric field ids, visible_fields, sort_by, group_by, vertical_group_by."""
        owner = self.repo.split("/")[0]
        return self.request("POST", f"/orgs/{owner}/projectsV2/{number}/views", body)

    def delete_view(self, view_id):
        return self.graphql("mutation($v:ID!){deleteProjectV2View(input:{viewId:$v}){clientMutationId}}", {"v": view_id})
