"""Buttons for signup, onboarding, and account removal."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.account_service import FlowButton


def markup(
    rows: tuple[tuple[FlowButton, ...], ...] | object,
) -> InlineKeyboardMarkup | None:
    """Turn signup buttons into a Telegram keyboard."""
    if not isinstance(rows, tuple) or not rows:
        return None
    keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        if not isinstance(row, tuple):
            return None
        buttons: list[InlineKeyboardButton] = []
        for button in row:
            if not isinstance(button, FlowButton):
                return None
            if button.url:
                buttons.append(InlineKeyboardButton(button.label, url=button.url))
            elif button.callback:
                buttons.append(InlineKeyboardButton(button.label, callback_data=button.callback))
        if buttons:
            keyboard.append(buttons)
    if not keyboard:
        return None
    return InlineKeyboardMarkup(keyboard)
