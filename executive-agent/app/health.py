"""HTTP entry for health checks and the local operations console."""

from app.web.server import serve_console as serve_health

__all__ = ["serve_health"]
