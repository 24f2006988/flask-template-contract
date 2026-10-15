"""Contract-level integration of the static Python and Jinja analyzers."""

from __future__ import annotations

import ast
from pathlib import Path

from .jinja_analyzer import analyze_template
from .models import AnalysisResult, Finding, FindingCode, Severity, SourceLocation
from .scanner import scan_project


def _gap_finding(gap, site=None, *, template=None, variable=None) -> Finding:
    severity = Severity.ERROR if gap.code == FindingCode.MISSING_VARIABLE else Severity.CANT_VERIFY
    return Finding(gap.code, severity, gap.location or (site.location if site else None),
                   site.function if site else None, site.routes[0] if site and site.routes else None,
                   template=template, variable=variable, reason=gap.reason,
                   dependency_chain=((template,) if template else ()))


def _template_location(summary, variable: str) -> SourceLocation | None:
    for requirement in summary.requirements:
        if requirement.variable == variable:
            return requirement.location
    return None


def _scope_roots(scan, site, root: Path) -> tuple[Path, ...]:
    if site.app:
        for scope, roots in scan.template_roots:
            if scope == site.app:
                return roots
    return (root / "templates",)


def _route(site):
    return site.routes[0] if site.routes else getattr(site, "route", None)


def analyze(root: Path, strict: bool = False) -> AnalysisResult:
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("project root is not a directory")
    scan = scan_project(root)
    findings: list[Finding] = []
    for gap in scan.gaps:
        findings.append(_gap_finding(gap))

    provider_keys = {key for provider in scan.providers for key in provider.definite_keys}
    provider_uncertain = any(provider.unknown_keys for provider in scan.providers)
    default_globals = {"config", "request", "session", "g", "url_for", "get_flashed_messages",
                       "current_user", "csrf_token", "range", "dict", "lipsum", "cycler", "joiner", "namespace"}

    for site in scan.render_sites:
        template = site.template_candidates[0] if site.template_candidates else None
        for gap in site.gaps:
            variable = gap.reason.split(": ", 1)[1] if gap.code == FindingCode.BRANCH_FLOW and ": " in gap.reason else None
            findings.append(_gap_finding(gap, site, template=template, variable=variable))
        if any(gap.code == FindingCode.AMBIGUOUS_ROOTS for gap in site.gaps):
            continue
        if not site.template_candidates:
            continue
        roots = _scope_roots(scan, site, root)
        candidate_path = None
        candidate_name = None
        for name in site.template_candidates:
            matches = [folder / name for folder in roots if (folder / name).is_file()]
            if len(matches) > 1:
                findings.append(Finding(FindingCode.AMBIGUOUS_ROOTS, Severity.CANT_VERIFY, site.location,
                    site.function, _route(site), template=name,
                    reason="The render target exists in multiple applicable template roots.",
                    dependency_chain=site.template_candidates))
                candidate_name = name
                break
            if matches:
                candidate_name, candidate_path = name, matches[0]
                break
        if candidate_path is None:
            if candidate_name is None:
                candidate_name = site.template_candidates[0]
                findings.append(Finding(FindingCode.MISSING_TEMPLATE, Severity.CANT_VERIFY, site.location,
                    site.function, _route(site), template=candidate_name,
                    reason="No literal render candidate could be found.", dependency_chain=site.template_candidates))
            continue

        summary = analyze_template(root, candidate_path, lookup_roots=roots)
        for gap in summary.gaps:
            findings.append(Finding(gap.code, Severity.CANT_VERIFY, gap.location, site.function, _route(site),
                template=candidate_name, reason=gap.reason, dependency_chain=(candidate_name,)))
        uncertain = bool(summary.gaps) or provider_uncertain or any(g.code in {FindingCode.UNPACKING, FindingCode.WRAPPER, FindingCode.BRANCH_FLOW} for g in site.gaps)
        supplied = set(site.explicit_kwargs) | provider_keys | default_globals
        used = {req.variable for req in summary.requirements}
        if not uncertain:
            for req in summary.requirements:
                if req.required and req.variable not in supplied:
                    findings.append(Finding(FindingCode.MISSING_VARIABLE, Severity.ERROR, req.location,
                        site.function, _route(site), template=candidate_name, variable=req.variable,
                        reason=f"Template reads {req.variable}, but the {site.function} render supplies no value for it.",
                        related_locations=(site.location,), dependency_chain=(candidate_name,)))
            keyword_locations = dict(site.explicit_keyword_locations)
            for variable in sorted(site.explicit_kwargs - used):
                location = keyword_locations.get(variable, site.location)
                findings.append(Finding(FindingCode.UNUSED_VARIABLE, Severity.WARNING, location,
                    site.function, _route(site), template=candidate_name, variable=variable,
                    reason=f"Render data {variable} is supplied explicitly but is not read by {candidate_name}.",
                    related_locations=(site.location,),
                    dependency_chain=(candidate_name,)))

    if not scan.render_sites and not scan.app_scopes and not scan.gaps:
        raise ValueError("no Flask app or render_template call found")
    return AnalysisResult(findings, complete=not any(f.severity == Severity.CANT_VERIFY for f in findings))
