"""Version rules: the version format, the bump, Version#, and UTC timestamps.

See the guide on branching and merging (section 3) and appendix C.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

# Impact of a ticket Type on the bump. Version and Alert tickets are ignored.
SUB_TYPES = {"Feature", "Enhancement"}
MOD_TYPES = {"Change", "Bug", "Refactor", "Task"}
IGNORED_TYPES = {"Version", "Alert"}
MARKERS = {"+V": "major", "+s": "sub", "+m": "mod"}

_VERSION = re.compile(r"^V(\d+)\.(\d+)\.(\d+)(?:-HF(\d+))?$")


class VersionError(ValueError):
    pass


@dataclass(frozen=True)
class Version:
    major: int
    sub: int
    mod: int
    hotfix: int = 0

    @classmethod
    def parse(cls, text):
        match = _VERSION.match(text.strip())
        if not match:
            raise VersionError(f"not a version: {text!r}")
        major, sub, mod, hotfix = match.groups()
        return cls(int(major), int(sub), int(mod), int(hotfix or 0))

    def __str__(self):
        text = f"V{self.major}.{self.sub}.{self.mod}"
        return text + (f"-HF{self.hotfix}" if self.hotfix else "")

    def number(self):
        """The number used only to sort versions (Version#)."""
        return self.major * 10_000_000 + self.sub * 10_000 + self.mod * 10 + self.hotfix


def bump_kind(types, marker=None):
    """The kind of bump (major, sub or mod) for the Types of a version's tickets.

    A marker forces the result. Without one, the highest-impact Type wins, and a
    version with no typed tickets is a mod. A major bump is never automatic.
    """
    if marker is not None:
        if marker not in MARKERS:
            raise VersionError(f"unknown marker: {marker!r}")
        return MARKERS[marker]
    unknown = set(types) - SUB_TYPES - MOD_TYPES - IGNORED_TYPES
    if unknown:
        raise VersionError(f"unknown ticket Type: {sorted(unknown)[0]}")
    return "sub" if SUB_TYPES & set(types) else "mod"


def next_version(latest, types, marker=None):
    """The version to give a merge. `latest` is the topmost finalized Version, or None.

    With no finalized version yet, the base is V0.0.0 and the Types are ignored,
    so the first version is V0.1.0 (a marker can still force another result).
    """
    if latest is None:
        kind = MARKERS[marker] if marker else "sub"
        latest = Version(0, 0, 0)
    else:
        kind = bump_kind(types, marker)
    if kind == "major":
        return Version(latest.major + 1, 0, 0)
    if kind == "sub":
        return Version(latest.major, latest.sub + 1, 0)
    return Version(latest.major, latest.sub, latest.mod + 1)


def utc_now():
    return datetime.now(timezone.utc)


def stamp(moment):
    """A build stamp or REF token: yyyymmddhhmmss, in UTC."""
    return moment.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")


def heading_time(moment):
    """The date and time in a finalized version heading: yyyy-mm-dd hh:mm, in UTC."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
