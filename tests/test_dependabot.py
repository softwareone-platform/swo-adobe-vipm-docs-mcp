"""
Tests that keep .github/dependabot.yml in step with pyproject.toml.

The `dev-dependencies` group is a hand-written list of name patterns, because
Dependabot does not recognise PEP 621 `[project.optional-dependencies]` as
development dependencies — a `dependency-type: development` group matches
nothing here, which is how `ruff` ended up grouped as a runtime dependency.
A hand-written list drifts, so these tests hold it to the `dev` extra.
"""

from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPENDABOT_PATH = REPO_ROOT / ".github" / "dependabot.yml"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def _dependabot() -> dict:
    return yaml.safe_load(DEPENDABOT_PATH.read_text(encoding="utf-8"))


def _uv_update_config() -> dict:
    for update in _dependabot()["updates"]:
        if update["package-ecosystem"] == "uv":
            return update
    raise AssertionError("no `uv` ecosystem entry in dependabot.yml")


def _requirement_names(specifiers: list[str]) -> set[str]:
    """Package names from PEP 508 specifiers, lowercased.

    Splits on the first character that can't be part of a name, so
    `ruff>=0.15.0,<0.16` and `mcp[cli]>=1.0.0` both reduce to their name.
    """
    names = set()
    for spec in specifiers:
        name = spec
        for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
            name = name.split(sep)[0]
        names.add(name.strip().lower())
    return names


def _dev_dependency_names() -> set[str]:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return _requirement_names(pyproject["project"]["optional-dependencies"]["dev"])


def _runtime_dependency_names() -> set[str]:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return _requirement_names(pyproject["project"]["dependencies"])


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


class TestDevDependencyGrouping:
    """
    Every dev dependency must be covered by the `dev-dependencies` patterns,
    and excluded from the catch-all runtime group. Otherwise a dev-tool bump
    is presented for review as though it changed what users install.
    """

    def test_every_dev_dependency_matches_a_dev_pattern(self):
        groups = _uv_update_config()["groups"]
        patterns = groups["dev-dependencies"]["patterns"]
        unmatched = {name for name in _dev_dependency_names() if not _matches_any(name, patterns)}
        assert not unmatched, (
            f"dev dependencies not covered by dependabot.yml dev-dependencies "
            f"patterns {patterns}: {sorted(unmatched)}"
        )

    def test_every_dev_dependency_is_excluded_from_the_runtime_group(self):
        groups = _uv_update_config()["groups"]
        excludes = groups["runtime-dependencies"].get("exclude-patterns", [])
        leaked = {name for name in _dev_dependency_names() if not _matches_any(name, excludes)}
        assert not leaked, (
            f"dev dependencies not excluded from the runtime-dependencies group "
            f"{excludes}: {sorted(leaked)}"
        )

    def test_no_runtime_dependency_is_captured_by_a_dev_pattern(self):
        """The dev patterns are matched first, so an over-broad one would
        silently pull a runtime dependency out of the runtime group."""
        patterns = _uv_update_config()["groups"]["dev-dependencies"]["patterns"]
        captured = {name for name in _runtime_dependency_names() if _matches_any(name, patterns)}
        assert not captured, (
            f"runtime dependencies wrongly matched by dev patterns {patterns}: {sorted(captured)}"
        )


class TestEcosystemCoverage:
    """The repo has Python dependencies and GitHub Actions; both need an entry."""

    def test_both_ecosystems_are_configured(self):
        ecosystems = {u["package-ecosystem"] for u in _dependabot()["updates"]}
        assert {"uv", "github-actions"} <= ecosystems, ecosystems
