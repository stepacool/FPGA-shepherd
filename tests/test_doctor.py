from __future__ import annotations

from pathlib import Path

from shepherd.backend.base import StepResult
from shepherd.context import Context
from shepherd.doctor import run_checks, run_doctor
from shepherd.output import Output


class FakeBackend:
    name = "fake"

    def version(self):
        return "1.6.0"

    def devices(self):
        return ["FTDI 0403:6010"]

    def install_drivers(self, kind="ftdi"):
        return ["echo drivers"]

    def ensure_toolchain(self, sink):
        return StepResult("toolchain", True, 0, None)


def test_run_checks_ok(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("META_API_KEY", "x")
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "blinky.v").write_text("module blinky; endmodule\n")
    (tmp_path / "tangnano9k.cst").write_text('IO_LOC "clk" 52;\n')
    (tmp_path / "shepherd.toml").write_text(
        'board = "tangnano9k"\ntop = "blinky"\nsources = ["rtl/blinky.v"]\n'
        'constraints = "tangnano9k.cst"\n'
    )
    items = run_checks(FakeBackend(), tmp_path)
    by_id = {i.id: i for i in items}
    assert by_id["python"].status == "ok"
    assert by_id["backend"].status == "ok"
    assert by_id["device"].status == "ok"
    assert by_id["project"].status == "ok"
    assert by_id["ai"].status == "ok"
    assert "apio" not in " ".join(i.message for i in items).lower()


def test_doctor_json(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr("shepherd.doctor.get_backend", lambda dry_run=False: FakeBackend())
    ctx = Context(project=tmp_path, json=True, yes=True)
    report = run_doctor(ctx, Output(ctx), fix=False)
    assert report.to_dict()["ok"] or any(i.status == "warn" for i in report.items)
    # Human output goes to stderr when json=True
    _ = capsys.readouterr()
