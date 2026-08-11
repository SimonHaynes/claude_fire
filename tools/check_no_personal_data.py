"""Refuse to commit a real person's data.

Run by `.githooks/pre-commit` over the staged tree. `.gitignore` keeps real
households inside `workspace/`, but a directory rule cannot see the other routes
into a commit — copied into a test fixture, quoted in a skill's worked example,
pasted into a TODO.

The design point: a regex cannot tell an invented balance from a real one, so
nothing here tries. It enforces something checkable instead — **every person
named in tracked code or docs must be on `ALLOWED_PEOPLE`** — which turns
"don't commit a client's name" into a visible, deliberate diff.

Precision is the whole value: a check that cries wolf gets bypassed with
`--no-verify` and then protects nothing. Every pattern here is verified silent
against the repo as it stands.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ALLOWED_PEOPLE = frozenset({
    "A", "B", "Ada", "Alex", "Bo", "Client", "Jo", "Mrs TA", "Older",
    "Pat", "Retiree", "Robin", "Sam", "TA", "Younger",
})
"""Invented people the repo is allowed to name. Adding one is the moment to ask
whether the figures beside it were invented too — anonymising a real household
is not the same as fabricating one, because a rounded real balance is still a
real balance."""

DOMAIN_WORDS = frozenset({
    "Beneficiary", "Both", "Each", "Household", "Inherited", "Partner",
    "Pension", "Pensions", "State", "The", "Their", "Unused", "Your",
})
"""Capitalised words that precede the person-shaped verbs below without being
anyone's name."""

PERSON_CALL = re.compile(r'Person\(\s*"([^"]+)"')
PROSE_SUBJECT = re.compile(
    r"\b([A-Z][a-z]{2,})(?:'s)?\s+"
    r"(?:turns \d|retires|stops working|unlocks|'s pension|pension unlocks)"
)

IDENTIFIERS = (
    (re.compile(r"\b[A-Z]{2}\d{6}[A-Z]\b"), "National Insurance number"),
    (re.compile(r"\b\d{2}-\d{2}-\d{2}\b"), "bank sort code"),
    (re.compile(r"\bGB\d{2}[A-Z]{4}\d{14}\b"), "IBAN"),
    (re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "email address"),
    (re.compile(r"sk-ant-|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"), "API key"),
)

TEXT_SUFFIXES = frozenset({".py", ".md", ".txt", ".json", ".toml", ".cfg", ".yaml", ".yml"})

EXEMPT = frozenset({
    "tools/check_no_personal_data.py",
    "tests/test_no_personal_data.py",
})
"""The checker and its tests, which have to spell out the patterns they refuse.

A path list rather than an in-file marker, so widening the exemption is a diff
here rather than a comment anyone can add to the file they want past the gate.
It does mean these two files are unguarded: keep invented data in them like
everywhere else.
"""


def scan(path: str, text: str) -> list[str]:
    """Reasons `text` must not be committed at `path`, or an empty list."""
    if path in EXEMPT:
        return []
    problems = []

    if (
        path.startswith("workspace/")
        and not path.startswith("workspace/sample_client/")
        and path != "workspace/__init__.py"
    ):
        problems.append(
            f"{path}: real household directories are gitignored — this can only be "
            "staged with `git add -f`, which is never the right answer"
        )
        return problems

    for name in PERSON_CALL.findall(text):
        if name not in ALLOWED_PEOPLE:
            problems.append(
                f"{path}: Person({name!r}) is not an invented person on the allowlist. "
                "Invent a new one and add it to ALLOWED_PEOPLE, rather than "
                "anonymising a real household"
            )

    for name in PROSE_SUBJECT.findall(text):
        if name not in ALLOWED_PEOPLE and name not in DOMAIN_WORDS:
            problems.append(
                f"{path}: {name!r} is written about as a person but is not on the "
                "allowlist — a worked example needs an invented household"
            )

    for pattern, what in IDENTIFIERS:
        if pattern.search(text):
            problems.append(f"{path}: looks like it contains a {what}")

    return problems


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, check=True,
    )
    return [p for p in out.stdout.splitlines() if p]


def staged_content(path: str) -> str | None:
    """The staged blob, or None if it is binary or unreadable."""
    blob = subprocess.run(
        ["git", "show", f":{path}"], capture_output=True, check=False
    )
    if blob.returncode != 0:
        return None
    try:
        return blob.stdout.decode()
    except UnicodeDecodeError:
        return None


def main() -> int:
    problems: list[str] = []
    for path in staged_files():
        if Path(path).suffix not in TEXT_SUFFIXES and not path.startswith("workspace/"):
            continue
        text = staged_content(path)
        if text is not None:
            problems.extend(scan(path, text))

    if not problems:
        return 0

    print("Commit refused — this looks like a real person's data:\n", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    print(
        "\nReal households live in workspace/<name>/, which is gitignored. "
        "Anything committed needs invented figures.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
