from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from shepherd.checks.paths import PathRewriter
from shepherd.config import ProjectConfig
from shepherd.llm.client import LlmClient, LlmConfig
from shepherd.llm.envfile import load_dotenv
from shepherd.llm.prompt import MAX_LOG_CHARS, build_diagnosis_messages, trim_around_error


def test_load_dotenv_does_not_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("META_API_KEY", "from-env")
    monkeypatch.delenv("META_MODEL", raising=False)
    (tmp_path / ".env").write_text("META_API_KEY=from-file\nMETA_MODEL=file-model\n")
    load_dotenv(tmp_path / ".env")
    import os

    assert os.environ["META_API_KEY"] == "from-env"
    assert os.environ["META_MODEL"] == "file-model"


def test_client_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["model"] == "test-model"
        assert body["messages"][0]["role"] == "system"
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"cause": "missing IO_LOC", "fix": "add pin", "confidence": 0.9}
                        )
                    }
                }
            ]
        }
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = LlmClient(
        LlmConfig(api_key="k", base_url="https://example.test/v1", model="test-model"),
        transport=transport,
    )
    result = client.chat([{"role": "system", "content": "x"}, {"role": "user", "content": "y"}])
    assert result.parsed == {"cause": "missing IO_LOC", "fix": "add pin", "confidence": 0.9}


def test_client_network_error():
    from shepherd.errors import NetworkRequired

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    client = LlmClient(
        LlmConfig(api_key="k", base_url="https://example.test/v1", model="m"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(NetworkRequired) as ei:
        client.chat([{"role": "user", "content": "hi"}])
    assert ei.value.what == "AI explanation"


def test_prompt_builder_no_apio_and_size_cap(tmp_path: Path):
    src = tmp_path / "rtl" / "blinky.sv"
    src.parent.mkdir()
    src.write_text("module blinky; endmodule\n")
    (tmp_path / "tangnano9k.cst").write_text('IO_LOC "clk" 52;\n')
    cfg = ProjectConfig(
        root=tmp_path,
        board="tangnano9k",
        top="blinky",
        sources=["rtl/blinky.sv"],
        constraints="tangnano9k.cst",
    )
    stage = tmp_path / ".shepherd" / "build"
    rewrite = PathRewriter({stage / "src/000_blinky.sv": src}, stage, tmp_path)
    huge = "info\n" + ("x" * (MAX_LOG_CHARS + 500)) + "\nERROR: boom\n" + ("y" * 1000)
    huge = f"see apio.ini and run apio drivers\n{huge}"
    messages = build_diagnosis_messages(
        cfg=cfg,
        logs={"build": huge},
        step="build",
        rewrite=rewrite,
    )
    blob = "\n".join(m["content"] for m in messages)
    assert "apio" not in blob.lower()
    assert "shepherd.toml" in blob or "shepherd doctor" in blob
    assert len(messages[1]["content"]) < len(huge) + 5000


def test_trim_around_error():
    text = "a" * 100 + "ERROR here" + "b" * 100
    trimmed = trim_around_error(text, limit=50)
    assert "ERROR" in trimmed
    assert len(trimmed) <= 50
