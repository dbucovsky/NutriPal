"""The local hooks' shared logic. The entry scripts (pre-commit, prepare-commit-msg, pre-push) call it.

- pre-commit: stamps the build in the staged changelog and warns about missing entries.
- prepare-commit-msg: drafts the commit message from the entries just written.
- pre-push: warns when the branch is behind main, when a pushed changelog still has its
  build placeholder, and when the push carries merges that need a rebuild.

The hooks warn and never block: an error in a check lets the work continue. See the guide on
starting work (section 1) and the guide on working and committing (section 5).
"""
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".github", "scripts"))

import changelog  # noqa: E402
import versions  # noqa: E402

CHANGELOG = "CHANGELOG.md"
PLACEHOLDER = "### WIP-Build"
ZEROS = "0" * 40


def git(*args, cwd=None, input=None):
    """Run git and return (exit code, standard output).

    Bytes in and out, so that line endings pass through untouched (text mode would turn LF into CRLF on Windows).
    """
    data = input.encode("utf-8") if input is not None else None
    result = subprocess.run(["git", *args], cwd=cwd, input=data, capture_output=True)
    return result.returncode, result.stdout.decode("utf-8")


def staged_changelog(cwd):
    code, text = git("show", f":{CHANGELOG}", cwd=cwd)
    return text if code == 0 else None


def head_changelog(cwd):
    code, text = git("show", f"HEAD:{CHANGELOG}", cwd=cwd)
    return text if code == 0 else None


def has_placeholder(text):
    return PLACEHOLDER in [line.rstrip("\r") for line in text.split("\n")]


def stamp_staged(cwd, now):
    """Replace the WIP-Build placeholder with a stamped build heading in the staged changelog.

    Only what is staged is stamped. The working copy gets the same replacement when it still has
    the placeholder, so it keeps matching. Returns the stamp, or None when there was nothing to do.
    """
    text = staged_changelog(cwd)
    if text is None or not has_placeholder(text):
        return None
    _, branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    stamp = versions.stamp(now)
    stamped = changelog.stamp_wip_build(text, stamp, branch.strip() or "HEAD")
    _, sha = git("hash-object", "-w", "--stdin", cwd=cwd, input=stamped)
    _, entry = git("ls-files", "-s", "--", CHANGELOG, cwd=cwd)
    mode = entry.split()[0] if entry.strip() else "100644"
    git("update-index", "--cacheinfo", f"{mode},{sha.strip()},{CHANGELOG}", cwd=cwd)
    path = os.path.join(cwd or ".", CHANGELOG)
    with open(path, encoding="utf-8", newline="") as handle:
        working = handle.read()
    if has_placeholder(working):
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(changelog.stamp_wip_build(working, stamp, branch.strip() or "HEAD"))
    return stamp


def new_builds(staged, head):
    """The builds in the staged changelog that the last commit's changelog does not have."""
    known = set()
    if head:
        known = {b.stamp for section in changelog.parse(head) for b in section.builds if b.stamp}
    return [b for section in changelog.parse(staged) for b in section.builds if b.stamp and b.stamp not in known]


def _shorten(line):
    return textwrap.shorten(line.lstrip("- ").strip(), width=72, placeholder="…")


def draft_message(builds):
    """The commit message drafted from the blocks of the new builds, or None if there are none."""
    groups = {}
    for build in builds:
        for block in build.blocks:
            if block.kind == "autoref":
                continue
            key = ("ticket", block.number) if block.kind == "ticket" else ("ref", block.token)
            groups.setdefault(key, (block, []))[1].extend(block.body)
    if not groups:
        return None
    entries = list(groups.values())
    if len(entries) == 1 and entries[0][0].kind == "ticket":
        summary = entries[0][0].title
    elif all(block.kind == "ref" for block, _ in entries):
        first_body = entries[0][1]
        summary = _shorten(first_body[0]) if first_body else entries[0][0].title
    else:
        summary = "Multiple tickets"
    parts = []
    for block, body in entries:
        heading = f"Ticket #{block.number} — {block.title}" if block.kind == "ticket" else f"REF {block.token} — {block.title}"
        parts.append("\n".join([heading, *body]))
    return summary + "\n\n" + "\n\n".join(parts) + "\n"


