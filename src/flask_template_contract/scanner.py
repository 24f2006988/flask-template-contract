"""Frozen interface for static Python/Flask source scanning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import AnalysisGap, ProviderSummary, RenderSite


@dataclass(frozen=True)
class PythonScan:
    """Evidence extracted from a project without importing or executing it.

    ``template_roots`` contains ``(scope, roots)`` pairs. Each ``roots`` tuple
    is an ordered lookup sequence for that app or blueprint scope: the app
    template folder first, followed by blueprint folders in registration
    order. The lead must preserve this order and report collisions.

    ``app_scopes`` contains stable names for the discovered app ownership
    scopes. It is a separate inventory so callers can distinguish a project
    with no statically identifiable app from one with render sites and roots.
    """

    render_sites: tuple[RenderSite, ...] = ()
    providers: tuple[ProviderSummary, ...] = ()
    gaps: tuple[AnalysisGap, ...] = ()
    template_roots: tuple[tuple[str, tuple[Path, ...]], ...] = ()
    app_scopes: tuple[str, ...] = ()


def scan_project(root: Path) -> PythonScan:
    """Statically scan Python sources under ``root``.

    Implemented by the Python-scanner worker. This stub freezes the integration
    boundary before parallel implementation begins.
    """

    raise NotImplementedError
