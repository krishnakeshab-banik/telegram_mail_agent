"""New mail is structured from the owner's words and is not sent by itself."""

from app.services.compose_service import parse_compose, structure_mail


def test_compose_uses_only_the_note_the_owner_wrote() -> None:
    """An address plus a note becomes a draft, and stray addresses do not."""
    request = parse_compose("email priya@example.com asking her to share the invoice by Friday")
    assert request is not None
    assert request.recipient == "priya@example.com"
    assert "invoice" in request.message.lower()
    assert "friday" in request.message.lower()
    assert parse_compose("see ada@college.edu tomorrow") is None
    subject, body = structure_mail(request.message, tone="direct")
    assert "Friday" in subject or "Friday" in body
    assert "Monday" not in body
    assert "invoice" in body.lower()
    assert body.startswith("Hi,")
