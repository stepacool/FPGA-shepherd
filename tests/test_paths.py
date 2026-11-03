from __future__ import annotations

from pathlib import Path

from shepherd.checks.paths import PathRewriter


def test_rewrites_relative_and_absolute_staged_paths(tmp_path: Path):
    stage = tmp_path / ".shepherd" / "build"
    user = tmp_path / "rtl" / "blinky.sv"
    rewrite = PathRewriter({stage / "src/000_blinky.sv": user}, stage, tmp_path)

    assert (
        rewrite("src/000_blinky.sv:36: ERROR: syntax error")
        == "rtl/blinky.sv:36: ERROR: syntax error"
    )
    assert rewrite(f"Parsing `{stage}/src/000_blinky.sv'") == "Parsing `rtl/blinky.sv'"
    assert rewrite("no paths here") == "no paths here"


def test_does_not_rewrite_partial_matches(tmp_path: Path):
    stage = tmp_path / "s"
    rewrite = PathRewriter({stage / "src/000_a.v": tmp_path / "a.v"}, stage, tmp_path)
    assert rewrite("other/src/000_a.v") == "other/src/000_a.v"


def test_empty_map():
    assert PathRewriter({}, Path("/s"), Path("/"))("x") == "x"


def test_verify_agent_rewrites_staged_paths_in_cause(tmp_path: Path):
    from shepherd.agents.verify import VerifyAgent

    stage = tmp_path / ".shepherd" / "build"
    user = tmp_path / "rtl" / "blinky.sv"
    rewrite = PathRewriter({stage / "src/000_blinky.sv": user}, stage, tmp_path)
    log = "src/000_blinky.sv:3: ERROR: syntax error, unexpected TOK_BEGIN\n"
    verdict = VerifyAgent().run(cfg=None, logs={"build": log}, rewrite=rewrite)
    assert verdict.level == "fail"
    joined = " ".join((f.cause or "") + " " + (f.fix or "") for f in verdict.findings)
    assert "rtl/blinky.sv" in joined
    assert "src/000_blinky.sv" not in joined
