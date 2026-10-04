"""Localhost HTTP server for health checks and the operations console."""

import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.utils.activity_log import get_activity_log

_CONSOLE = Path(__file__).with_name("console.html")
_LOOPBACK = {"127.0.0.1", "::1"}


async def serve_console(port: int) -> asyncio.Server:
    """Listen for the health check and the local log console.

    Args:
        port: TCP port.

    Returns:
        Running asyncio server.
    """

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await _read_headers(reader)
            await _dispatch(writer, raw)
        except (asyncio.IncompleteReadError, ConnectionError, TimeoutError):
            writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            return

    return await asyncio.start_server(handle, "0.0.0.0", port)


async def _dispatch(writer: asyncio.StreamWriter, raw: bytes) -> None:
    method, target = _request_line(raw)
    if method != "GET":
        await _send(writer, 405, b"Method not allowed", "text/plain; charset=utf-8")
        return
    path, query = _split_target(target)
    if path == "/health":
        await _send(writer, 200, b'{"status":"ok"}', "application/json")
        return
    if not _is_loopback(writer):
        await _send(writer, 403, b"Open this console from localhost.", "text/plain; charset=utf-8")
        return
    if path == "/api/logs":
        await _send(writer, 200, _logs_body(query), "application/json")
        return
    if path in {"/", "/console"}:
        await _send(writer, 200, _console_body(), "text/html; charset=utf-8")
        return
    await _send(writer, 404, b'{"status":"not_found"}', "application/json")


def _logs_body(query: dict[str, list[str]]) -> bytes:
    level = _first(query, "level")
    text = _first(query, "q")
    limit = _limit(_first(query, "limit"))
    rows = [row.as_dict() for row in get_activity_log().query(level=level, text=text, limit=limit)]
    return json.dumps({"events": rows}).encode("utf-8")


def _console_body() -> bytes:
    if not _CONSOLE.exists():
        return b"Operations console file is missing."
    return _CONSOLE.read_bytes()


def _request_line(raw: bytes) -> tuple[str, str]:
    line = raw.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
    parts = line.split(" ")
    if len(parts) < 2:
        return "", "/"
    return parts[0].upper(), parts[1]


def _split_target(target: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urlsplit(target)
    return parsed.path or "/", parse_qs(parsed.query, keep_blank_values=False)


def _first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    return values[0] if values else ""


def _limit(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return 400
    return max(1, min(parsed, 500))


def _is_loopback(writer: asyncio.StreamWriter) -> bool:
    peer = writer.get_extra_info("peername")
    if not isinstance(peer, tuple) or not peer:
        return False
    return str(peer[0]) in _LOOPBACK


async def _read_headers(reader: asyncio.StreamReader) -> bytes:
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 8192:
        chunk = await asyncio.wait_for(reader.read(1024), timeout=5)
        if not chunk:
            break
        data += chunk
    return data


async def _send(writer: asyncio.StreamWriter, status: int, body: bytes, content_type: str) -> None:
    reason = {200: "OK", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed"}.get(
        status, "Error"
    )
    header = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n\r\n"
    )
    writer.write(header.encode("ascii") + body)
    await writer.drain()
    writer.close()
