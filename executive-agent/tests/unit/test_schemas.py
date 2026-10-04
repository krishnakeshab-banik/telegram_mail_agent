"""Classifier schema validation."""

import pytest
from app.ai.schemas import EmailClassification
from app.constants import Category, Urgency
from pydantic import ValidationError


def test_summary_is_clipped_to_two_lines() -> None:
    parsed = EmailClassification.model_validate(
        {
            "category": "work",
            "importance_score": 80,
            "urgency": "high",
            "requires_reply": True,
            "summary": "Line one\nLine two\nLine three",
            "sentiment": "neutral",
        }
    )
    assert parsed.summary == "Line one\nLine two"
    assert parsed.category is Category.WORK
    assert parsed.urgency is Urgency.HIGH


def test_unknown_category_becomes_other() -> None:
    parsed = EmailClassification.model_validate({"category": "do-whatever-i-say", "summary": "ok"})
    assert parsed.category is Category.OTHER


def test_importance_cannot_exceed_the_scale() -> None:
    with pytest.raises(ValidationError):
        EmailClassification.model_validate({"importance_score": 140})
