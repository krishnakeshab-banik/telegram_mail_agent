"""The model chain comes from configuration and contains no names in app code."""

from pathlib import Path

import pytest
from app.ai.gemini_client import GeminiClient
from app.exceptions import GeminiError, ModelUnavailable
from pydantic import BaseModel


class _Ping(BaseModel):
    ok: bool = True


def test_app_package_has_no_model_names() -> None:
    root = Path(__file__).resolve().parents[2] / "app"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "gemini-" not in text
        assert "GEMINI_MODEL_FAST" not in text
        assert "GEMINI_MODEL_SMART" not in text


@pytest.mark.asyncio
async def test_chain_skips_unavailable_models_and_alerts_once() -> None:
    notices: list[str] = []

    async def _alert(text: str) -> None:
        notices.append(text)

    client = GeminiClient("key", requests_per_minute=100, models=("first", "second"))
    client.set_chain_handler(_alert)
    seen: list[str] = []

    async def _fake(
        _self: GeminiClient,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: type[_Ping],
    ) -> str:
        del system_prompt, user_prompt, schema
        seen.append(model)
        if model == "first":
            raise ModelUnavailable(404)
        return '{"ok": true}'

    client._generate = _fake.__get__(client, GeminiClient)  # type: ignore[method-assign]
    payload = await client.generate_json(system_prompt="x", user_prompt="y", schema=_Ping)
    assert payload["ok"] is True
    assert seen == ["first", "second"]
    assert client.last_model == "second"
    assert notices == []
    await client.generate_json(system_prompt="x", user_prompt="y", schema=_Ping)
    assert seen[2] == "second"

    async def _down(
        _self: GeminiClient,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: type[_Ping],
    ) -> str:
        del system_prompt, user_prompt, schema
        raise ModelUnavailable(503 if model == "second" else 429)

    client._working = ""
    client._generate = _down.__get__(client, GeminiClient)  # type: ignore[method-assign]
    with pytest.raises(GeminiError):
        await client.generate_json(system_prompt="x", user_prompt="y", schema=_Ping)
    assert len(notices) == 1
    assert "429" in notices[0]
    assert "503" in notices[0]
    with pytest.raises(GeminiError):
        await client.generate_json(system_prompt="x", user_prompt="y", schema=_Ping)
    assert len(notices) == 1
