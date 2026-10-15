"""Conservative, AST-only discovery of Flask render/context evidence."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .models import AnalysisGap, FindingCode, ProviderSummary, RenderSite, SourceLocation


@dataclass(frozen=True)
class PythonScan:
    render_sites: tuple[RenderSite, ...] = ()
    providers: tuple[ProviderSummary, ...] = ()
    gaps: tuple[AnalysisGap, ...] = ()
    template_roots: tuple[tuple[str, tuple[Path, ...]], ...] = ()
    app_scopes: tuple[str, ...] = ()


def _loc(path: Path, root: Path, node: ast.AST) -> SourceLocation:
    return SourceLocation(path.relative_to(root).as_posix(), getattr(node, "lineno", 1),
                         getattr(node, "col_offset", 0) + 1)


def _str(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _names(node: ast.AST | None) -> tuple[str, ...] | None:
    value = _str(node)
    if value is not None:
        return (value,)
    if isinstance(node, (ast.List, ast.Tuple)):
        values = tuple(_str(item) for item in node.elts)
        return values if all(value is not None for value in values) else None  # type: ignore[return-value]
    return None


def _dict_keys(node: ast.AST) -> tuple[str, ...] | None:
    if isinstance(node, ast.Dict):
        keys = tuple(_str(k) for k in node.keys if k is not None)
        if len(keys) == len(node.keys) and all(k is not None for k in keys):
            return keys  # type: ignore[return-value]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
        keys = tuple(keyword.arg for keyword in node.keywords)
        if all(keys) and not node.args:
            return keys  # type: ignore[return-value]
    return None


def _decorator_name(node: ast.AST) -> str | None:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def scan_project(root: Path) -> PythonScan:
    """Collect Flask evidence without importing, evaluating, or executing source."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("project root is not a directory")

    gaps: list[AnalysisGap] = []
    unsupported: list[AnalysisGap] = []
    sites: list[RenderSite] = []
    providers: list[ProviderSummary] = []
    apps: dict[str, dict] = {}
    blueprints: dict[str, dict] = {}
    functions: dict[str, tuple[ast.AST, Path]] = {}
    trees: list[tuple[Path, ast.Module]] = []
    paths = sorted(p for p in root.rglob("*.py")
                   if not any(part in {".git", ".venv", "tests", "__pycache__"}
                              for part in p.relative_to(root).parts))

    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            line = getattr(exc, "lineno", 1) or 1
            gaps.append(AnalysisGap(FindingCode.PYTHON_SYNTAX,
                                    SourceLocation(path.relative_to(root).as_posix(), line, 1),
                                    "Python source could not be parsed."))
            continue
        except OSError as exc:
            gaps.append(AnalysisGap(FindingCode.UNREADABLE_FILE,
                                    SourceLocation(path.relative_to(root).as_posix(), 1, 1), str(exc)))
            continue
        trees.append((path, tree))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions[node.name] = (node, path)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call = node.value
                target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if isinstance(call.func, ast.Name) and call.func.id == "Flask" and target_names:
                    folder = next((_str(k.value) for k in call.keywords if k.arg == "template_folder"), None)
                    for name in target_names:
                        apps[name] = {"path": path, "folder": folder or "templates", "blueprints": []}
                elif isinstance(call.func, ast.Name) and call.func.id == "Blueprint" and target_names:
                    folder = next((_str(k.value) for k in call.keywords if k.arg == "template_folder"), None)
                    for name in target_names:
                        blueprints[name] = {"path": path, "folder": folder or "templates", "app": None}

    # Registration relationships and literal folder paths.
    for path, tree in trees:
        function_info = []
        for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            route = None
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in {"get", "post", "put", "patch", "delete", "route"} and dec.args:
                    route = _str(dec.args[0])
            function_info.append((fn, fn.name, route))

        def enclosing(node: ast.AST):
            candidates = []
            line = getattr(node, "lineno", 0)
            for fn, name, route in function_info:
                end = getattr(fn, "end_lineno", line)
                if fn.lineno <= line <= end:
                    candidates.append((end - fn.lineno, name, route, fn))
            return min(candidates, default=(0, None, None, None))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            owner = node.func.value.id if isinstance(node.func.value, ast.Name) else None
            if owner in apps and node.func.attr == "register_blueprint" and node.args:
                bp = node.args[0].id if isinstance(node.args[0], ast.Name) else None
                if bp in blueprints:
                    blueprints[bp]["app"] = owner
                    apps[owner]["blueprints"].append(bp)

    default_globals = {"config", "request", "session", "g", "url_for", "get_flashed_messages",
                       "current_user", "csrf_token", "range", "dict", "lipsum", "cycler", "joiner", "namespace"}
    # Provider registrations and render sites are deliberately gathered per source file.
    for path, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorated = {_decorator_name(d) for d in node.decorator_list}
                if decorated & {"context_processor", "app_context_processor"}:
                    keys: set[str] = set(); dynamic = False
                    for child in ast.walk(node):
                        if isinstance(child, ast.Return) and child.value is not None:
                            found = _dict_keys(child.value)
                            if found is None: dynamic = True
                            else: keys.update(found)
                    scope = "app"
                    providers.append(ProviderSummary(definite_keys=keys, unknown_keys=dynamic, scope=scope, origin=_loc(path, root, node)))
                    if dynamic:
                        gaps.append(AnalysisGap(FindingCode.DYNAMIC_PROVIDER, _loc(path, root, node), "Provider keys are not statically enumerable."))
                if decorated & {"template_global"}:
                    providers.append(ProviderSummary(definite_keys={node.name}, scope="app", origin=_loc(path, root, node)))

            if not isinstance(node, ast.Call):
                # Literal assignment to ``*.jinja_env.globals[name]`` is a
                # useful provider even though the object itself is unknown.
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Attribute)
                                and target.value.attr == "globals"):
                            key = _str(target.slice)
                            if key:
                                providers.append(ProviderSummary(definite_keys={key}, scope="app", origin=_loc(path, root, node)))
                            else:
                                gaps.append(AnalysisGap(FindingCode.DYNAMIC_PROVIDER, _loc(path, root, node), "Global name is dynamic."))
                continue
            if isinstance(node.func, ast.Name) and node.func.id in {"Babel", "Moment", "LoginManager", "Environment"}:
                unsupported.append(AnalysisGap(
                    FindingCode.UNSUPPORTED_CUSTOMIZATION, _loc(path, root, node),
                    f"Unsupported extension or loader customization: {node.func.id}."))
            # Explicit registrations such as app.context_processor(fn), and globals APIs.
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"context_processor", "app_context_processor", "add_template_global"}:
                if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in functions:
                    fn, fp = functions[node.args[0].id]
                    keys = set(); dynamic = False
                    for child in ast.walk(fn):
                        if isinstance(child, ast.Return) and child.value is not None:
                            found = _dict_keys(child.value)
                            if found is None: dynamic = True
                            else: keys.update(found)
                    providers.append(ProviderSummary(definite_keys=keys, unknown_keys=dynamic, scope="app", origin=_loc(path, root, node)))
                    if dynamic: gaps.append(AnalysisGap(FindingCode.DYNAMIC_PROVIDER, _loc(path, root, node), "Provider applicability or keys are dynamic."))
                elif node.func.attr == "add_template_global":
                    key = _str(node.args[0]) if node.args else None
                    if key: providers.append(ProviderSummary(definite_keys={key}, scope="app", origin=_loc(path, root, node)))
                    else: gaps.append(AnalysisGap(FindingCode.DYNAMIC_PROVIDER, _loc(path, root, node), "Global name is dynamic."))
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"update", "setdefault"} and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "globals":
                keys = _dict_keys(node.args[0]) if node.args else tuple(k.arg for k in node.keywords) or None
                if keys: providers.append(ProviderSummary(definite_keys=set(keys), scope="app", origin=_loc(path, root, node)))
                else: gaps.append(AnalysisGap(FindingCode.DYNAMIC_PROVIDER, _loc(path, root, node), "Global keys are dynamic."))

            render = isinstance(node.func, ast.Name) and node.func.id == "render_template"
            if not render: continue
            candidates = _names(node.args[0]) if node.args else None
            kwargs = tuple((k.arg, _loc(path, root, k.value)) for k in node.keywords if k.arg is not None)
            unpacked = any(k.arg is None for k in node.keywords)
            app = next(iter(apps), None)
            _, function, route, function_node = enclosing(node)
            gaps_here: list[AnalysisGap] = []
            if candidates is None:
                gaps_here.append(AnalysisGap(FindingCode.DYNAMIC_TEMPLATE, _loc(path, root, node), "Render target is dynamic."))
            if unpacked:
                gaps_here.append(AnalysisGap(FindingCode.UNPACKING, _loc(path, root, node), "Keyword context is unpacked."))
            if function_node is not None:
                for branch in ast.walk(function_node):
                    if isinstance(branch, ast.If):
                        assigned = {target.id for n in ast.walk(branch) if isinstance(n, ast.Assign) for target in n.targets if isinstance(target, ast.Name)}
                        for key, value_loc in kwargs:
                            if isinstance(next((kw.value for kw in node.keywords if kw.arg == key), None), ast.Name) and key in assigned:
                                gaps_here.append(AnalysisGap(FindingCode.BRANCH_FLOW, _loc(path, root, node), f"branch-dependent variable: {key}"))
            sites.append(RenderSite(_loc(path, root, node), function=function, routes=(route,) if route else (),
                                    template_candidates=candidates or (), explicit_kwargs={k for k, _ in kwargs},
                                    explicit_keyword_locations=kwargs, app=app, gaps=tuple(gaps_here)))

    # Any conditional provider registration is uncertain rather than guessed.
    for path, tree in trees:
        for branch in ast.walk(tree):
            if isinstance(branch, (ast.If, ast.Try, ast.For, ast.While)):
                if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"context_processor", "app_context_processor", "add_template_global"} for n in ast.walk(branch)):
                    gaps.append(AnalysisGap(FindingCode.BRANCH_FLOW, _loc(path, root, branch), "Provider registration depends on control flow."))

    # A project-local helper that performs rendering is intentionally opaque at
    # its call sites.  Keep it as a site so callers can retain source identity,
    # but never pretend its arguments have render_template semantics.
        wrappers: set[str] = set()
        for path, tree in trees:
            for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
                has_route = any(isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                                and dec.func.attr in {"get", "post", "put", "patch", "delete", "route"}
                                for dec in fn.decorator_list)
                if not has_route and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "render_template" for n in ast.walk(fn)):
                    wrappers.add(fn.name)
        for node in (n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in wrappers):
            _, function, route, _ = enclosing(node)
            sites.append(RenderSite(_loc(path, root, node), function=function, routes=(route,) if route else (),
                                    gaps=(AnalysisGap(FindingCode.WRAPPER, _loc(path, root, node), "Render wrapper prevents sound attribution."),)))

    roots: list[tuple[str, tuple[Path, ...]]] = []
    for name, info in apps.items():
        app_root = (info["path"].parent / info["folder"]).resolve() if info["folder"] != "templates" else (root / "templates").resolve()
        ordered = [app_root]
        for bp in info["blueprints"]:
            b = blueprints[bp]
            ordered.append((b["path"].parent / b["folder"]).resolve())
        ordered = list(dict.fromkeys(ordered))
        roots.append((name, tuple(ordered)))
    sites = [site for site in sites if not (site.function in wrappers and site.function)]
    if unsupported:
        gap = unsupported[0]
        sites = [RenderSite(site.location, function=site.function, routes=site.routes,
                            app=site.app, blueprint=site.blueprint,
                            template_candidates=site.template_candidates,
                            explicit_kwargs=site.explicit_kwargs,
                            explicit_keyword_locations=site.explicit_keyword_locations,
                            gaps=site.gaps + (gap,)) for site in sites]
    if len(apps) > 1:
        sites = [RenderSite(site.location, function=site.function, routes=site.routes,
                            app=None, blueprint=site.blueprint,
                            template_candidates=site.template_candidates,
                            explicit_kwargs=site.explicit_kwargs,
                            explicit_keyword_locations=site.explicit_keyword_locations,
                            gaps=site.gaps + (AnalysisGap(
                                FindingCode.AMBIGUOUS_ROOTS, site.location,
                                "Multiple independent Flask app scopes make render ownership unresolved."),))
                 for site in sites]
    return PythonScan(tuple(sites), tuple(providers), tuple(gaps), tuple(roots), tuple(apps))
