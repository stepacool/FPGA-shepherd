from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from shepherd import cli, ui_cmd
from shepherd.context import Context
from shepherd.output import Output

runner = CliRunner()


def test_ui_help_lists_stop_restart():
    result = runner.invoke(cli.app, ["ui", "--help"])
    assert result.exit_code == 0
    assert "stop" in result.output
    assert "restart" in result.output
    assert "start" in result.output


def test_ui_stop_nothing_running(tmp_path: Path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text("{}\n")
    monkeypatch.setenv("SHEPHERD_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ui_cmd, "_pids_on_port", lambda port: [])
    monkeypatch.setattr(ui_cmd, "_port_up", lambda port: False)

    result = runner.invoke(cli.app, ["ui", "stop"])
    assert result.exit_code == 0, result.output
    assert "not running" in result.output.lower()


def test_stop_ui_kills_recorded_pid(tmp_path: Path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text("{}\n")
    pid_file = web / ui_cmd.PID_NAME
    pid_file.write_text(json.dumps({"pid": 424242, "port": 3010}) + "\n")

    killed: list[int] = []

    def fake_alive(pid: int) -> bool:
        return pid == 424242 and pid not in killed

    def fake_kill_pid(pid: int) -> None:
        killed.append(pid)

    monkeypatch.setattr(ui_cmd, "_alive", fake_alive)
    monkeypatch.setattr(ui_cmd, "_kill_pid", fake_kill_pid)
    monkeypatch.setattr(ui_cmd, "_pids_on_port", lambda port: [])
    monkeypatch.setattr(ui_cmd, "_port_up", lambda port: False)
    monkeypatch.setenv("SHEPHERD_ROOT", str(tmp_path))

    ctx = Context(project=tmp_path)
    code = ui_cmd.stop_ui(ctx, Output(ctx))
    assert code == 0
    assert not pid_file.exists()
    assert 424242 in killed


def test_start_ui_writes_pid(tmp_path: Path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text("{}\n")
    (web / "node_modules").mkdir()
    nxt = web / ".next"
    nxt.mkdir()
    (nxt / "BUILD_ID").write_text("x\n")
    route = nxt / "server" / "app" / "api" / "defaults"
    route.mkdir(parents=True)
    (route / "route.js").write_text("export {}\n")

    class FakeProc:
        pid = 99901

    monkeypatch.setattr(ui_cmd, "_ui_healthy", lambda port: False)
    monkeypatch.setattr(ui_cmd, "_port_up", lambda port: False)
    monkeypatch.setattr(ui_cmd, "_pids_on_port", lambda port: [])
    monkeypatch.setattr(ui_cmd, "_wait_healthy", lambda port, timeout_s=20.0: True)
    monkeypatch.setattr(
        ui_cmd.subprocess,
        "Popen",
        lambda *a, **k: FakeProc(),
    )
    monkeypatch.setattr(ui_cmd.webbrowser, "open", lambda url: None)
    monkeypatch.setenv("SHEPHERD_ROOT", str(tmp_path))

    ctx = Context(project=tmp_path)
    code = ui_cmd.start_ui(ctx, Output(ctx), port=3010, open_browser=False)
    assert code == 0
    state = json.loads((web / ui_cmd.PID_NAME).read_text())
    assert state == {"pid": 99901, "port": 3010}


def test_start_skips_spawn_when_healthy(tmp_path: Path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text("{}\n")
    monkeypatch.setenv("SHEPHERD_ROOT", str(tmp_path))
    monkeypatch.setattr(ui_cmd, "_ui_healthy", lambda port: True)
    opened: list[str] = []
    monkeypatch.setattr(ui_cmd.webbrowser, "open", lambda url: opened.append(url))

    ctx = Context(project=tmp_path)
    code = ui_cmd.start_ui(ctx, Output(ctx), port=3010, open_browser=True)
    assert code == 0
    assert opened
    assert not (web / ui_cmd.PID_NAME).exists()
