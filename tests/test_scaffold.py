"""Smoke check for the installed package; no analyzer exists yet."""

from flask_template_contract import __version__


def test_package_version():
    assert __version__ == "0.1.0"
