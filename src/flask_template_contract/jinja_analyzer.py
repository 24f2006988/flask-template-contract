"""Frozen interface for scope-aware Jinja template analysis."""

from __future__ import annotations

from pathlib import Path

from .models import TemplateSummary


def analyze_template(
    root: Path,
    template_path: Path,
    *,
    lookup_roots: tuple[Path, ...],
) -> TemplateSummary:
    """Analyze one template using the supplied ordered lookup roots.

    The implementation must report an ambiguity gap when a dependency name
    exists in more than one searched root; it must never silently choose the
    first match. Imported macro-body free-variable analysis remains deferred by
    the v1 contract.
    """

    raise NotImplementedError