def git_dir(cwd):
    _, out = git("rev-parse", "--git-dir", cwd=cwd)
    path = out.strip()
    return path if os.path.isabs(path) else os.path.join(cwd or ".", path)


def pre_commit(cwd=None, now=None):
    """Stamp the build, then return the list of warnings."""
    warnings = []
    stamp_staged(cwd, now or versions.utc_now())
    gdir = git_dir(cwd)
    if os.path.exists(os.path.join(gdir, "MERGE_HEAD")):
        warnings.append("This commit completes a merge: recompile the project, and retest in proportion to what came in.")
        merge_message = os.path.join(gdir, "MERGE_MSG")
        conflicted = False
        if os.path.exists(merge_message):
            with open(merge_message, encoding="utf-8") as handle:
                conflicted = "Conflicts:" in handle.read()
        if conflicted:
            warnings.append("A conflict was resolved by hand: build and test the result, and log any adjustment "
                            "in the changelog (guide on syncing and merging, section 1.2).")
        return warnings
    _, names = git("diff", "--cached", "--name-only", cwd=cwd)
    if not names.strip():
        return warnings
    staged = staged_changelog(cwd)
    if staged is None or CHANGELOG not in names.split("\n"):
        warnings.append("This commit changes files but not CHANGELOG.md: add a build block with a ticket or REF entry.")
        return warnings
    try:
        builds = new_builds(staged, head_changelog(cwd))
    except changelog.ChangelogError as error:
        return warnings + [f"CHANGELOG.md has a problem: {error}"]
    if not any(build.blocks for build in builds):
        warnings.append("CHANGELOG.md has no new build with a ticket or REF entry for this commit.")
    return warnings


def prepare_commit_msg(message_file, source="", cwd=None):
    """Put a drafted message at the top of the message file when the editor is about to open."""
    if source not in ("", "template"):
        return False
    staged = staged_changelog(cwd)
    if staged is None:
        return False
    message = draft_message(new_builds(staged, head_changelog(cwd)))
    if message is None:
        return False
    with open(message_file, encoding="utf-8") as handle:
        existing = handle.read()
    with open(message_file, "w", encoding="utf-8", newline="") as handle:
        handle.write(message + existing)
    return True


def pre_push(lines, cwd=None):
    """Return the warnings for the refs about to be pushed (the lines git sends to the hook)."""
    warnings = []
    has_main = git("rev-parse", "--verify", "-q", "origin/main", cwd=cwd)[0] == 0
    for line in lines:
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZEROS:
            continue
        _, local_sha, _, remote_sha = parts
        base = remote_sha if remote_sha != ZEROS else ("origin/main" if has_main else None)
        if has_main:
            _, behind = git("rev-list", "--count", f"{local_sha}..origin/main", cwd=cwd)
            if behind.strip() not in ("", "0"):
                warnings.append(f"The branch is {behind.strip()} commit(s) behind main: merge main into it, rebuild and retest "
                                "before opening the pull request.")
        if base is None:
            continue
        _, merges = git("rev-list", "--merges", "--count", f"{base}..{local_sha}", cwd=cwd)
        if merges.strip() not in ("", "0"):
            warnings.append("This push carries a merge: make sure the result was recompiled and retested.")
        _, changed = git("diff", "--name-only", base, local_sha, cwd=cwd)
        code, tip = git("show", f"{local_sha}:{CHANGELOG}", cwd=cwd)
        if CHANGELOG in changed.split("\n") and code == 0 and has_placeholder(tip):
            warnings.append("CHANGELOG.md still has its WIP-Build placeholder in a pushed commit: the commit hook was "
                            "probably skipped.")
    return warnings


def main(argv):
    name, args = argv[0], argv[1:]
    try:
        if name == "pre-commit":
            warnings = pre_commit()
        elif name == "prepare-commit-msg":
            prepare_commit_msg(args[0], args[1] if len(args) > 1 else "")
            warnings = []
        elif name == "pre-push":
            warnings = pre_push(sys.stdin.read().splitlines())
        else:
            warnings = [f"unknown hook {name}"]
    except Exception as error:  # the hooks fail open
        print(f"hooks: {name} skipped: {error}", file=sys.stderr)
        return 0
    for warning in dict.fromkeys(warnings):
        print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
