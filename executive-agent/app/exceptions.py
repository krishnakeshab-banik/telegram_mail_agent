"""Application exception hierarchy."""


class ExecutiveAgentError(Exception):
    """Base error for expected agent failures."""


class UnscopedQueryError(ExecutiveAgentError):
    """A user-owned query ran without a user id."""


class ConfigurationError(ExecutiveAgentError):
    """Required configuration is missing or invalid."""


class AuthExpiredError(ExecutiveAgentError):
    """Google OAuth credentials are missing or can no longer be refreshed."""


class ApprovalExpiredError(ExecutiveAgentError):
    """The user confirmed an approval after its expiry time."""


class ApprovalNotFoundError(ExecutiveAgentError):
    """No approval exists for the supplied identifier."""


class ApprovalStateError(ExecutiveAgentError):
    """An approval is not in a state that allows the requested transition."""


class QuotaExceededError(ExecutiveAgentError):
    """An upstream API refused the call because a quota was exhausted."""


class GmailApiError(ExecutiveAgentError):
    """The Gmail API returned an unexpected error."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        """Store the HTTP status when one is available.

        Args:
            message: Redacted error summary.
            status_code: HTTP status code, or 0 when unknown.
        """
        super().__init__(message)
        self.status_code = status_code


class CalendarApiError(ExecutiveAgentError):
    """The Calendar API returned an unexpected error."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        """Store the HTTP status when one is available.

        Args:
            message: Redacted error summary.
            status_code: HTTP status code, or 0 when unknown.
        """
        super().__init__(message)
        self.status_code = status_code


class GeminiError(ExecutiveAgentError):
    """Gemini failed after retries or returned an unusable response."""


class ModelUnavailable(GeminiError):
    """One model returned 404, 429, or 503. The chain may try the next name."""

    def __init__(self, code: object) -> None:
        """Store the upstream status code."""
        super().__init__(f"Gemini model unavailable ({code}).")
        self.code = code


class RateLimitError(ExecutiveAgentError):
    """A local rate limit delayed or blocked an upstream call."""


class AttachmentError(ExecutiveAgentError):
    """An attachment could not be downloaded or parsed safely."""


class NotAllowedError(ExecutiveAgentError):
    """The Telegram user is not on the allowlist."""


class AgentPausedError(ExecutiveAgentError):
    """Processing is stopped by the global kill switch."""


class DemoModeError(ExecutiveAgentError):
    """A live Google mutation was requested while the app is in demo mode."""


class RecordNotFoundError(ExecutiveAgentError):
    """A database row required by the operation does not exist."""
