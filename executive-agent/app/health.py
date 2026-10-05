"""HTTP entry for health checks, the OAuth callback, and the local console."""

from app.web.server import OAuthHandler, serve_console


async def serve_health(
    port: int,
    on_oauth: OAuthHandler | None = None,
    *,
    console: bool = False,
) -> object:
    """Listen for /health and the Google OAuth callback."""
    return await serve_console(port, on_oauth, console=console)


__all__ = ["serve_health"]
