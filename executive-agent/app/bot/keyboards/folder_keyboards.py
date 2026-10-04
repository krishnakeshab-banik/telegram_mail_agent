"""Inline keyboards for folder pages, OTP reveal, and opportunity status."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.constants import CallbackPrefix, callback_data
from app.services.folder_service import FolderCard


def folder_menu_keyboard(rows: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    """Button grid of folder name and active count."""
    buttons = [
        _button(f"{title} ({count})", CallbackPrefix.FOLDER_PAGE, slug, 0)
        for slug, title, count in rows
    ]
    return InlineKeyboardMarkup(_rows(buttons, 2))


def folder_page_keyboard(slug: str, page: int, cards: list[FolderCard]) -> InlineKeyboardMarkup:
    """Prev, next, and the actions that belong on this folder's cards."""
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(_button("Prev", CallbackPrefix.FOLDER_PAGE, slug, page - 1))
    buttons.append(_button("Next", CallbackPrefix.FOLDER_PAGE, slug, page + 1))
    rows = [_rows(buttons, 2)[0]]
    for card in cards:
        if slug == "otps":
            rows.append([_button("Reveal", CallbackPrefix.OTP_REVEAL, card.email_id)])
        elif card.opportunity_id:
            rows.append(
                [
                    _button("Interested", CallbackPrefix.OPP_STATUS, card.opportunity_id, "saved"),
                    _button("Applied", CallbackPrefix.OPP_STATUS, card.opportunity_id, "applied"),
                    _button(
                        "Not for me", CallbackPrefix.OPP_STATUS, card.opportunity_id, "dismissed"
                    ),
                ]
            )
        elif slug in {"waiting", "important", "vip"}:
            rows.append(
                [
                    _button("1", CallbackPrefix.REPLY_VARIANT, card.email_id, 0),
                    _button("2", CallbackPrefix.REPLY_VARIANT, card.email_id, 1),
                    _button("3", CallbackPrefix.REPLY_VARIANT, card.email_id, 2),
                ]
            )
    return InlineKeyboardMarkup(rows)


def _rows(buttons: list[InlineKeyboardButton], width: int) -> list[list[InlineKeyboardButton]]:
    packed: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []
    for button in buttons:
        current.append(button)
        if len(current) == width:
            packed.append(current)
            current = []
    if current:
        packed.append(current)
    return packed or [[]]


def _button(label: str, prefix: CallbackPrefix, *parts: object) -> InlineKeyboardButton:
    data = callback_data(prefix, *parts) if parts else prefix.value
    return InlineKeyboardButton(label, callback_data=data)
