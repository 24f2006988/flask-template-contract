import json
from dataclasses import FrozenInstanceError

import pytest

from flask_template_contract.models import (
    AnalysisGap, AnalysisResult, Finding, FindingCode, ProviderSummary, RenderSite,
    Severity, SourceLocation, TemplateRequirement, TemplateSummary,
)


def test_location_normalizes_relative_posix_path():
    location = SourceLocation(r".\views\home.py", 3)
    assert location.to_dict() == {"file": "views/home.py", "line": 3, "column": None}
    assert SourceLocation("views//home.py", 3, 2).column == 2


@pytest.mark.parametrize("path", ["", ".", "/app.py", r"C:\app.py", "C:app.py",
                                   r"\\server\app.py", "a\0b"])
def test_location_rejects_invalid_paths(path):
    with pytest.raises(ValueError):
        SourceLocation(path, 1)


@pytest.mark.parametrize("line,column", [(0, None), (-1, None), (True, None),
                                         (1.5, None), (None, None), (1, 0),
                                         (1, -1), (1, False), (1, 1.5)])
def test_location_rejects_invalid_positions(line, column):
    with pytest.raises(ValueError):
        SourceLocation("app.py", line, column)


def test_records_have_practical_frozen_defaults_and_copy_collections():
    location = SourceLocation("app.py", 1)
    routes, keys = ["/"], {"user"}
    site = RenderSite(location, routes=routes, explicit_kwargs=keys)
    routes.append("/later")
    keys.add("later")
    assert site.routes == ("/",)
    assert site.explicit_kwargs == frozenset({"user"})
    assert site.template_candidates == () and site.gaps == ()
    provider = ProviderSummary(definite_keys={"user"}, possible_keys=["token"])
    assert provider.definite_keys == frozenset({"user"})
    assert provider.possible_keys == frozenset({"token"})
    assert provider.unknown_keys is False and provider.origin is None
    required = TemplateRequirement("user", dependency_chain=["home.html"])
    optional = TemplateRequirement("token", required=False)
    assert required.required and not required.optional
    assert optional.optional and not optional.required
    assert required.dependency_chain == ("home.html",)
    summary = TemplateSummary(requirements=[required], dependencies=["base.html"],
                              external_usage={"user"})
    assert summary.requirements == (required,)
    assert summary.dependencies == ("base.html",)
    assert summary.external_usage == frozenset({"user"})
    gap = AnalysisGap("FTC102")
    finding = Finding("FTC102", "cant_verify")
    result = AnalysisResult([finding])
    for record in [location, site, provider, required, summary, gap, finding, result]:
        with pytest.raises(FrozenInstanceError):
            record.unexpected = True


def test_stable_codes_and_severities():
    assert [code.value for code in FindingCode] == ["FTC001", "FTC002"] + [
        f"FTC{number}" for number in range(101, 114)]
    assert [severity.value for severity in Severity] == ["error", "warning", "cant_verify"]
    for code in list(FindingCode)[2:]:
        assert AnalysisGap(code).code == code
        assert Finding(code, "cant_verify").severity is Severity.CANT_VERIFY
    with pytest.raises(ValueError):
        Finding("FTC001", "warning")
    with pytest.raises(ValueError):
        Finding("FTC999", "cant_verify")
    with pytest.raises(ValueError):
        AnalysisGap("FTC002")
    with pytest.raises(ValueError):
        TemplateRequirement("")
    with pytest.raises(ValueError):
        TemplateRequirement("user", required="optional")
    with pytest.raises(ValueError):
        AnalysisResult(complete="yes")


@pytest.mark.parametrize("codes,normal,strict,complete", [
    ([], 0, 0, True), (["FTC001"], 1, 1, True), (["FTC002"], 0, 1, True),
    (["FTC102"], 0, 0, False), (["FTC001", "FTC102"], 1, 1, False),
    (["FTC002", "FTC102"], 0, 1, False),
])
def test_exit_semantics_and_unknown_completeness(codes, normal, strict, complete):
    severity = {"FTC001": "error", "FTC002": "warning"}
    result = AnalysisResult([Finding(code, severity.get(code, "cant_verify"))
                             for code in codes])
    assert result.exit_code() == normal
    assert result.exit_code(strict=True) == strict
    assert result.to_dict()["exit_code"] == normal
    assert result.to_dict(strict=True)["exit_code"] == strict
    assert result.complete is complete
    assert AnalysisResult(complete=False).exit_code(strict=True) == 0
    assert AnalysisResult(complete=False).complete is False


def test_json_order_counts_nulls_and_dependency_order():
    a, b = SourceLocation("a.py", 2), SourceLocation("b.py", 1, 4)
    findings = [
        Finding("FTC002", "warning", b, variable="unused"),
        Finding("FTC001", "error", a, variable="z", related_locations=[b, a],
                dependency_chain=["child.html", "base.html"]),
        Finding("FTC001", "error", a, variable="a"),
        Finding("FTC113", "cant_verify"),
    ]
    result = AnalysisResult(findings)
    payload = result.to_dict()
    assert list(payload) == ["schema_version", "complete", "findings", "summary", "exit_code"]
    assert payload["schema_version"] == 1
    assert payload["summary"] == {"errors": 2, "warnings": 1, "cant_verify": 1}
    assert payload["complete"] is False
    assert [f["variable"] for f in payload["findings"]] == [None, "a", "z", "unused"]
    unknown = payload["findings"][0]
    for key in ["location", "function", "route", "branch", "template", "variable"]:
        assert key in unknown and unknown[key] is None
    assert payload["findings"][2]["related_locations"] == [a.to_dict(), b.to_dict()]
    assert payload["findings"][2]["dependency_chain"] == ["child.html", "base.html"]
    assert json.dumps(payload) == json.dumps(AnalysisResult(reversed(findings)).to_dict())
    assert json.loads(json.dumps(payload)) == payload
    payload["findings"].clear()
    assert len(result.findings) == 4


def test_sort_distinguishes_null_from_empty_optional_values():
    null = Finding("FTC001", "error")
    empty = Finding("FTC001", "error", function="")
    assert AnalysisResult([null, empty]).to_dict() == AnalysisResult([empty, null]).to_dict()


@pytest.mark.parametrize("code", list(FindingCode)[2:])
def test_every_unknown_code_is_nonfailing_even_in_strict_mode(code):
    result = AnalysisResult([Finding(code, Severity.CANT_VERIFY)])
    assert result.to_dict(strict=True)["exit_code"] == 0
    assert result.complete is False
