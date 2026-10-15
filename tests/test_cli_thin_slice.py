"""Subprocess tests for the first real CLI slice."""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent / "fixtures"


def run_fixture(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "flask_template_contract", str(ROOT / name), *args],
        text=True, capture_output=True, check=False,
    )


def test_clean_and_missing_exit_codes():
    clean = run_fixture("clean")
    missing = run_fixture("missing_variable")
    assert clean.returncode == 0
    assert missing.returncode == 1
    assert "ERROR" in missing.stdout


def test_warning_strictness_and_unknowns_do_not_fail_strict():
    warning = run_fixture("dead_data")
    strict = run_fixture("dead_data", "--strict")
    unknown = run_fixture("kwargs_unpacking", "--strict")
    assert warning.returncode == 0
    assert strict.returncode == 1
    assert unknown.returncode == 0


def test_json_report_has_schema_and_expected_summary():
    result = run_fixture("missing_variable", "--format", "json")
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["schema_version"] == 1
    assert payload["summary"] == {"errors": 1, "warnings": 0, "cant_verify": 0}


def test_dynamic_and_dependency_cases_are_cant_verify():
    for name in ("kwargs_unpacking", "dynamic_template_name", "uses_extends"):
        result = run_fixture(name, "--format", "json")
        payload = json.loads(result.stdout)
        assert result.returncode == 0
        assert payload["complete"] is False
        assert payload["summary"]["cant_verify"] >= 1


def test_builtins_fixture_is_clean():
    result = run_fixture("builtin_globals", "--format", "json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["findings"] == []


def test_bad_root_is_tool_failure():
    result = subprocess.run(
        [sys.executable, "-m", "flask_template_contract", str(ROOT / "does-not-exist")],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2


def test_context_processor_literal_keys_are_supported(tmp_path):
    (tmp_path / "app.py").write_text(
        "from flask import Flask, render_template\n"
        "app = Flask(__name__)\n"
        "@app.context_processor\n"
        "def inject():\n"
        "    return {'account_name': 'x'}\n"
        "@app.get('/')\n"
        "def home():\n"
        "    return render_template('home.html')\n",
        encoding="utf-8",
    )
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "home.html").write_text("{{ account_name }}", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "flask_template_contract", str(tmp_path), "--format", "json"],
        text=True, capture_output=True, check=False,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["complete"] is True
    assert payload["summary"]["cant_verify"] == 0
    assert payload["summary"]["errors"] == 0
