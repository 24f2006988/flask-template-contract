"""Thin, deliberately conservative end-to-end analyzer.

The template reader in this module is TEMPORARY: it uses Jinja's meta API for
simple templates. Deep scope, inheritance, include, import, and processor
analysis is intentionally reported as CAN'T VERIFY for this slice.
"""

from __future__ import annotations

import ast
from pathlib import Path

from jinja2 import Environment, TemplateSyntaxError, meta, nodes

from .models import AnalysisResult, Finding, FindingCode, Severity, SourceLocation

DEFAULT_GLOBALS = frozenset({
    "request", "session", "g", "config", "url_for", "get_flashed_messages",
    "current_user", "csrf_token", "range", "dict", "lipsum", "cycler",
    "joiner", "namespace",
})


def _location(path: Path, root: Path, line: int, column: int | None = None) -> SourceLocation:
    return SourceLocation(path.relative_to(root).as_posix(), line, column)


def _literal_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _literal_names(node: ast.AST) -> tuple[str, ...] | None:
    value = _literal_string(node)
    if value is not None:
        return (value,)
    if isinstance(node, (ast.List, ast.Tuple)):
        names = tuple(_literal_string(item) for item in node.elts)
        if all(name is not None for name in names):
            return names  # type: ignore[return-value]
    return None


