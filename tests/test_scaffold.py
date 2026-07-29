"""Smoke test for the project scaffold. Real tests arrive with Phase 1."""

import src


def test_package_imports():
    assert src.__version__ == "0.0.0"
