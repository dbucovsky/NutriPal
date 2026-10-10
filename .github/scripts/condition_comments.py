"""The comments the automation writes for a condition, and how it reads them back.

A *decide* condition (stale, waited too long, new work on a finished ticket, a passed version) is raised as one
comment, so that it notifies. Besides the first-line marker the automation has always written
(`<!-- attention:watch ... -->`, which keeps the comment out of a ticket's "last activity"), the comment carries
a second marker, `<!-- condition:<id> -->`, and two checkboxes:

    - [ ] Fine: nothing is wrong, or it is put right
    - [ ] Handled elsewhere: say where in a reply

A person ticks one. A ticket with several open conditions has several comments, and it drops out of Decide only
when every one is ticked. A *fix* condition that stays broken gets a comment too (no boxes: the cause is fixed
in the fields), and when the rule stops being broken the comment is edited to say so.

This module only builds and reads text; `conditions.py` decides what to post or edit and when.
"""
import re

FINE = "Fine: nothing is wrong, or it is put right"
ELSEWHERE = "Handled elsewhere: say where in a reply"
CONDITION = re.compile(r"<!-- condition:([a-z-]+) -->")
BOX_FINE = re.compile(r"^- \[([ xX])\] " + re.escape(FINE) + r"\s*$", re.M)
BOX_ELSEWHERE = re.compile(r"^- \[([ xX])\] " + re.escape(ELSEWHERE) + r"\s*$", re.M)
FIXED = "✅ fixed on "
RESTORED = "<!-- boxes-restored -->"
LEVEL_ORDER = {"Watch": 1, "Caution": 2}


def marker(condition_id):
    return f"<!-- condition:{condition_id} -->"


def boxes():
    return f"- [ ] {FINE}\n- [ ] {ELSEWHERE}"


def decorate(text, condition_id):
    """The text of a flag comment (its first line is the attention marker) with the condition marker and the boxes."""
    first, _, rest = text.partition("\n")
    return f"{first}\n{marker(condition_id)}\n{rest}\n\n{boxes()}"


def fix_comment(rule_id, explanation):
    """The comment for a fix rule that stays broken. It has no boxes."""
    return (f"<!-- attention:fix rule={rule_id} -->\n{marker(rule_id)}\n"
            f"Fix: {explanation}. Put the fields right and this goes by itself at the next refresh; "
            "this comment then says it was fixed.")


def condition_of(body):
    """The condition id a comment was written for, or None."""
    match = CONDITION.search(body or "")
    return match.group(1) if match else None


def is_fix_comment(body):
    return (body or "").startswith("<!-- attention:fix ")


def is_fixed(body):
    return FIXED in (body or "")


def state(body):
    """What a decide comment says: 'open', 'fine', 'elsewhere' or 'damaged' (the box lines were edited away).

    A damaged comment counts as open; `restore` puts its lines back."""
    fine, elsewhere = BOX_FINE.search(body or ""), BOX_ELSEWHERE.search(body or "")
    if not fine or not elsewhere:
        return "damaged"
    if elsewhere.group(1) in "xX":
        return "elsewhere"
    if fine.group(1) in "xX":
        return "fine"
    return "open"


def restore(body):
    """The comment with any missing box line put back, unticked, and a note saying so (once)."""
    text = body
    if not BOX_FINE.search(text):
        text += f"\n- [ ] {FINE}"
    if not BOX_ELSEWHERE.search(text):
        text += f"\n- [ ] {ELSEWHERE}"
    if RESTORED not in text:
        text += f"\n{RESTORED}\nThe lines of the boxes were changed, so they were put back unticked: tick one."
    return text


def mark_fixed(body, date):
    return f"{body}\n\n{FIXED}{date}: the rule is no longer broken."


def attention_after(comments, current, levels):
    """The Attention a ticket should have, from its decide comments (a list of (condition id, state)).

    Only the flags the automation raises (Watch, Caution) are ever changed; a value a person set by hand, and
    AtRisk, are left alone. Never raises a flag: raising is done when the comment is posted.
    Returns the new value, or None for no change."""
    if current not in LEVEL_ORDER or not comments:
        return None
    open_levels = [levels[i] for i, s in comments if s in ("open", "damaged") and i in levels]
    if open_levels:
        top = max(open_levels, key=lambda name: LEVEL_ORDER[name])
        return top if top != current else None
    if any(s == "elsewhere" for _, s in comments):
        return "Acknowledged"
    return "Fine"