class _RenderVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, root: Path):
        self.path, self.root = path, root
        self.function: str | None = None
        self.route: str | None = None
        self.sites: list[dict] = []
        self.context_processor = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self.function, self.route
        self.function = node.name
        self.route = self._route(node)
        self.generic_visit(node)
        self.function, self.route = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    def _route(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                if decorator.func.attr in {"get", "post", "put", "patch", "delete", "route"}:
                    if decorator.args:
                        return _literal_string(decorator.args[0])
        return None

    def visit_Call(self, node: ast.Call) -> None:
        is_render = isinstance(node.func, ast.Name) and node.func.id == "render_template"
        if is_render:
            candidates = _literal_names(node.args[0]) if node.args else None
            kwargs = {keyword.arg: keyword for keyword in node.keywords if keyword.arg is not None}
            unpacked = next((keyword for keyword in node.keywords if keyword.arg is None), None)
            self.sites.append({
                "node": node, "candidates": candidates, "kwargs": kwargs,
                "unpacked": unpacked, "function": self.function, "route": self.route,
                "location": _location(self.path, self.root, node.lineno, node.col_offset + 1),
            })
        self.generic_visit(node)


def _read_template(path: Path, root: Path, site: dict, findings: list[Finding]) -> tuple[set[str], set[str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(Finding(FindingCode.UNREADABLE_FILE, Severity.CANT_VERIFY,
            site["location"], site["function"], site["route"], template=site["candidates"][0],
            reason=f"Template file cannot be read: {exc}.", dependency_chain=site["candidates"]))
        return set(), set()
    try:
        tree = Environment().parse(source)
    except TemplateSyntaxError as exc:
        findings.append(Finding(FindingCode.TEMPLATE_SYNTAX, Severity.CANT_VERIFY,
            _location(path, root, exc.lineno or 1, 1), site["function"], site["route"],
            template=site["candidates"][0], reason="Template syntax could not be parsed.",
            dependency_chain=site["candidates"]))
        return set(), set()

    # TEMPORARY reader: meta sees simple free names but not our final scopes.
    used = set(meta.find_undeclared_variables(tree))
    referenced = []
    for node in tree.find_all((nodes.Extends, nodes.Include, nodes.Import, nodes.FromImport)):
        referenced.append(node)
        kind = {nodes.Extends: "inheritance parent", nodes.Include: "included template",
                nodes.Import: "imported macro template", nodes.FromImport: "imported macro template"}[type(node)]
        expression = getattr(node, "template", None)
        expression_text = expression.name if isinstance(expression, nodes.Name) else "dynamic expression"
        findings.append(Finding(FindingCode.DYNAMIC_DEPENDENCY, Severity.CANT_VERIFY,
            _location(path, root, node.lineno, 1), site["function"], site["route"],
            template=site["candidates"][0], reason=f"The {kind} is selected by {expression_text}, so the dependency cannot be resolved.",
            dependency_chain=site["candidates"]))
    return used, {str(getattr(node, "template", "")) for node in referenced}


def analyze(root: Path, strict: bool = False) -> AnalysisResult:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("project root is not a directory")
    findings: list[Finding] = []
    sites: list[dict] = []
    found_flask = False
    for path in sorted(root.rglob("*.py")):
        if any(part in {".venv", ".git", "tests"} for part in path.relative_to(root).parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            findings.append(Finding(FindingCode.PYTHON_SYNTAX, Severity.CANT_VERIFY,
                _location(path, root, getattr(exc, "lineno", 1) or 1, 1), reason=f"Python source could not be parsed: {exc}."))
            continue
        source = path.read_text(encoding="utf-8")
        if "Flask" in source or "render_template" in source:
            found_flask = found_flask or "Flask" in source
        visitor = _RenderVisitor(path, root)
        visitor.visit(tree)
        processor_present = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(((isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                      and dec.func.attr in {"context_processor", "app_context_processor"})
                     or (isinstance(dec, ast.Attribute)
                         and dec.attr in {"context_processor", "app_context_processor"}))
                    for dec in node.decorator_list)
            for node in ast.walk(tree)
        )
        for site in visitor.sites:
            site["provider_uncertain"] = processor_present
        sites.extend(visitor.sites)
        if processor_present:
            for site in visitor.sites:
                findings.append(Finding(FindingCode.DYNAMIC_PROVIDER, Severity.CANT_VERIFY,
                    site["location"], site["function"], site["route"],
                    template=(site["candidates"] or (None,))[0],
                    reason="A context processor is present; its injected names are outside the temporary reader.",
                    dependency_chain=site["candidates"] or ()))

    if not found_flask or not sites:
        raise ValueError("no Flask app or render_template call found")
    template_roots = [root / "templates"]
    for site in sites:
        candidates = site["candidates"]
        if candidates is None:
            findings.append(Finding(FindingCode.DYNAMIC_TEMPLATE, Severity.CANT_VERIFY,
                site["location"], site["function"], site["route"],
                reason="The render target comes from a non-literal expression rather than a resolvable literal template name.", dependency_chain=()))
            continue
        template_name = next((name for name in candidates if any((candidate / name).is_file() for candidate in template_roots)), None)
        if template_name is None:
            findings.append(Finding(FindingCode.MISSING_TEMPLATE, Severity.CANT_VERIFY,
                site["location"], site["function"], site["route"], template=candidates[0],
                reason="No literal render candidate could be found.", dependency_chain=candidates))
            continue
        path = next(candidate / template_name for candidate in template_roots if (candidate / template_name).is_file())
        used, dependencies = _read_template(path, root, {**site, "candidates": (template_name,)}, findings)
        used -= DEFAULT_GLOBALS
        supplied = set(site["kwargs"])
        uncertain = bool(dependencies) or bool(site.get("provider_uncertain"))
        if site["unpacked"] is not None:
            keyword = site["unpacked"]
            findings.append(Finding(FindingCode.UNPACKING, Severity.CANT_VERIFY,
                site["location"],
                site["function"], site["route"], template=template_name,
                reason=f"Keyword context is unpacked from {ast.unparse(keyword.value)}, so the supplied render names cannot be verified statically.",
                dependency_chain=(template_name,)))
            uncertain = True
        if uncertain:
            continue
        for variable in sorted(used - supplied):
            try:
                template_line = next(i for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                                     if variable in line)
                line_text = path.read_text(encoding="utf-8").splitlines()[template_line - 1]
                template_column = line_text.find("{{") + 2
            except (StopIteration, OSError):
                template_line, template_column = 1, 1
            findings.append(Finding(FindingCode.MISSING_VARIABLE, Severity.ERROR,
                _location(path, root, template_line, template_column), site["function"], site["route"],
                template=template_name, variable=variable,
                reason=f"Template reads {variable}, but the {site['function']} render supplies no value for it.",
                related_locations=(site["location"],), dependency_chain=(template_name,)))
        for variable in sorted(supplied - used):
            keyword = site["kwargs"][variable]
            findings.append(Finding(FindingCode.UNUSED_VARIABLE, Severity.WARNING,
                _location(root / site["location"].file, root, keyword.value.lineno, keyword.value.col_offset + 1),
                site["function"], site["route"], template=template_name, variable=variable,
                reason=f"Render data {variable} is supplied explicitly but is not read by {template_name}.",
                dependency_chain=(template_name,)))
    return AnalysisResult(findings, complete=not any(f.severity == Severity.CANT_VERIFY for f in findings))
