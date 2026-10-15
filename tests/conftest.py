"""Fixture metadata helpers only: no application imports or analyzer execution."""

from dataclasses import dataclass
import difflib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import pytest


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


@dataclass(frozen=True)
class FixtureCase:
    """Source directory and expected report for a future analyzer integration test."""

    name: str
    root: Path
    expected: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {value}")


def validate_expected(expected: Any) -> None:
    """Validate fixture report metadata independently of application source."""
    _require(type(expected) is dict, "expected report must be an object")
    _require(
        set(expected) == {"schema_version", "complete", "findings", "summary", "exit_code"},
        "expected report must contain exactly the version 1 envelope fields",
    )
    _require(type(expected["schema_version"]) is int and expected["schema_version"] == 1,
             "schema_version must be integer 1")
    _require(type(expected["complete"]) is bool, "complete must be boolean")
    _require(type(expected["findings"]) is list, "findings must be a list")
    summary = expected["summary"]
    _require(type(summary) is dict and set(summary) == {"errors", "warnings", "cant_verify"},
             "summary must contain errors, warnings, cant_verify")
    _require(all(type(value) is int and value >= 0 for value in summary.values()),
             "summary counts must be nonnegative integers")
    _require(type(expected["exit_code"]) is int and expected["exit_code"] in (0, 1, 2),
             "exit_code must be integer 0, 1, or 2")
    counts = {"errors": 0, "warnings": 0, "cant_verify": 0}
    for finding in expected["findings"]:
        _validate_finding(finding)
        counts[{"error": "errors", "warning": "warnings", "cant_verify": "cant_verify"}[
            finding["severity"]]] += 1
    _require(summary == counts, "summary counts must match findings")
    _require(not expected["complete"] or counts["cant_verify"] == 0,
             "CAN'T VERIFY findings require complete=false")
    if expected["exit_code"] != 2:
        _require(not counts["errors"] or expected["exit_code"] == 1,
                 "errors require exit_code 1")
        _require(expected["exit_code"] != 1 or bool(counts["errors"] or counts["warnings"]),
                 "exit_code 1 requires errors or strict-mode warnings")


def _validate_finding(finding: Any) -> None:
    _require(type(finding) is dict, "finding must be an object")
    _require(set(finding) == {
        "code", "severity", "location", "function", "route", "branch", "template",
        "variable", "reason", "related_locations", "dependency_chain",
    }, "finding must contain exactly the version 1 finding fields")
    codes = {"FTC001": "error", "FTC002": "warning"}
    codes.update({f"FTC{number}": "cant_verify" for number in range(101, 114)})
    _require(type(finding["code"]) is str and finding["code"] in codes,
             "finding code must be a registered version 1 code")
    _require(finding["severity"] == codes[finding["code"]],
             "finding severity must match its code")
    for field in ("function", "route", "branch", "template", "variable"):
        _require(finding[field] is None or type(finding[field]) is str,
                 f"finding {field} must be a string or null")
    _require(type(finding["reason"]) is str, "finding reason must be a string")
    if finding["location"] is not None:
        _validate_location(finding["location"])
    _require(type(finding["related_locations"]) is list,
             "related_locations must be a list")
    for location in finding["related_locations"]:
        _validate_location(location)
    _require(type(finding["dependency_chain"]) is list
             and all(type(item) is str for item in finding["dependency_chain"]),
             "dependency_chain must be a list of strings")


def _validate_location(location: Any) -> None:
    _require(type(location) is dict and set(location) == {"file", "line", "column"},
             "location must contain file, line, column")
    path = location["file"]
    _require(type(path) is str, "location file must be a string")
    _require(bool(path) and "\x00" not in path and "\\" not in path
             and not PurePosixPath(path).is_absolute() and not PureWindowsPath(path).drive
             and PurePosixPath(path).as_posix() == path and path != ".",
             "location file must be a normalized project-relative POSIX path")
    _require(type(location["line"]) is int and location["line"] > 0,
             "location line must be a positive integer")
    column = location["column"]
    _require(column is None or (type(column) is int and column > 0),
             "location column must be null or a positive integer")


def load_fixture_case(root: Path) -> FixtureCase:
    """Read JSON as data; never import or execute the fixture's Python source."""
    root = Path(root).resolve()
    expected = json.loads(
        (root / "expected.json").read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_invalid_constant,
    )
    validate_expected(expected)
    return FixtureCase(name=root.name, root=root, expected=expected)


def discover_fixture_cases(root: Path = FIXTURES_ROOT) -> tuple[FixtureCase, ...]:
    """Enumerate immediate fixture directories in stable name order."""
    return tuple(load_fixture_case(path) for path in sorted(Path(root).iterdir())
                 if path.is_dir() and not path.name.startswith((".", "__")))


def assert_exact_result(actual: dict[str, Any], case: FixtureCase) -> None:
    """Compare a caller-supplied report exactly; this helper never runs an analyzer.

    Object keys are printed deterministically; list order and all report data are
    significant. No timestamps, paths, or other volatile fields are discarded.
    """
    _require(type(actual) is dict, "actual report must be an object")
    expected_json = json.dumps(case.expected, sort_keys=True, indent=2, allow_nan=False)
    actual_json = json.dumps(actual, sort_keys=True, indent=2, allow_nan=False)
    if actual_json != expected_json:
        diff = "\n".join(difflib.unified_diff(
            expected_json.splitlines(), actual_json.splitlines(),
            fromfile=f"{case.name}/expected.json", tofile="actual report", lineterm="",
        ))
        raise AssertionError(f"Report differs from fixture expectation:\n{diff}")


@pytest.fixture
def fixture_cases() -> tuple[FixtureCase, ...]:
    return discover_fixture_cases()


@pytest.fixture
def fixture_loader():
    return load_fixture_case


@pytest.fixture
def assert_fixture_result():
    return assert_exact_result
