from __future__ import annotations

from pathlib import Path

import pytest

from shepherd.backend.apio.translate import translate_line
from shepherd.context import Context
from shepherd.errors import NetworkRequired
from shepherd.output import Output

FIXTURES = Path(__file__).parent / "fixtures" / "apio"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("run apio drivers --install", "run shepherd doctor --fix --install"),
        ("see apio devices list", "see shepherd doctor --fix list"),
        ("please run apio packages install", "please run shepherd init"),
        ("edit apio.ini and retry", "edit shepherd.toml and retry"),
        ("Using env default (sipeed-tang-nano-9k)", None),
        ("Setting shell vars.", None),
        ("-" * 40, None),
        ("yosys -p synth_gowin", "yosys -p synth_gowin"),
        ("nextpnr-himbaechel --device X", "nextpnr-himbaechel --device X"),
        ("gowin_pack -d GW1N-9C", "gowin_pack -d GW1N-9C"),
        ("openFPGALoader -b tangnano9k", "openFPGALoader -b tangnano9k"),
        ("ERROR: something from apio helper", "ERROR: something from the build backend helper"),
    ],
)
def test_translate_rules(raw: str, expected: str | None):
    assert translate_line(raw) == expected


def test_fixture_logs_have_no_apio_after_translate():
    for path in FIXTURES.glob("*.log"):
        for line in path.read_text().splitlines():
            out = translate_line(line)
            if out is None:
                continue
            assert "apio" not in out.lower(), (path.name, out)


def test_network_required_rendering(capsys):
    out = Output(Context())
    out.error(NetworkRequired("toolchain install", failed="Connection refused"))
    text = capsys.readouterr().out
    assert "internet required for toolchain install" in text
    assert "what failed: Connection refused" in text
    assert "shepherd init" in text


def test_offline_toolchain_install_exits_3(tmp_path: Path, monkeypatch):
    from typer.testing import CliRunner

    from shepherd import cli

    class OfflineBackend:
        def ensure_toolchain(self, sink):
            raise OSError("Network is unreachable")

    monkeypatch.setattr("shepherd.init_cmd.get_backend", lambda dry_run=False: OfflineBackend())
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "blinky.sv").write_text("module blinky; endmodule\n")
    (tmp_path / "shepherd.toml").write_text(
        'board = "tangnano9k"\ntop = "blinky"\nsources = ["rtl/blinky.sv"]\n'
    )
    result = CliRunner().invoke(cli.app, ["--project", str(tmp_path), "init"])
    assert result.exit_code == 3, result.output
    assert "internet required for toolchain install" in result.output
