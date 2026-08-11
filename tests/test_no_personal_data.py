"""The pre-commit guard against committing a real person's data.

This file is on the checker's `EXEMPT` list, because a test for a rule has to
spell out what the rule refuses — every offending pattern below would otherwise
block its own commit. That exemption is why the fixtures here stay obviously
invented: nothing in this file is checked by anything.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from check_no_personal_data import ALLOWED_PEOPLE, scan  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
UNKNOWN = "Nigel"


def person_literal(name: str) -> str:
    return 'Person("' + name + '", date(1974, 1, 14))'


class TestPeopleMustBeInvented:
    def test_an_unlisted_name_is_refused(self):
        assert scan("tests/t.py", person_literal(UNKNOWN))

    def test_an_allowlisted_name_passes(self):
        assert scan("tests/t.py", person_literal("Ada")) == []

    def test_the_message_names_the_offender(self):
        assert UNKNOWN in scan("tests/t.py", person_literal(UNKNOWN))[0]

    @pytest.mark.parametrize("name", sorted(ALLOWED_PEOPLE))
    def test_every_allowlisted_person_really_passes(self, name):
        """Guards against an allowlist entry that the regex cannot match."""
        assert scan("tests/t.py", person_literal(name)) == []


class TestProseExamples:
    """A worked example in a skill is the other route in: a name attached to
    balances in ordinary prose, in a file nobody classes as data."""

    def test_a_name_tied_to_an_age_is_refused(self):
        assert scan("s.md", "leaving about £138,000 when " + UNKNOWN + " turns 57.")

    def test_a_name_tied_to_a_pension_is_refused(self):
        assert scan("s.md", "From March 2032 " + UNKNOWN + "'s pension unlocks.")

    def test_an_invented_household_passes(self):
        assert scan("s.md", "leaving about £138,000 when Ada turns 57.") == []

    def test_domain_words_are_not_mistaken_for_people(self):
        assert scan("s.md", "Unused pension unlocks at 57, and the Partner retires.") == []


class TestIdentifiers:
    @pytest.mark.parametrize("text,what", [
        ("NI number QQ123456C on file", "NI number"),
        ("sort code 12-34-56", "sort code"),
        ("contact a.person@example.com", "email"),
        ("key sk-ant-api03-xxxxxxxxxxxxxxxxxxxx", "API key"),
    ])
    def test_identifiers_are_refused(self, text, what):
        assert scan("notes.md", text), what

    def test_ordinary_financial_prose_passes(self):
        assert scan("s.md", "Draw £50,270 a year, pay 20%, and recycle £20,000.") == []


class TestRealHouseholdDirectories:
    def test_a_client_directory_is_refused(self):
        assert scan("workspace/someone/household.py", "x = 1")

    def test_the_fabricated_fixture_passes(self):
        assert scan("workspace/sample_client/household.py", "x = 1") == []

    def test_the_package_marker_passes(self):
        assert scan("workspace/__init__.py", "") == []


class TestTheRepoItself:
    def test_every_tracked_file_passes(self):
        """The guard is only worth having if it is silent on a clean tree."""
        files = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.split()
        problems = []
        for name in files:
            path = REPO / name
            if path.suffix not in {".py", ".md", ".txt", ".json", ".toml"}:
                continue
            try:
                problems += scan(name, path.read_text())
            except (UnicodeDecodeError, FileNotFoundError):
                continue
        assert problems == []


class TestTheExemption:
    def test_the_checker_and_its_tests_are_exempt(self):
        """Otherwise this file could never be committed."""
        assert scan("tests/test_no_personal_data.py", person_literal(UNKNOWN)) == []
        assert scan("tools/check_no_personal_data.py", "sk-ant-anything") == []

    def test_the_exemption_does_not_extend_to_neighbours(self):
        assert scan("tests/test_serde.py", person_literal(UNKNOWN))


class TestTheHookIsWiredUp:
    def test_hook_is_executable(self):
        assert (REPO / ".githooks" / "pre-commit").stat().st_mode & 0o111

    def test_git_is_pointed_at_it_once_configured(self):
        """Skips on a fresh clone, fails if someone unsets it afterwards."""
        configured = subprocess.run(
            ["git", "config", "core.hooksPath"], cwd=REPO,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if not configured:
            pytest.skip("hooks not set up on this machine — run tools/setup_hooks.sh")
        assert configured == ".githooks"
