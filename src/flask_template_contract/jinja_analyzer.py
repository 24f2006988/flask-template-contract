"""Static, scope-aware analysis of Jinja templates."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from jinja2 import Environment, TemplateSyntaxError, nodes
from jinja2.visitor import NodeVisitor

from .models import AnalysisGap, FindingCode, SourceLocation, TemplateRequirement, TemplateSummary

_GLOBALS = {"range", "dict", "lipsum", "cycler", "joiner", "namespace",
            "config", "request", "session", "g", "url_for",
            "get_flashed_messages", "current_user", "csrf_token"}


class _Walker(NodeVisitor):
    def __init__(self, owner: "_Analysis", chain: tuple[str, ...], initial: Iterable[str] = ()):
        self.owner, self.chain = owner, chain
        self.scopes: list[set[str]] = [set(initial) | _GLOBALS | {"self", "super"}]
        self.guarded: set[str] = set()

    def loc(self, node: nodes.Node) -> SourceLocation:
        return self.owner.location(getattr(node, "lineno", 1))

    def bound(self, name: str) -> bool:
        return any(name in scope for scope in reversed(self.scopes))

    def bind_target(self, target: nodes.Node, scope: set[str] | None = None) -> None:
        scope = scope if scope is not None else self.scopes[-1]
        if isinstance(target, nodes.Name): scope.add(target.name)
        elif isinstance(target, (nodes.Tuple, nodes.List)):
            for item in target.items: self.bind_target(item, scope)

    def use(self, name: str, node: nodes.Node) -> None:
        if not self.bound(name):
            guarded = name in self.guarded
            self.owner.requirements.append(TemplateRequirement(
                name, required=not guarded, guarded=guarded,
                location=self.loc(node), dependency_chain=self.chain))
            self.owner.external.add(name)

    def visit_Name(self, node: nodes.Name, *args) -> None:
        if node.ctx == "load": self.use(node.name, node)

    def visit_If(self, node: nodes.If, *args) -> None:
        # Definedness tests are reads, but protect only the corresponding branch.
        name, positive = self.owner.defined_test(node.test)
        old = set(self.guarded)
        if name: self.guarded.add(name)
        self.visit(node.test)
        self.guarded = old
        if name:
            old = set(self.guarded); self.guarded.add(name)
            for child in (node.body if positive else node.else_): self.visit(child)
            self.guarded = old
            for child in (node.else_ if positive else node.body): self.visit(child)
        else:
            for child in node.body: self.visit(child)
            for child in node.else_: self.visit(child)

    def visit_Set(self, node: nodes.Set, *args) -> None:
        self.visit(node.value)
        self.bind_target(node.target)

    def visit_Assign(self, node: nodes.Assign, *args) -> None:
        self.visit(node.node)
        self.bind_target(node.target)

    def visit_For(self, node: nodes.For, *args) -> None:
        self.visit(node.iter)
        local = set(self.scopes[-1]); self.bind_target(node.target, local); local.update({"loop"})
        self.scopes.append(local)
        for child in node.body: self.visit(child)
        for child in node.else_: self.visit(child)
        self.scopes.pop()

    def visit_With(self, node: nodes.With, *args) -> None:
        local = set(self.scopes[-1])
        for target, value in zip(node.targets, node.values):
            self.visit(value); self.bind_target(target, local)
        self.scopes.append(local)
        for child in node.body: self.visit(child)
        self.scopes.pop()

    def visit_AssignBlock(self, node: nodes.AssignBlock, *args) -> None:
        # A block assignment's body is evaluated before its value is bound.
        for child in node.body: self.visit(child)
        self.bind_target(node.target)

    def visit_Macro(self, node: nodes.Macro, *args) -> None:
        self.scopes[-1].add(node.name)
        local = set(self.scopes[-1]) | {"caller", "varargs", "kwargs"}
        for arg, default in zip(node.args, node.defaults):
            self.visit(default); self.bind_target(arg, local)
        self.scopes.append(local)
        for child in node.body: self.visit(child)
        self.scopes.pop()

    def visit_CallBlock(self, node: nodes.CallBlock, *args) -> None:
        self.visit(node.call)
        local = set(self.scopes[-1]) | {"caller"}
        for arg in node.args: self.bind_target(arg, local)
        self.scopes.append(local)
        for child in node.body: self.visit(child)
        self.scopes.pop()

    def visit_Import(self, node: nodes.Import, *args) -> None:
        self.owner.dependency(node.template, node, imported=True)
        self.scopes[-1].add(node.target)

    def visit_FromImport(self, node: nodes.FromImport, *args) -> None:
        self.owner.dependency(node.template, node, imported=True)
        for name in node.names:
            self.scopes[-1].add(name if isinstance(name, str) else name[1])

    def visit_Extends(self, node: nodes.Extends, *args) -> None:
        self.owner.parent = node

    def visit_Include(self, node: nodes.Include, *args) -> None:
        self.owner.dependency(node.template, node, imported=False)

    def visit_Filter(self, node: nodes.Filter, *args) -> None:
        self.visit(node.node)
        for arg in node.args: self.visit(arg)
        for kw in node.kwargs: self.visit(kw.value)

    def visit_Call(self, node: nodes.Call, *args) -> None:
        self.visit(node.node)
        for arg in node.args: self.visit(arg)
        for kw in node.kwargs: self.visit(kw.value)
        if node.dyn_args: self.visit(node.dyn_args)
        if node.dyn_kwargs: self.visit(node.dyn_kwargs)

    def visit_Getattr(self, node: nodes.Getattr, *args) -> None: self.visit(node.node)
    def visit_Getitem(self, node: nodes.Getitem, *args) -> None:
        self.visit(node.node); self.visit(node.arg)

    def visit_Const(self, node: nodes.Const, *args) -> None: pass

    def visit_BinExpr(self, node, *args) -> None:
        self.visit(node.left); self.visit(node.right)

    def visit_Or(self, node: nodes.Or, *args) -> None:
        # The left root is protected by its fallback; right-hand reads are not.
        old = set(self.guarded); self.guarded |= self.owner.roots(node.left)
        self.visit(node.left); self.guarded = old; self.visit(node.right)

    def visit_Filter(self, node: nodes.Filter, *args) -> None:
        old = set(self.guarded)
        if node.name == "default": self.guarded |= self.owner.roots(node.node)
        self.visit(node.node); self.guarded = old
        for arg in node.args: self.visit(arg)
        for kw in node.kwargs: self.visit(kw.value)


class _Analysis:
    def __init__(self, root: Path, lookup: tuple[Path, ...]):
        self.root, self.lookup = root, lookup
        self.requirements: list[TemplateRequirement] = []
        self.external: set[str] = set(); self.dependencies: list[str] = []
        self.gaps: list[AnalysisGap] = []; self.stack: list[Path] = []
        self.parent: nodes.Extends | None = None

    def rel(self, path: Path) -> str:
        try: return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError: return path.name

    def location(self, line: int) -> SourceLocation:
        return SourceLocation(self.rel(self.stack[-1]), max(1, line))

    def roots(self, node: nodes.Node) -> set[str]:
        out: set[str] = set()
        if isinstance(node, nodes.Name) and node.ctx == "load": out.add(node.name)
        for n in node.find_all(nodes.Name):
            if n.ctx == "load": out.add(n.name)
        return out

    def defined_test(self, node: nodes.Node) -> tuple[str | None, bool]:
        if isinstance(node, nodes.Test) and node.name == "defined" and isinstance(node.node, nodes.Name):
            return node.node.name, True
        if isinstance(node, nodes.Not) and isinstance(node.node, nodes.Test):
            t = node.node
            if t.name == "defined" and isinstance(t.node, nodes.Name): return t.node.name, False
        return None, True

    def literal(self, node: nodes.Node) -> str | None:
        return node.value if isinstance(node, nodes.Const) and isinstance(node.value, str) else None

    def dependency(self, expr: nodes.Node, node: nodes.Node, imported: bool) -> None:
        name = self.literal(expr)
        if name is None:
            self.gaps.append(AnalysisGap(FindingCode.DYNAMIC_DEPENDENCY, self.location(node.lineno), "dynamic template dependency")); return
        self.dependencies.append(name)
        matches = [r / name for r in self.lookup if (r / name).is_file()]
        if len(matches) > 1:
            self.gaps.append(AnalysisGap(FindingCode.AMBIGUOUS_ROOTS, self.location(node.lineno), f"template {name!r} exists in multiple lookup roots")); return
        if not matches:
            if not (not imported and getattr(node, "ignore_missing", False)):
                self.gaps.append(AnalysisGap(FindingCode.MISSING_TEMPLATE, self.location(node.lineno), f"template {name!r} was not found"))
            return
        if imported: return  # imported macro bodies are deliberately deferred
        self.walk(matches[0], (name,) + tuple(self.stack_names()))

    def stack_names(self): return tuple(self.rel(p) for p in self.stack)

    def walk(self, path: Path, chain: tuple[str, ...], overrides: dict[str, nodes.Block] | None = None,
             initial: Iterable[str] = ()) -> None:
        path = path.resolve()
        if path in self.stack:
            self.gaps.append(AnalysisGap(FindingCode.CYCLE, SourceLocation(self.rel(path), 1), "template dependency cycle")); return
        self.stack.append(path)
        try: source = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.gaps.append(AnalysisGap(FindingCode.UNREADABLE_FILE, self.location(1), str(exc))); self.stack.pop(); return
        try: tree = Environment().parse(source)
        except TemplateSyntaxError as exc:
            self.gaps.append(AnalysisGap(FindingCode.TEMPLATE_SYNTAX, self.location(exc.lineno or 1), str(exc))); self.stack.pop(); return
        self.parent = None
        blocks = {b.name: b for b in tree.find_all(nodes.Block)}
        has_extends = any(isinstance(item, nodes.Extends) for item in tree.body)
        walker = _Walker(self, chain, initial)
        for child in tree.body:
            if isinstance(child, nodes.Extends): self.parent = child; continue
            if has_extends and isinstance(child, nodes.Block): continue
            if isinstance(child, nodes.Block) and overrides and child.name in overrides:
                # The child implementation replaces the parent's block.
                replacement = overrides[child.name]
                for item in replacement.body: walker.visit(item)
                # ``super()`` reintroduces the parent implementation.
                if any(isinstance(call, nodes.Call) and isinstance(call.node, nodes.Name)
                       and call.node.name == "super" for call in replacement.find_all(nodes.Call)):
                    for item in child.body: walker.visit(item)
                continue
            walker.visit(child)
        if self.parent:
            parent_name = self.literal(self.parent.template)
            if parent_name is None:
                self.gaps.append(AnalysisGap(FindingCode.DYNAMIC_DEPENDENCY, self.location(self.parent.lineno), "dynamic extends"))
            else:
                matches = [r / parent_name for r in self.lookup if (r / parent_name).is_file()]
                self.dependencies.append(parent_name)
                if len(matches) > 1: self.gaps.append(AnalysisGap(FindingCode.AMBIGUOUS_ROOTS, self.location(self.parent.lineno), "ambiguous parent template"))
                elif not matches: self.gaps.append(AnalysisGap(FindingCode.MISSING_TEMPLATE, self.location(self.parent.lineno), f"template {parent_name!r} was not found"))
                else:
                    inherited = set(walker.scopes[0]) - _GLOBALS - {"self", "super"}
                    self.walk(matches[0], (parent_name,) + chain, blocks, inherited)
        self.stack.pop()

    def result(self, path: Path) -> TemplateSummary:
        self.walk(path.resolve(), (self.rel(path),))
        return TemplateSummary(tuple(self.requirements), frozenset(self.external), tuple(dict.fromkeys(self.dependencies)), tuple(self.gaps))


def analyze_template(root: Path, template_path: Path, *, lookup_roots: tuple[Path, ...]) -> TemplateSummary:
    """Analyze a template without importing or executing the application."""
    return _Analysis(root, tuple(Path(p) for p in lookup_roots)).result(Path(template_path))
