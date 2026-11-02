"""Trivial package smoke tests (#1)."""

from __future__ import annotations


def test_import_shepherd():
    import shepherd

    assert isinstance(shepherd.__version__, str)
    assert shepherd.__version__


def test_cli_entrypoint_importable():
    from shepherd.cli import main

    assert callable(main)
