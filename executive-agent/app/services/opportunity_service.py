"""Fit scores and status moves for jobs, hackathons, events, and scholarships."""

from app.ai.prompt_loader import load_prompt
from app.services.folder_rules import score_fit

ALLOWED_STATUSES = frozenset(
    {
        "new",
        "saved",
        "applied",
        "interview",
        "offer",
        "rejected",
        "dismissed",
        "interested",
        "registered",
        "submitted",
        "done",
    }
)


def field_list(slug: str) -> list[str]:
    """Return the extracted fields declared for one opportunity folder."""
    prefix = f"{slug}:"
    for line in load_prompt("opportunity_extractor").splitlines():
        if line.lower().startswith(prefix):
            return [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
    return []


def normalize_status(status: str) -> str:
    """Return a pipeline status, or an empty string when it is not allowed."""
    cleaned = status.strip().lower()
    return cleaned if cleaned in ALLOWED_STATUSES else ""


def score_opportunity(text: str, interests: str) -> tuple[int, str]:
    """Score one posting against the owner's interests."""
    return score_fit(text, interests)
