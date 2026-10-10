"""The manifest of the automation files, and the script that checks the project against it.

The manifest (`.github/automation-manifest.json`) names the version of the standard the files
come from and a hash (a fingerprint) of each file as it is in that version. The check reports each
file as unchanged, edited locally, from an older version, or missing. To update a project, copy
the new files from the standard, replace the manifest, and run the check. See the guide on the
new-project bootstrap (section 2.4).

    python .github/scripts/check_manifest.py                       check against the project's manifest
    python .github/scripts/check_manifest.py --against NEW.json     check against a newer manifest
    python .github/scripts/check_manifest.py --update --standard V0.3.0   rewrite the manifest
"""
import fnmatch
import hashlib
import json
import os
import sys

MANIFEST = os.path.join(".github", "automation-manifest.json")

# The automation files: the project copies these unchanged from the standard.
PATTERNS = [
    ".githooks/*",
    ".github/scripts/*.py",
    ".github/workflows/versioning.yml",
    ".github/workflows/reenable-schedule.yml",
    ".github/views.json",
    ".github/pull_request_template.md",
    "tests/test_automation_library.py",
    "tests/test_preflight.py",
    "tests/test_hooks.py",
    "tests/test_finalize.py",
    "tests/test_checks.py",
    "tests/test_workflow.py",
    "tests/test_implemented.py",
    "tests/test_push_step.py",
    "tests/test_skipped_hooks.py",
    "tests/test_dates.py",
    "tests/test_version_numbers.py",
    "tests/test_board_pull_requests.py",
    "tests/test_pull_request_items.py",
    "tests/test_watch.py",
    "tests/test_release.py",
    "tests/test_hotfix.py",
    "tests/test_retire.py",
    "tests/test_views.py",
    "tests/test_conditions.py",
    "tests/test_board_status.py",
    "tests/test_condition_comments.py",
    "tests/test_fields.py",
    "tests/test_reenable_schedule.py",
    "tests/test_manifest.py",
]

UNCHANGED, EDITED, OLDER, MISSING, NEW = "unchanged", "edited locally", "from an older version", "missing", "new in the standard"


def file_hash(path):
    """SHA-256 of the file with line endings normalized, so a checkout's line endings do not matter."""
    with open(path, "rb") as handle:
        data = handle.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def automation_files(root):
    found = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for name in names:
            relative = os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
            if any(fnmatch.fnmatch(relative, pattern) for pattern in PATTERNS):
                found.append(relative)
    return sorted(found)


def build(root, standard):
    return {"standard": standard, "files": {path: file_hash(os.path.join(root, path)) for path in automation_files(root)}}


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write(root, manifest):
    with open(os.path.join(root, MANIFEST), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")


def check(root, manifest, reference=None):
    """Return {path: state}. With a newer `reference` manifest, files are judged against it."""
    own = manifest["files"]
    expected = reference["files"] if reference else own
    states = {}
    for path in sorted(set(own) | set(expected)):
        full = os.path.join(root, path)
        if not os.path.exists(full):
            states[path] = NEW if reference and path not in own else MISSING
            continue
        if path not in expected:
            continue  # a file the newer standard no longer lists
        actual = file_hash(full)
        if actual == expected[path]:
            states[path] = UNCHANGED
        elif reference and actual == own.get(path):
            states[path] = OLDER
        else:
            states[path] = EDITED
    return states


def render(states, standard, reference_standard=None):
    target = f"{standard}" + (f" -> {reference_standard}" if reference_standard else "")
    lines = [f"automation files against the standard ({target}):"]
    lines += [f"  {state:<22} {path}" for path, state in states.items()]
    problems = sum(1 for s in states.values() if s != UNCHANGED)
    lines.append("all files unchanged" if not problems else f"{problems} file(s) differ")
    return "\n".join(lines)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    args = argv if argv is not None else sys.argv[1:]
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    if "--update" in args:
        if "--standard" not in args:
            print("--update needs --standard <version>, for example --standard V0.3.0")
            return 1
        manifest = build(root, args[args.index("--standard") + 1])
        write(root, manifest)
        print(f"wrote {MANIFEST}: {len(manifest['files'])} files, standard {manifest['standard']}")
        return 0
    manifest = load(os.path.join(root, MANIFEST))
    reference = load(args[args.index("--against") + 1]) if "--against" in args else None
    states = check(root, manifest, reference)
    print(render(states, manifest["standard"], reference["standard"] if reference else None))
    return 0 if all(s == UNCHANGED for s in states.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
