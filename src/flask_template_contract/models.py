"""Immutable, stdlib-only records shared by analysis and output adapters.

Locations are relative to the analyzed project, and positions are one-based.
Unknown analysis is represented by ``cant_verify``, never by a failing exit code.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    CANT_VERIFY = "cant_verify"


class FindingCode(StrEnum):
    MISSING_VARIABLE = "FTC001"
    UNUSED_VARIABLE = "FTC002"
    UNPACKING = "FTC101"
    DYNAMIC_TEMPLATE = "FTC102"
    WRAPPER = "FTC103"
    BRANCH_FLOW = "FTC104"
    TEMPLATE_SYNTAX = "FTC105"
    UNREADABLE_FILE = "FTC106"
    MISSING_TEMPLATE = "FTC107"
    AMBIGUOUS_ROOTS = "FTC108"
    DYNAMIC_PROVIDER = "FTC109"
    UNSUPPORTED_CUSTOMIZATION = "FTC110"
    DYNAMIC_DEPENDENCY = "FTC111"
    PYTHON_SYNTAX = "FTC112"
    CYCLE = "FTC113"


@dataclass(frozen=True)
class SourceLocation:
    file: str
    line: int
    column: int | None = None

    def __post_init__(self) -> None:
        path = self.file.replace("\\", "/")
        if (
            not path
            or "\x00" in path
            or PurePosixPath(path).is_absolute()
            or PureWindowsPath(path).drive
            or str(PurePosixPath(path)) == "."
        ):
            raise ValueError("file must be a nonempty project-relative path")
        for name, value in (("line", self.line), ("column", self.column)):
            if value is None and name == "column":
                continue
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive one-based integer")
        object.__setattr__(self, "file", PurePosixPath(path).as_posix())

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "column": self.column}


def _freeze(record: object, **values: object) -> None:
    for name, value in values.items():
        object.__setattr__(record, name, value)


@dataclass(frozen=True)
class AnalysisGap:
    code: FindingCode
    location: SourceLocation | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        code = FindingCode(self.code)
        if code in (FindingCode.MISSING_VARIABLE, FindingCode.UNUSED_VARIABLE):
            raise ValueError("analysis gaps require a cant_verify code")
        _freeze(self, code=code)


@dataclass(frozen=True)
class RenderSite:
    location: SourceLocation
    function: str | None = None
    routes: tuple[str, ...] = ()
    app: str | None = None
    blueprint: str | None = None
    branch: str | None = None
    template_candidates: tuple[str, ...] = ()
    explicit_kwargs: frozenset[str] = frozenset()
    gaps: tuple[AnalysisGap, ...] = ()

    def __post_init__(self) -> None:
        _freeze(self, routes=tuple(self.routes),
                template_candidates=tuple(self.template_candidates),
                explicit_kwargs=frozenset(self.explicit_kwargs), gaps=tuple(self.gaps))


@dataclass(frozen=True)
class ProviderSummary:
    definite_keys: frozenset[str] = frozenset()
    possible_keys: frozenset[str] = frozenset()
    unknown_keys: bool = False
    scope: str = "app"
    origin: SourceLocation | None = None

    def __post_init__(self) -> None:
        # Unknown keys means additional, unenumerable names may be supplied.
        _freeze(self, definite_keys=frozenset(self.definite_keys),
                possible_keys=frozenset(self.possible_keys))


@dataclass(frozen=True)
class TemplateRequirement:
    variable: str
    required: bool = True
    location: SourceLocation | None = None
    dependency_chain: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.variable:
            raise ValueError("variable must not be empty")
        if type(self.required) is not bool:
            raise ValueError("required must be a boolean")
        _freeze(self, dependency_chain=tuple(self.dependency_chain))

    @property
    def optional(self) -> bool:
        return not self.required


@dataclass(frozen=True)
class TemplateSummary:
    requirements: tuple[TemplateRequirement, ...] = ()
    external_usage: frozenset[str] = frozenset()
    dependencies: tuple[str, ...] = ()
    gaps: tuple[AnalysisGap, ...] = ()

    def __post_init__(self) -> None:
        _freeze(self, requirements=tuple(self.requirements),
                external_usage=frozenset(self.external_usage),
                dependencies=tuple(self.dependencies), gaps=tuple(self.gaps))


@dataclass(frozen=True)
class Finding:
    code: FindingCode
    severity: Severity
    location: SourceLocation | None = None
    function: str | None = None
    route: str | None = None
    branch: str | None = None
    template: str | None = None
    variable: str | None = None
    reason: str = ""
    related_locations: tuple[SourceLocation, ...] = ()
    dependency_chain: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        code, severity = FindingCode(self.code), Severity(self.severity)
        expected = {FindingCode.MISSING_VARIABLE: Severity.ERROR,
                    FindingCode.UNUSED_VARIABLE: Severity.WARNING}.get(
                        code, Severity.CANT_VERIFY)
        if severity != expected:
            raise ValueError(f"{code} requires severity {expected}")
        _freeze(self, code=code, severity=severity,
                related_locations=tuple(self.related_locations),
                dependency_chain=tuple(self.dependency_chain))

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "location": self.location.to_dict() if self.location else None,
            "function": self.function,
            "route": self.route,
            "branch": self.branch,
            "template": self.template,
            "variable": self.variable,
            "reason": self.reason,
            "related_locations": [loc.to_dict() for loc in
                                  sorted(self.related_locations, key=_location_key)],
            "dependency_chain": list(self.dependency_chain),
        }


def _location_key(location: SourceLocation | None) -> tuple:
    if location is None:
        return ("", 0, 0)
    return (location.file, location.line, location.column or 0)


def _finding_key(finding: Finding) -> tuple:
    return (
        _location_key(finding.location), finding.code.value, finding.severity.value,
        finding.function or "", finding.route or "", finding.branch or "",
        finding.template or "", finding.variable or "", finding.reason,
        tuple(sorted((_location_key(loc) for loc in finding.related_locations))),
        finding.dependency_chain,
        # Keep None and empty strings deterministic even if all display keys tie.
        tuple(value is not None for value in (finding.function, finding.route,
              finding.branch, finding.template, finding.variable)),
    )


@dataclass(frozen=True)
class AnalysisResult:
    findings: tuple[Finding, ...] = ()
    complete: bool = True

    def __post_init__(self) -> None:
        if type(self.complete) is not bool:
            raise ValueError("complete must be a boolean")
        findings = tuple(sorted(self.findings, key=_finding_key))
        _freeze(self, findings=findings,
                complete=self.complete and not any(
                    item.severity == Severity.CANT_VERIFY for item in findings))

    def exit_code(self, strict: bool = False) -> int:
        return int(any(item.severity == Severity.ERROR or
                       (strict and item.severity == Severity.WARNING)
                       for item in self.findings))

    def to_dict(self, strict: bool = False) -> dict:
        return {
            "schema_version": 1,
            "complete": self.complete,
            "findings": [finding.to_dict() for finding in self.findings],
            "summary": {
                "errors": sum(f.severity == Severity.ERROR for f in self.findings),
                "warnings": sum(f.severity == Severity.WARNING for f in self.findings),
                "cant_verify": sum(f.severity == Severity.CANT_VERIFY for f in self.findings),
            },
            "exit_code": self.exit_code(strict),
        }
