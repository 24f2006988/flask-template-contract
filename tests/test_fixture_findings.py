"""End-to-end exact finding checks for every analyzer fixture."""

from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess
import sys
import traceback

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined, UndefinedError

from flask_template_contract.scanner import scan_project


FIXTURES_ROOT = Path(__file__).parent / "fixtures"
FINDING_FIELDS = (
    "code",
    "severity",
    "function",
    "route",
    "template",
    "variable",
    "file",
    "line",
)


def _fixture_directories() -> list[Path]:
    return sorted(
        path for path in FIXTURES_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith((".", "__"))
    )


def _finding_signature(finding: dict) -> tuple:
    location = finding["location"] or {}
    return tuple(
        location.get(field) if field in {"file", "line"} else finding[field]
        for field in FINDING_FIELDS
    )


def _finding_identity(finding: dict) -> tuple:
    return tuple(finding[field] for field in ("code", "function", "route", "template", "variable"))


def _finding_diff(expected: list[dict], actual: list[dict]) -> str:
    expected_counts = Counter(_finding_signature(finding) for finding in expected)
    actual_counts = Counter(_finding_signature(finding) for finding in actual)
    missing = expected_counts - actual_counts
    unexpected = actual_counts - expected_counts
    lines = []
    if missing:
        lines.append("missing findings:")
        lines.extend(f"  - {signature}" for signature, count in missing.items() for _ in range(count))
    if unexpected:
        lines.append("unexpected findings:")
        lines.extend(f"  + {signature}" for signature, count in unexpected.items() for _ in range(count))

    expected_by_identity = defaultdict(list)
    actual_by_identity = defaultdict(list)
    for finding in expected:
        expected_by_identity[_finding_identity(finding)].append(finding)
    for finding in actual:
        actual_by_identity[_finding_identity(finding)].append(finding)
    mismatches = []
    for identity in sorted(set(expected_by_identity) & set(actual_by_identity)):
        for expected_finding, actual_finding in zip(
            expected_by_identity[identity], actual_by_identity[identity]
        ):
            differing = {
                field: (expected_finding.get(field), actual_finding.get(field))
                for field in FINDING_FIELDS
                if (expected_finding.get("location") or {}).get(field) != (actual_finding.get("location") or {}).get(field)
                if field in {"file", "line"}
            }
            differing.update({
                field: (expected_finding.get(field), actual_finding.get(field))
                for field in FINDING_FIELDS
                if field not in {"file", "line"}
                and expected_finding.get(field) != actual_finding.get(field)
            })
            if differing:
                mismatches.append((identity, differing))
    if mismatches:
        lines.append("field mismatches:")
        lines.extend(f"  * {identity}: {fields}" for identity, fields in mismatches)
    return "\n".join(lines)


@pytest.mark.parametrize("fixture_root", _fixture_directories(), ids=lambda path: path.name)
def test_analyzer_findings_match_expected_exactly(fixture_root: Path):
    expected_path = fixture_root / "expected.json"
    assert expected_path.is_file(), f"fixture {fixture_root.name} has no expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    result = subprocess.run(
        [sys.executable, "-m", "flask_template_contract", str(fixture_root), "--format", "json"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 2, (
        f"analyzer tool failure for {fixture_root.name}:\n{result.stderr or result.stdout}"
    )
    actual = json.loads(result.stdout)

    for field in ("schema_version", "complete", "summary", "exit_code"):
        assert actual[field] == expected[field], (
            f"{fixture_root.name}: envelope field {field!r} differs: "
            f"expected {expected[field]!r}, got {actual[field]!r}"
        )
    diff = _finding_diff(expected["findings"], actual["findings"])
    assert not diff, f"{fixture_root.name}: {diff}"


def _missing_finding_cases():
    cases = []
    for fixture_root in _fixture_directories():
        expected = json.loads((fixture_root / "expected.json").read_text(encoding="utf-8"))
        for finding in expected["findings"]:
            if finding["code"] == "FTC001":
                cases.append((fixture_root, finding))
    return cases


@pytest.mark.parametrize(
    "fixture_root,finding", _missing_finding_cases(),
    ids=[f"{fixture.name}-{finding['variable']}" for fixture, finding in _missing_finding_cases()],
)
def test_ground_truth_for_missing_variable(fixture_root: Path, finding: dict):
    """Check simple FTC001s against Jinja2 StrictUndefined, without Flask."""
    template_files = list((fixture_root / "templates").rglob("*.html"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in template_files)
    if fixture_root.name == "guards_all":
        pytest.skip("StrictUndefined raises on maybe's bool conversion before the reported truthy use")

    scan = scan_project(fixture_root)
    site = next((site for site in scan.render_sites
                 if finding["template"] in site.template_candidates), None)
    if site is None:
        pytest.skip("render site could not be matched")
    roots = next((roots for scope, roots in scan.template_roots if scope == site.app),
                 (fixture_root / "templates",))
    env = Environment(loader=FileSystemLoader([str(path) for path in roots]),
                      undefined=StrictUndefined)
    env.globals.update({name: object() for name in (
        "config", "request", "session", "g", "url_for", "get_flashed_messages",
        "current_user", "csrf_token", "range", "dict", "lipsum", "cycler", "joiner", "namespace",
    )})
    context = {name: object() for name in site.explicit_kwargs}
    with pytest.raises(UndefinedError, match=f"{finding['variable']}.*undefined") as raised:
        env.get_template(finding["template"]).render(**context)
    template_path = (fixture_root / finding["location"]["file"]).resolve()
    frames = traceback.extract_tb(raised.value.__traceback__)
    matching = [frame for frame in frames if Path(frame.filename).resolve() == template_path]
    assert matching, f"UndefinedError did not trace to {finding['template']}"
    assert any(frame.lineno == finding["location"]["line"] for frame in matching), (
        f"UndefinedError traced to {finding['template']} lines "
        f"{[frame.lineno for frame in matching]}, expected line {finding['location']['line']}"
    )
