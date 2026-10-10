"""A trace of the board writes that could not be made, for the last step of a job.

A sweep that cannot reach or write to the board lets the other steps run (the version is still finalized,
as the guides say) but must not end the run green: a green run with a stale board looks like a healthy one.
Each such place calls `record`, and the last step of the job, `board_status.py`, ends the run red when
anything was recorded. The trace is a file in the runner's temporary directory (`RUNNER_TEMP`, which exists
only in a workflow run), or in the file named by `BOARD_FAILURES_FILE`; a run by hand records nothing.
"""
import os

NAME = "board-failures.txt"


def path():
    """Where the trace is kept, or None outside a workflow run."""
    named = os.environ.get("BOARD_FAILURES_FILE")
    if named:
        return named
    base = os.environ.get("RUNNER_TEMP")
    return os.path.join(base, NAME) if base else None


def record(text):
    """Add one line to the trace. Returns whether it was kept."""
    target = path()
    if not target:
        return False
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(" ".join(str(text).split()) + "\n")
    return True


def recorded():
    """The lines of the trace, oldest first."""
    target = path()
    if not target or not os.path.exists(target):
        return []
    with open(target, encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if line.strip()]
