"""Metadata/harness tests only; these do not establish any analyzer behavior."""

import ast
from copy import deepcopy
import json

import pytest


CLEAN_EXPECTED = {
    "schema_version": 1,
    "complete": True,
    "findings": [],
    "summary": {"errors": 0, "warnings": 0, "cant_verify": 0},
    "exit_code": 0,
}


def test_clean_fixture_metadata_is_discoverable_and_exact(fixture_cases):
    """Check fixture inventory and declared JSON, not an analyzer result."""
    names = [case.name for case in fixture_cases]
    assert names == sorted(names)
    assert names.count("clean") == 1
    clean = next(case for case in fixture_cases if case.name == "clean")
    assert clean.expected == CLEAN_EXPECTED
    assert clean.root.is_absolute()


def test_clean_fixture_source_references_existing_template(fixture_cases):
    """Parse source statically; neither import Flask nor render the template."""
    clean = next(case for case in fixture_cases if case.name == "clean")
    tree = ast.parse((clean.root / "app.py").read_text(encoding="utf-8"))
    routes = [node for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and isinstance(node.func.value, ast.Name) and node.func.value.id == "app"
              and node.func.attr == "get"]
    assert len(routes) == 1
    assert ast.literal_eval(routes[0].args[0]) == "/"
    renders = [node for node in ast.walk(tree)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == "render_template"]
    assert len(renders) == 1
    assert ast.literal_eval(renders[0].args[0]) == "index.html"
    assert {keyword.arg: ast.literal_eval(keyword.value)
            for keyword in renders[0].keywords} == {"title": "Welcome"}
    template = clean.root / "templates" / "index.html"
    assert template.is_file()
    assert "{{ title }}" in template.read_text(encoding="utf-8")


@pytest.mark.parametrize("patch", [
    {"schema_version": True}, {"schema_version": 2}, {"complete": "true"},
    {"findings": {}}, {"findings": [{}]},
    {"summary": {"errors": True, "warnings": 0, "cant_verify": 0}},
    {"summary": {"errors": -1, "warnings": 0, "cant_verify": 0}},
    {"summary": {"errors": 1, "warnings": 0, "cant_verify": 0}},
    {"summary": {"errors": 0}}, {"exit_code": True}, {"exit_code": 3},
    {"exit_code": 1}, {"unexpected": "not part of schema"},
])
def test_loader_rejects_malformed_envelope(tmp_path, fixture_loader, patch):
    """Reject invalid metadata without invoking application or analyzer code."""
    expected = deepcopy(CLEAN_EXPECTED)
    expected.update(patch)
    (tmp_path / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    with pytest.raises(ValueError):
        fixture_loader(tmp_path)


@pytest.mark.parametrize("text", [
    '{"schema_version": 1, "schema_version": 1}',
    '{"schema_version": NaN}', '[1]', '{',
])
def test_loader_rejects_ambiguous_or_invalid_json(tmp_path, fixture_loader, text):
    (tmp_path / "expected.json").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        fixture_loader(tmp_path)


def _finding_metadata():
    """Synthetic schema example, never presented as an analyzer result."""
    return {
        "code": "FTC101", "severity": "cant_verify", "location": None,
        "function": None, "route": None, "branch": None, "template": None,
        "variable": None, "reason": "Dynamic unpacking is not statically known.",
        "related_locations": [], "dependency_chain": [],
    }


@pytest.mark.parametrize("patch", [
    {"code": "FTC999"}, {"severity": "error"}, {"reason": None},
    {"function": 1}, {"related_locations": [None]}, {"dependency_chain": [1]},
    {"location": {"file": "views\\app.py", "line": 1, "column": None}},
    {"location": {"file": "/app.py", "line": 1, "column": None}},
    {"location": {"file": "app.py", "line": True, "column": None}},
    {"location": {"file": "app.py", "line": 1, "column": 0}},
    {"extra": None},
])
def test_loader_rejects_malformed_finding_metadata(tmp_path, fixture_loader, patch):
    expected = deepcopy(CLEAN_EXPECTED)
    finding = _finding_metadata()
    finding.update(patch)
    expected.update(complete=False, findings=[finding],
                    summary={"errors": 0, "warnings": 0, "cant_verify": 1})
    (tmp_path / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    with pytest.raises(ValueError):
        fixture_loader(tmp_path)


def test_unknown_metadata_requires_incomplete_but_does_not_fail(tmp_path, fixture_loader):
    """Validate unknown metadata semantics, without an analyzer invocation."""
    expected = deepcopy(CLEAN_EXPECTED)
    expected.update(complete=False, findings=[_finding_metadata()],
                    summary={"errors": 0, "warnings": 0, "cant_verify": 1})
    path = tmp_path / "expected.json"
    path.write_text(json.dumps(expected), encoding="utf-8")
    assert fixture_loader(tmp_path).expected["exit_code"] == 0
    expected["complete"] = True
    path.write_text(json.dumps(expected), encoding="utf-8")
    with pytest.raises(ValueError, match="complete=false"):
        fixture_loader(tmp_path)


def test_comparison_helper_preserves_every_report_field(fixture_cases, assert_fixture_result):
    """Exercise comparator mechanics with synthetic data, not analyzer output."""
    clean = next(case for case in fixture_cases if case.name == "clean")
    for patch in ({"complete": False}, {"elapsed": 0}, {"schema_version": True}):
        synthetic = deepcopy(clean.expected)
        synthetic.update(patch)
        with pytest.raises(AssertionError, match="Report differs"):
            assert_fixture_result(synthetic, clean)


def test_comparison_helper_ignores_only_object_key_order(fixture_cases, assert_fixture_result):
    """A metadata round trip checks the helper only; no analyzer is run."""
    clean = next(case for case in fixture_cases if case.name == "clean")
    reordered_metadata = dict(reversed(list(deepcopy(clean.expected).items())))
    assert_fixture_result(reordered_metadata, clean)


def test_model_serialization_matches_harness_schema(tmp_path, fixture_loader):
    """Cross-check independent schema implementations, not analyzer behavior."""
    from flask_template_contract.models import (
        AnalysisResult, Finding, FindingCode, Severity, SourceLocation,
    )

    result = AnalysisResult([
        Finding(FindingCode.MISSING_VARIABLE, Severity.ERROR,
                SourceLocation("app.py", 4), variable="title", reason="Missing title."),
        Finding(FindingCode.UNUSED_VARIABLE, Severity.WARNING,
                SourceLocation("app.py", 5), variable="unused", reason="Unused kwarg."),
        Finding(FindingCode.UNPACKING, Severity.CANT_VERIFY,
                SourceLocation("app.py", 6), reason="Unknown unpacking."),
    ])
    payload = result.to_dict()
    (tmp_path / "expected.json").write_text(json.dumps(payload), encoding="utf-8")
    assert fixture_loader(tmp_path).expected == payload
