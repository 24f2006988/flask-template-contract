"""Reproducible benchmark runner for the pinned public Flask projects."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
import tomllib


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "benchmarks" / ".cache"
RESULTS = ROOT / "benchmarks" / "results"
SELECTION = ROOT / "benchmarks" / "repos.toml"


def repo_id(name: str) -> str:
    return name.replace("/", "__")


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def checkout(repo: dict) -> Path:
    destination = CACHE / repo_id(repo["name"])
    if not (destination / ".git").is_dir():
        result = run(["git", "clone", repo["url"], str(destination)])
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "git clone failed")
    result = run(["git", "fetch", "--quiet", "origin", repo["commit"]], cwd=destination)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git fetch failed")
    result = run(["git", "checkout", "--quiet", "--detach", repo["commit"]], cwd=destination)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git checkout failed")
    return destination


def main() -> int:
    selection = tomllib.loads(SELECTION.read_text(encoding="utf-8"))
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for repo in selection["repos"]:
        started = time.perf_counter()
        record = {"repo": repo["name"], "commit": repo["commit"], "url": repo["url"]}
        try:
            project = checkout(repo)
            templates = sorted(
                path for path in project.rglob("*.html")
                if not any(part in {".git", ".venv", "node_modules"} for part in path.parts)
            )
            try:
                from flask_template_contract.scanner import scan_project
                render_sites = len(scan_project(project).render_sites)
            except Exception:
                render_sites = 0
            result = run([sys.executable, "-m", "flask_template_contract", str(project), "--format", "json"], cwd=ROOT)
            record.update({
                "templates": len(templates),
                "render_sites": render_sites,
                "runtime_seconds": round(time.perf_counter() - started, 3),
            })
            if result.returncode == 2 and not result.stdout.strip():
                record.update({"tool_error": result.stderr.strip() or "tool failure"})
                record.update({"errors": 0, "warnings": 0, "cant_verify": 0})
            else:
                payload = json.loads(result.stdout)
                record.update({
                    "errors": payload["summary"]["errors"],
                    "warnings": payload["summary"]["warnings"],
                    "cant_verify": payload["summary"]["cant_verify"],
                    "report": payload,
                })
        except Exception as exc:
            record.update({"templates": 0, "render_sites": 0,
                          "errors": 0, "warnings": 0, "cant_verify": 0,
                          "runtime_seconds": round(time.perf_counter() - started, 3),
                          "tool_error": str(exc)})
        (RESULTS / f"{repo_id(repo['name'])}.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        rows.append(record)

    lines = ["| Repo | Templates | Render sites | Errors | Warnings | Can't verify | Runtime (s) |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append("| {repo} | {templates} | {render_sites} | {errors} | {warnings} | {cant_verify} | {runtime_seconds} |".format(**row))
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
