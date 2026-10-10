"""Read and write CHANGELOG.md.

The structure is described in the guide on project structure (section 7):

    ## WIP-Version [+V|+s|+m]            the open version, on a branch
    ### WIP-Build                        placeholder for the commit being made
    ### Build <stamp> (branch <name>)    one per commit that logs a change
    #### #123 — <ticket title>           one block per ticket
    #### REF <token> — <reason>          a change with no ticket yet
    #### AUTO-REF <token> (tracked as #N)  written by the automation
    ## V1.2.3 — 2026-10-05 14:32 UTC     a finalized version, newest first
"""
import re
from dataclasses import dataclass, field

from versions import Version

_WIP = re.compile(r"^## WIP-Version(?: (\+[Vsm]))?$")
_FINAL = re.compile(r"^## (V\d+\.\d+\.\d+(?:-HF\d+)?) — (\d{4}-\d\d-\d\d \d\d:\d\d) UTC$")
_BUILD = re.compile(r"^### Build (\d{14}) \(branch ([^\s,)]+)(?:, commit ([0-9a-f]{7,40}))?\)$")
_WIP_BUILD = "### WIP-Build"
_TICKET = re.compile(r"^#### #(\d+) — (.+)$")
_REF = re.compile(r"^#### REF (\d{14}) — (.+)$")
_AUTO_REF = re.compile(r"^#### AUTO-REF (\d{14}) \(tracked as #(\d+)\)$")


class ChangelogError(ValueError):
    pass


@dataclass
class Block:
    kind: str  # "ticket", "ref" or "autoref"
    line: int  # index of the heading line
    number: int = 0  # the ticket number (ticket), or the Alert number (autoref)
    token: str = ""  # the REF or AUTO-REF token
    title: str = ""  # the ticket title, or the REF reason
    body: list = field(default_factory=list)  # the lines under the heading, without blank lines


@dataclass
class Build:
    stamp: str  # "" for the WIP-Build placeholder
    branch: str
    line: int
    blocks: list = field(default_factory=list)
    commit: str = ""  # set when the automation filled in the heading of a commit made without the hooks


@dataclass
class Section:
    kind: str  # "wip" or "final"
    line: int  # index of the heading line
    end: int  # index after the last line of the section
    marker: str = ""  # "+V", "+s", "+m" or ""
    version: Version = None
    time: str = ""
    builds: list = field(default_factory=list)

    def blocks(self):
        return [block for build in self.builds for block in build.blocks]

    def ticket_numbers(self):
        """Ticket numbers in order of first appearance, without repeats."""
        seen = []
        for block in self.blocks():
            if block.kind == "ticket" and block.number not in seen:
                seen.append(block.number)
        return seen

    def last_build(self):
        """The stamp of the latest stamped build, or None."""
        stamps = [build.stamp for build in self.builds if build.stamp]
        return max(stamps) if stamps else None


def parse(text):
    """The sections of the changelog, top to bottom."""
    lines = text.split("\n")
    sections, build, block = [], None, None
    for index, raw in enumerate(lines):
        line = raw.rstrip("\r")  # a changelog with Windows line endings is read the same way
        if line.startswith("## "):
            section = _section(line, index)
            if sections:
                sections[-1].end = index
            sections.append(section)
            build = block = None
        elif line.startswith("### "):
            if not sections:
                raise ChangelogError(f"line {index + 1}: a build heading before any version")
            build = _build(line, index)
            sections[-1].builds.append(build)
            block = None
        elif line.startswith("#### "):
            if build is None:
                raise ChangelogError(f"line {index + 1}: a ticket heading before any build")
            block = _block(line, index)
            build.blocks.append(block)
        elif block is not None and line.strip():
            block.body.append(line)
    if sections:
        sections[-1].end = len(lines)
    if sum(1 for s in sections if s.kind == "wip") > 1:
        raise ChangelogError("more than one open WIP-Version heading")
    return sections


def _section(line, index):
    if line.startswith("## WIP-Version"):
        match = _WIP.match(line)
        if not match:
            raise ChangelogError(f"line {index + 1}: unexpected text after WIP-Version: {line!r}")
        return Section("wip", index, index + 1, marker=match.group(1) or "")
    match = _FINAL.match(line)
    if not match:
        raise ChangelogError(f"line {index + 1}: unrecognized version heading: {line!r}")
    return Section("final", index, index + 1, version=Version.parse(match.group(1)), time=match.group(2))


def _build(line, index):
    if line == _WIP_BUILD:
        return Build("", "", index)
    match = _BUILD.match(line)
    if not match:
        raise ChangelogError(f"line {index + 1}: unrecognized build heading: {line!r}")
    return Build(match.group(1), match.group(2), index, commit=match.group(3) or "")


def _block(line, index):
    match = _TICKET.match(line)
    if match:
        return Block("ticket", index, number=int(match.group(1)), title=match.group(2))
    match = _REF.match(line)
    if match:
        return Block("ref", index, token=match.group(1), title=match.group(2))
    match = _AUTO_REF.match(line)
    if match:
        return Block("autoref", index, token=match.group(1), number=int(match.group(2)))
    raise ChangelogError(f"line {index + 1}: unrecognized entry heading: {line!r}")


def open_section(sections):
    """The open WIP-Version section, or None."""
    return next((s for s in sections if s.kind == "wip"), None)


def latest_final(sections):
    """The topmost finalized section: the single source of truth for the version."""
    return next((s for s in sections if s.kind == "final"), None)


def rename_open_heading(text, version, heading_time):
    """Return the text with the open WIP-Version heading renamed to a finalized one."""
    sections = parse(text)
    wip = open_section(sections)
    if wip is None:
        raise ChangelogError("no open WIP-Version heading")
    lines = text.split("\n")
    lines[wip.line] = f"## {version} — {heading_time} UTC" + _ending(lines[wip.line])
    return "\n".join(lines)


def stamp_wip_build(text, stamp, branch, commit=None):
    """Return the text with the ### WIP-Build placeholder replaced by a stamped build heading.

    The automation passes `commit` when it fills the heading in for a commit made without the hooks.
    """
    lines = text.split("\n")
    hits = [i for i, line in enumerate(lines) if line.rstrip("\r") == _WIP_BUILD]
    if len(hits) != 1:
        raise ChangelogError(f"expected one WIP-Build placeholder, found {len(hits)}")
    where = f"branch {branch}" + (f", commit {commit}" if commit else "")
    lines[hits[0]] = f"### Build {stamp} ({where})" + _ending(lines[hits[0]])
    return "\n".join(lines)


def _ending(line):
    return "\r" if line.endswith("\r") else ""



def add_note(text, stamp, note):
    """Return the text with a bullet added under the first entry of the build with this stamp."""
    for section in parse(text):
        for build in section.builds:
            if build.stamp == stamp and build.blocks:
                lines = text.split("\n")
                at = build.blocks[0].line
                lines.insert(at + 1, f"- {note}" + _ending(lines[at]))
                return "\n".join(lines)
    raise ChangelogError(f"no entry under build {stamp} to add a note to")
