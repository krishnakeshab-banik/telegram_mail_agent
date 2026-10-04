"""Natural-language routing in demo mode, where no Gemini key is configured."""

from app.services.container import Container


async def test_pending_question_lists_deadlines_without_sending(agent: Container) -> None:
    await agent.sync.sync_inbox()
    await agent.pipeline.process_pending()
    result = await agent.queries.handle(42, "what's pending this week?")
    assert result.kind == "text"
    outbox = agent.sync._mailbox._outbox_path  # type: ignore[attr-defined]
    assert not outbox.exists()


async def test_preference_command_is_stored(agent: Container) -> None:
    result = await agent.queries.handle(42, "tone formal")
    assert "tone" in result.text.lower()
    prefs = await agent.preferences.get()
    assert prefs.tone == "formal"
