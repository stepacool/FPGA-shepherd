"""OpenAI-compatible chat client for Meta Llama (httpx, no SDK)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from shepherd.errors import NetworkRequired
from shepherd.llm.envfile import load_dotenv

DEFAULT_BASE_URL = "https://api.llama.com/compat/v1"
DEFAULT_MODEL = "Llama-4-Maverick-17B-128E-Instruct-FP8"


@dataclass(frozen=True)
class LlmConfig:
    api_key: str
    base_url: str
    model: str

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def load_config(project_root: Path | None = None) -> LlmConfig:
    if project_root is not None:
        load_dotenv(project_root / ".env")
    load_dotenv(Path.cwd() / ".env")
    return LlmConfig(
        api_key=os.environ.get("META_API_KEY", "").strip(),
        base_url=(os.environ.get("META_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        model=os.environ.get("META_MODEL") or DEFAULT_MODEL,
    )


@dataclass
class ChatResult:
    text: str
    parsed: dict[str, Any] | None = None


class LlmClient:
    def __init__(self, config: LlmConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        self._transport = transport

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.1) -> ChatResult:
        if not self.config.enabled:
            raise RuntimeError("LLM client used without META_API_KEY")
        url = f"{self.config.base_url}/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(transport=self._transport, timeout=60.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as e:
            raise NetworkRequired("AI explanation", failed=str(e)) from e

        text = data["choices"][0]["message"]["content"]
        parsed = _try_parse_json(text)
        return ChatResult(text=text, parsed=parsed)


def _try_parse_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None
