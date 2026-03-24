"""Tier 1 pure function tests for project matching.

Covers _extract_project(), _make_alias(), and _resolve_project()
from cyrus_common.py. Zero mocking required — these are pure functions.

References:
  - cyrus_common.py lines 180-221 (where all three functions are defined)
  - docs/14-test-suite.md — Tier 1: Pure Function Tests

Note on imports: All three functions are defined in cyrus_common.py.
We import directly from cyrus_common to avoid the Windows-only (UIA/COM)
deps that cyrus_brain.py pulls in at import time.
cyrus_common handles missing platform deps gracefully via try/except.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add cyrus2/ to sys.path so `import cyrus_common` resolves correctly.
# cyrus_common wraps Windows-only packages in try/except, so it imports
# cleanly on any platform without mocking.
_CYRUS2_DIR = Path(__file__).parent.parent
if str(_CYRUS2_DIR) not in sys.path:
    sys.path.insert(0, str(_CYRUS2_DIR))

from cyrus_common import (  # noqa: E402
    _extract_project,
    _make_alias,
    _resolve_project,
)

# ── test_extract_project ──────────────────────────────────────────────────────


class TestExtractProject:
    """Tier 1 tests for _extract_project(): VS Code window title parsing."""

    # ── Standard formats ─────────────────────────────────────────────────────

    def test_extract_project_simple_title(self) -> None:
        """'myproject - Visual Studio Code' → 'myproject'."""
        assert _extract_project("myproject - Visual Studio Code") == "myproject"

    def test_extract_project_file_and_project(self) -> None:
        """'main.py - cyrus - Visual Studio Code' → 'cyrus' (last segment)."""
        assert _extract_project("main.py - cyrus - Visual Studio Code") == "cyrus"

    def test_extract_project_deeply_nested_path(self) -> None:
        """'a - b - c - Visual Studio Code' → 'c' (last segment always wins)."""
        assert _extract_project("a - b - c - Visual Studio Code") == "c"

    # ── Bullet / modified indicator ───────────────────────────────────────────

    def test_extract_project_bullet_prefix(self) -> None:
        """'● my-app - Visual Studio Code' → 'my-app' (bullet stripped)."""
        assert _extract_project("● my-app - Visual Studio Code") == "my-app"

    def test_extract_project_bullet_with_file(self) -> None:
        """'● main.py - my-proj - Visual Studio Code' → 'my-proj'."""
        assert _extract_project("● main.py - my-proj - Visual Studio Code") == "my-proj"

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_extract_project_empty_string_returns_fallback(self) -> None:
        """Empty title returns the 'VS Code' fallback."""
        assert _extract_project("") == "VS Code"

    def test_extract_project_single_word_no_vscode_suffix(self) -> None:
        """A single word with no ' - Visual Studio Code' suffix returns that word."""
        # No " - Visual Studio Code" to strip, single part, returns it directly
        assert _extract_project("myapp") == "myapp"

    def test_extract_project_no_vscode_suffix_uses_last_segment(self) -> None:
        """Title without VS Code suffix still returns the last ' - ' segment."""
        # Useful when the title parsing is called on raw platform strings
        assert _extract_project("file.py - myapp") == "myapp"

    # ── Unicode and special characters ───────────────────────────────────────

    def test_extract_project_unicode_in_project_name(self) -> None:
        """Unicode project name is preserved verbatim."""
        assert _extract_project("プロジェクト - Visual Studio Code") == "プロジェクト"

    def test_extract_project_project_name_with_spaces(self) -> None:
        """Project names containing spaces are preserved correctly."""
        assert _extract_project("My Project - Visual Studio Code") == "My Project"

    def test_extract_project_project_name_with_hyphens(self) -> None:
        """Hyphenated project names (common in repos) are returned intact."""
        assert _extract_project("my-web-app - Visual Studio Code") == "my-web-app"

    def test_extract_project_project_name_with_dots(self) -> None:
        """Dotted project names like org.example.app are returned intact."""
        result = _extract_project("org.example.app - Visual Studio Code")
        assert result == "org.example.app"


# ── test_make_alias ───────────────────────────────────────────────────────────


class TestMakeAlias:
    """Tier 1 tests for _make_alias(): project name → voice-friendly alias."""

    # ── Kebab-case ────────────────────────────────────────────────────────────

    def test_make_alias_kebab_case(self) -> None:
        """'my-project' → 'my project' (hyphens become spaces)."""
        assert _make_alias("my-project") == "my project"

    def test_make_alias_kebab_multi_word(self) -> None:
        """'my-web-app' → 'my web app' (all hyphens replaced)."""
        assert _make_alias("my-web-app") == "my web app"

    # ── Snake_case ────────────────────────────────────────────────────────────

    def test_make_alias_snake_case(self) -> None:
        """'my_project' → 'my project' (underscores become spaces)."""
        assert _make_alias("my_project") == "my project"

    def test_make_alias_snake_multi_word(self) -> None:
        """'backend_service_v2' → 'backend service v2'."""
        assert _make_alias("backend_service_v2") == "backend service v2"

    # ── Case normalisation ────────────────────────────────────────────────────

    def test_make_alias_uppercase_converted_to_lower(self) -> None:
        """'MY-PROJECT' → 'my project' (lowercased + hyphens replaced)."""
        assert _make_alias("MY-PROJECT") == "my project"

    def test_make_alias_mixed_case_lowercased(self) -> None:
        """'Backend-Service' → 'backend service'."""
        assert _make_alias("Backend-Service") == "backend service"

    # ── Already-clean input ───────────────────────────────────────────────────

    def test_make_alias_already_spaced_lowercase(self) -> None:
        """'my project' (already voice-friendly) is returned unchanged."""
        assert _make_alias("my project") == "my project"

    def test_make_alias_plain_word_unchanged(self) -> None:
        """A single lowercase word with no separators passes through unchanged."""
        assert _make_alias("cyrus") == "cyrus"

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_make_alias_mixed_separators(self) -> None:
        """'my-web_app' → 'my web app' (both hyphens and underscores replaced)."""
        assert _make_alias("my-web_app") == "my web app"

    def test_make_alias_consecutive_separators_collapsed(self) -> None:
        """'my--project' → 'my project' (double hyphens collapse to one space)."""
        assert _make_alias("my--project") == "my project"

    def test_make_alias_empty_string(self) -> None:
        """Empty string input returns empty string."""
        assert _make_alias("") == ""

    def test_make_alias_only_separators_returns_empty(self) -> None:
        """A string of only hyphens/underscores normalises to empty string."""
        assert _make_alias("---") == ""


# ── test_resolve_project ──────────────────────────────────────────────────────


class TestResolveProject:
    """Tier 1 tests for _resolve_project(): fuzzy project name matching."""

    # ── Happy path: exact matches ─────────────────────────────────────────────

    def test_resolve_project_exact_match(self) -> None:
        """Exact alias match returns the associated project name immediately."""
        aliases = {"cyrus": "cyrus-proj"}
        assert _resolve_project("cyrus", aliases) == "cyrus-proj"

    def test_resolve_project_exact_match_normalised_query(self) -> None:
        """Query 'my-app' is normalised to 'my app', matching alias 'my app'."""
        aliases = {"my app": "my-app-proj"}
        assert _resolve_project("my-app", aliases) == "my-app-proj"

    def test_resolve_project_exact_match_case_insensitive(self) -> None:
        """Query 'WEB APP' normalises to 'web app', matching alias 'web app'."""
        aliases = {"web app": "WebProject"}
        assert _resolve_project("WEB APP", aliases) == "WebProject"

    # ── Happy path: partial matches ───────────────────────────────────────────

    def test_resolve_project_query_is_substring_of_alias(self) -> None:
        """Short query 'web' partially matches alias 'web app' → returns project."""
        aliases = {"web app": "WebProject"}
        assert _resolve_project("web", aliases) == "WebProject"

    def test_resolve_project_alias_is_substring_of_query(self) -> None:
        """Alias 'web app' is a substring of query 'switch to web app' → match."""
        aliases = {"web app": "WebProject"}
        assert _resolve_project("switch to web app", aliases) == "WebProject"

    def test_resolve_project_longest_alias_wins_on_ambiguity(self) -> None:
        """When multiple aliases partially match, the longest (most specific) wins."""
        aliases = {
            "web": "ShortProject",
            "web app service": "LongProject",
        }
        # "web app service" is longer → it wins
        result = _resolve_project("web app service", aliases)
        assert result == "LongProject"

    def test_resolve_project_normalises_query_before_partial_match(self) -> None:
        """Query 'MY_WEB_APP' normalises to 'my web app', matching 'my web app'."""
        aliases = {"my web app": "MyWebProj"}
        assert _resolve_project("MY_WEB_APP", aliases) == "MyWebProj"

    # ── No-match and empty cases ──────────────────────────────────────────────

    def test_resolve_project_no_match_returns_none(self) -> None:
        """Query with no matching alias returns None."""
        aliases = {"cyrus": "cyrus-proj", "barf": "barf-proj"}
        assert _resolve_project("unknown-project", aliases) is None

    def test_resolve_project_empty_aliases_returns_none(self) -> None:
        """Empty aliases dict always returns None."""
        assert _resolve_project("anything", {}) is None

    def test_resolve_project_empty_query_matches_all_returns_longest(self) -> None:
        """Empty query ('') is a substring of every alias — longest alias wins."""
        aliases = {
            "cyrus": "CyrusProj",
            "my web app": "WebProj",
        }
        # Empty string is a substring of every alias — longest alias returned
        result = _resolve_project("", aliases)
        # "my web app" (10 chars) > "cyrus" (5 chars), so WebProj wins
        assert result == "WebProj"

    # ── Special character handling ────────────────────────────────────────────

    @pytest.mark.parametrize(
        "query,aliases,expected",
        [
            # Underscore in query normalised to space
            ("backend_service", {"backend service": "BackendProj"}, "BackendProj"),
            # Hyphen in query normalised to space
            ("my-api", {"my api": "ApiProj"}, "ApiProj"),
            # Mixed query separators
            ("my-web_app", {"my web app": "WebProj"}, "WebProj"),
        ],
        ids=["underscore_query", "hyphen_query", "mixed_separators"],
    )
    def test_resolve_project_normalises_query_separators(
        self, query: str, aliases: dict, expected: str
    ) -> None:
        """Hyphens and underscores in the query are normalised before matching."""
        assert _resolve_project(query, aliases) == expected
