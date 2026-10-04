"""Inline keyboards. Callback payloads are built from constants."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.constants import CallbackPrefix, Category, callback_data


def email_actions(
    email_id: int, *, has_meeting: bool, labels_enabled: bool
) -> InlineKeyboardMarkup:
    """Buttons shown on an important-email alert."""
    rows = [
        [
            _button("Draft Reply", CallbackPrefix.DRAFT, email_id),
            _button("Summarize", CallbackPrefix.SUMMARIZE, email_id),
        ],
        [
            _button("1 Short", CallbackPrefix.REPLY_VARIANT, email_id, 0),
            _button("2 Detailed", CallbackPrefix.REPLY_VARIANT, email_id, 1),
            _button("3 Decline", CallbackPrefix.REPLY_VARIANT, email_id, 2),
        ],
        [
            _button("Yes", CallbackPrefix.QUICK_REPLY, email_id, 0),
            _button("Thanks", CallbackPrefix.QUICK_REPLY, email_id, 1),
            _button("Later", CallbackPrefix.QUICK_REPLY, email_id, 2),
        ],
        [
            _button("Create Task", CallbackPrefix.CREATE_TASK, email_id),
            _button("Mark Done", CallbackPrefix.MARK_DONE, email_id),
        ],
        [
            _button("Mute Sender", CallbackPrefix.MUTE, email_id),
            _button("Not Important", CallbackPrefix.NOT_IMPORTANT, email_id),
        ],
    ]
    if has_meeting:
        rows.insert(1, [_button("Add to Calendar", CallbackPrefix.ADD_CALENDAR, email_id)])
    if labels_enabled:
        rows.append([_button("Apply Label", CallbackPrefix.CATEGORY, email_id, "label")])
    return InlineKeyboardMarkup(rows)


def draft_actions(approval_id: int) -> InlineKeyboardMarkup:
    """Buttons shown on a reply preview."""
    return InlineKeyboardMarkup(
        [
            [
                _button("Send", CallbackPrefix.SEND, approval_id),
                _button("Edit", CallbackPrefix.EDIT, approval_id),
                _button("Cancel", CallbackPrefix.CANCEL, approval_id),
            ],
            [
                _button("Regenerate", CallbackPrefix.REGENERATE, approval_id),
                _button("Shorter", CallbackPrefix.SHORTER, approval_id),
            ],
            [
                _button("More Formal", CallbackPrefix.FORMAL, approval_id),
                _button("More Friendly", CallbackPrefix.FRIENDLY, approval_id),
            ],
        ]
    )


def confirm_actions(approval_id: int) -> InlineKeyboardMarkup:
    """Confirm or cancel a pending approval."""
    return InlineKeyboardMarkup(
        [
            [
                _button("Confirm", CallbackPrefix.SEND, approval_id),
                _button("Cancel", CallbackPrefix.CANCEL, approval_id),
            ]
        ]
    )


def event_actions(approval_id: int, event_id: int) -> InlineKeyboardMarkup:
    """Confirm, ignore, or queue a delete for a meeting."""
    return InlineKeyboardMarkup(
        [
            [
                _button("Add to Calendar", CallbackPrefix.APPROVE_EVENT, approval_id),
                _button("Edit Details", CallbackPrefix.EDIT_EVENT, event_id),
                _button("Ignore", CallbackPrefix.IGNORE, event_id),
            ]
        ]
    )


def reminder_actions(target_type: str, target_id: int) -> InlineKeyboardMarkup:
    """Done and snooze buttons for a reminder."""
    prefix = CallbackPrefix.DONE_TASK if target_type == "task" else CallbackPrefix.MARK_DONE
    return InlineKeyboardMarkup(
        [
            [
                _button("Done", prefix, target_id),
                _button("Snooze 1h", CallbackPrefix.SNOOZE_TASK_1H, target_type, target_id),
                _button(
                    "Snooze tomorrow", CallbackPrefix.SNOOZE_TASK_TOMORROW, target_type, target_id
                ),
            ]
        ]
    )


def followup_actions(followup_id: int) -> InlineKeyboardMarkup:
    """Buttons for a follow-up nudge."""
    return InlineKeyboardMarkup(
        [
            [
                _button("Draft Follow-up", CallbackPrefix.FOLLOWUP_DRAFT, followup_id),
                _button("Dismiss", CallbackPrefix.DISMISS, followup_id),
                _button("Snooze", CallbackPrefix.SNOOZE_1H, followup_id),
            ]
        ]
    )


def preference_actions() -> InlineKeyboardMarkup:
    """Buttons that edit common preferences."""
    return InlineKeyboardMarkup(
        [
            [
                _button("Tone", CallbackPrefix.PREF_TONE),
                _button("Labels", CallbackPrefix.PREF_LABELS),
                _button("Threshold", CallbackPrefix.PREF_THRESHOLD),
            ]
        ]
    )


def category_actions(email_id: int) -> InlineKeyboardMarkup:
    """Buttons that correct an email category."""
    rows = []
    current: list[InlineKeyboardButton] = []
    for category in Category:
        current.append(_button(category.value, CallbackPrefix.CATEGORY, email_id, category.value))
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    return InlineKeyboardMarkup(rows)


def _button(label: str, prefix: CallbackPrefix, *parts: object) -> InlineKeyboardButton:
    data = callback_data(prefix, *parts) if parts else prefix.value
    return InlineKeyboardButton(label, callback_data=data)
