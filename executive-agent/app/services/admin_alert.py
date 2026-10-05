"""One-shot notices to admin accounts. The text never includes mail or tokens."""

from app.db.base import session_scope
from app.db.repositories.user_repository import UserRepository
from app.services.container import Container
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def alert_admins(container: Container, text: str) -> None:
    """Send one notice to each admin who has a stored chat id."""
    async with session_scope(container.sessions) as session:
        chats = await UserRepository(session).admin_chat_ids(container.settings.admin_ids)
    if not chats:
        logger.warning("admin_alert_undelivered")
        return
    for chat_id in chats:
        await container.sender.send_text(chat_id, text)
