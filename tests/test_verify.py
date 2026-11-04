from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from shepherd import cli
from shepherd.agents.verify import VerifyAgent
from shepherd.knowledge.signatures import match_log

FIXTURES = Path(__file__).parent / "fixtures" / "apio"
runner = CliRunner()


def test_seed_signatures_match_fixtures():
    cases = [
        ("build_pnr_unconstrained.log", "nextpnr-unconstrained-io"),
        ("build_syntax_error.log", "yosys-syntax-error"),
    ]
    for name, expected_id in cases:
        text = (FIXTURES / name).read_text()
        matches = match_log(text, constraints="tangnano9k.cst")
        assert matches, name
        assert matches[0].signature.id == expected_id, (name, matches)
        assert matches[0].cause and matches[0].fix


def test_unconstrained_obuf_port_normalized():
    text = (FIXTURES / "build_pnr_unconstrained.log").read_text()
    matches = match_log(text, constraints="tangnano9k.cst")
    assert matches[0].groups["port"] == "led[5]"
    assert "led[5]" in matches[0].cause
    assert "OBUF" not in matches[0].cause


def test_verify_agent_on_unconstrained_log():
    text = (FIXTURES / "build_pnr_unconstrained.log").read_text()
    verdict = VerifyAgent().explain_text(text)
    assert verdict.level == "fail"
    assert any(
        "unconstrained" in (f.cause or "").lower() or "IO_LOC" in (f.fix or "")
        for f in verdict.findings
    )


def test_explain_log_without_project(tmp_path: Path):
    log = tmp_path / "fail.log"
    log.write_text((FIXTURES / "build_pnr_unconstrained.log").read_text())
    # No shepherd.toml in tmp_path — explain must still work with an explicit log.
    result = runner.invoke(cli.app, ["--project", str(tmp_path), "explain", str(log)])
    assert result.exit_code == 1, result.output
    assert "cause:" in result.output
    assert "fix:" in result.output
    assert "apio" not in result.output.lower()


def test_pipeline_fail_prints_signature_cause(project: Path, monkeypatch):
    from test_pipeline import PNR_FAIL_SCRIPT, FakeBackend

    from shepherd import pipeline

    monkeypatch.setattr(
        pipeline,
        "get_backend",
        lambda dry_run=False: FakeBackend(build_script=PNR_FAIL_SCRIPT, build_code=2),
    )
    result = runner.invoke(cli.app, ["--project", str(project), "build"])
    assert result.exit_code == 1, result.output
    assert "cause:" in result.output
    assert "fix:" in result.output
    assert "led[5]" in result.output
    assert "checkpoint" not in result.output
    assert result.output.count("pnr") >= 1
    # One FAIL banner for pnr — not a second "pnr FAIL checkpoint".
    assert result.output.count("FAIL") >= 1
    assert "FAIL checkpoint" not in result.output


def test_verify_pass_on_clean_upload_does_not_call_ai(project: Path, monkeypatch):
    """Successful upload + no signatures → pass; AI must not invent a failure."""
    from shepherd.events.db import EventStore
    from shepherd.events.logs import RunDir
    from shepherd.llm import diagnose

    store = EventStore.open(project)
    run = store.start_run("upload", board="tangnano9k", run_id="upload-ok")
    run_dir = RunDir(project, run.id)
    run_dir.path.mkdir(parents=True, exist_ok=True)
    run_dir.log_path("upload").write_text(
        "JTAG chainpos: 0 Device IDCODE: 0x...\nSRAM load: 100% done\nCRC check: Success\nDONE\n"
    )
    run.finish("pass")
    store.close()

    def boom(**_kwargs):
        raise AssertionError("AI must not run on a clean successful upload")

    monkeypatch.setattr(diagnose, "ai_findings", boom)
    result = runner.invoke(cli.app, ["--project", str(project), "verify"])
    assert result.exit_code == 0, result.output
    assert "pass" in result.output.lower() or "no known error" in result.output.lower()
