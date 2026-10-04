"""Cheap header and phrase rules that assign folders before any model call."""

import re
from dataclasses import dataclass, field

_OTP = re.compile(r"\b(otp|one[- ]time|verification code|login code|password reset)\b", re.I)
_CODE = re.compile(r"\b(\d{4,8})\b")
_PHISH = re.compile(
    r"\b(verify your (account|password)|wire transfer|urgent payment|seed phrase|"
    r"confirm your identity|suspended account)\b",
    re.I,
)
_HACK = re.compile(r"\b(hackathon|devpost|prize pool|coding competition)\b", re.I)
_JOB = re.compile(r"\b(internship|job opening|we.?re hiring|role:|stipend)\b", re.I)
_SCHOLAR = re.compile(r"\b(scholarship|fellowship|grant)\b", re.I)
_EVENT = re.compile(r"\b(webinar|workshop|conference)\b", re.I)
_BILL = re.compile(r"\b(invoice|amount due|payment due)\b", re.I)
_ORDER = re.compile(r"\b(order confirmed|shipped|tracking number|refund)\b", re.I)
_TRAVEL = re.compile(r"\b(flight|boarding pass|hotel booking|pnr)\b", re.I)


@dataclass(frozen=True)
class FolderHit:
    """One folder assignment produced by rules."""

    slug: str
    status: str = "new"
    fields: dict[str, str] = field(default_factory=dict)


def looks_like_otp(subject: str, body: str) -> bool:
    """Return whether the message is a one-time code or login alert."""
    return _OTP.search(f"{subject}\n{body}") is not None


def extract_code(text: str) -> str:
    """Return the first 4-8 digit code, or an empty string."""
    match = _CODE.search(text)
    return match.group(1) if match else ""


def mask_code(code: str) -> str:
    """Hide all but the last two digits."""
    if len(code) < 2:
        return "••••"
    return f"•••• {code[-2:]}"


def phishing_reasons(subject: str, body: str) -> list[str]:
    """Return human-readable suspicion reasons. Empty means not phishing."""
    text = f"{subject}\n{body}"
    reasons: list[str] = []
    if _PHISH.search(text):
        reasons.append("urgent credential or payment language")
    if "bit.ly" in text.lower() or "tinyurl.com" in text.lower():
        reasons.append("shortened link")
    return reasons


def classify_message(
    *,
    subject: str,
    body: str,
    sender: str,
    category: str,
    is_bulk: bool,
    requires_reply: bool,
    has_meeting: bool,
    has_deadline: bool,
    is_vip: bool,
    custom_rules: list[tuple[str, list[str]]] | None = None,
    has_task: bool = False,
) -> list[FolderHit]:
    """Assign zero or more folders. The first hit is the primary folder.

    Args:
        subject: Email subject.
        body: Plain body.
        sender: Sender address.
        category: Classifier category.
        is_bulk: Newsletter-style bulk flag.
        requires_reply: Whether a reply is owed.
        has_meeting: Whether a meeting was extracted.
        has_deadline: Whether a deadline was extracted.
        is_vip: Whether the sender is marked VIP.
        custom_rules: Optional (slug, keywords) pairs.
        has_task: Whether a usable task was extracted.

    Returns:
        Folder hits, primary first.
    """
    text = f"{subject}\n{body}\n{sender}"
    hits: list[FolderHit] = []
    reasons = phishing_reasons(subject, body)
    if reasons:
        hits.append(FolderHit("spam", fields={"reasons": "; ".join(reasons)}))
    if looks_like_otp(subject, body):
        hits.append(FolderHit("otps", fields={"code": extract_code(text)}))
    if has_meeting or category == "meetings":
        hits.append(FolderHit("meets"))
    if _HACK.search(text):
        hits.append(FolderHit("hackathons"))
        hits.append(FolderHit("opportunities"))
    if _JOB.search(text):
        hits.append(FolderHit("jobs"))
        hits.append(FolderHit("opportunities"))
    if _SCHOLAR.search(text):
        hits.append(FolderHit("scholarships"))
        hits.append(FolderHit("opportunities"))
    if _EVENT.search(text):
        hits.append(FolderHit("events"))
    if has_deadline or "deadline" in text.lower():
        hits.append(FolderHit("deadlines"))
    if _BILL.search(text):
        hits.append(FolderHit("bills"))
    if _ORDER.search(text):
        hits.append(FolderHit("orders"))
    if _TRAVEL.search(text):
        hits.append(FolderHit("travel"))
    if category == "academics":
        hits.append(FolderHit("academics"))
    if category == "finance":
        hits.append(FolderHit("finance"))
    if is_bulk or category == "newsletters":
        hits.append(FolderHit("newsletters"))
        hits.append(FolderHit("filtered"))
    if has_task:
        hits.append(FolderHit("tasks"))
    if requires_reply:
        hits.append(FolderHit("waiting"))
    if is_vip:
        hits.append(FolderHit("vip"))
    if category in {"work", "personal", "academics", "finance", "meetings"} and not is_bulk:
        hits.append(FolderHit("important"))
    for slug, keywords in custom_rules or []:
        if any(word.lower() in text.lower() for word in keywords if word):
            hits.append(FolderHit(slug))
    return _unique(hits)


def score_fit(text: str, interests: str) -> tuple[int, str]:
    """Score an opportunity against a comma-separated interest list."""
    words = [part.strip().lower() for part in interests.split(",") if part.strip()]
    if not words:
        return 40, "No interest profile yet"
    matched = [word for word in words if word in text.lower()]
    score = min(100, 30 + 25 * len(matched))
    if not matched:
        return 25, "Weak overlap with your interests"
    return score, f"Matches {matched[0]}"


def _unique(hits: list[FolderHit]) -> list[FolderHit]:
    seen: set[str] = set()
    ordered: list[FolderHit] = []
    for hit in hits:
        if hit.slug in seen:
            continue
        seen.add(hit.slug)
        ordered.append(hit)
    return ordered
