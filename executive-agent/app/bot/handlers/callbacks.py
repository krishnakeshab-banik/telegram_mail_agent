"""Inline button dispatch. Mutating buttons call the approval gate."""

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import formatters, keyboards
from app.bot.handlers import commands, folders
from app.bot.middleware import callback_parts, container_from, reply_html, require_user_id
from app.constants import CallbackPrefix
from app.exceptions import ExecutiveAgentError
from app.utils.time import format_local


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatch one callback query.

    Args:
        update: Telegram update containing the callback.
        context: Handler context.
    """
    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()
    prefix, parts = callback_parts(query.data)
    handler = _HANDLERS.get(prefix)
    if handler is None:
        return
    try:
        await handler(update, context, parts)
    except ExecutiveAgentError as exc:
        await reply_html(update, formatters.plain(str(exc)))


async def _draft(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    preview = await container_from(context).replies.create_preview(
        int(parts[0]), require_user_id(update)
    )
    await reply_html(
        update, formatters.draft_preview(preview), keyboards.draft_actions(preview.approval_id)
    )


async def _summarize(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    summary = await container_from(context).threads.summarize(int(parts[0]))
    await reply_html(update, formatters.thread_summary(summary))


async def _add_calendar(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    services = container_from(context)
    event = await services.calendar.for_email(int(parts[0]))
    if event is None:
        await reply_html(update, formatters.plain("No meeting was detected in that email."))
        return
    leads = (await services.preferences.get()).reminder_leads
    approval_id, warning = await services.calendar.request_create(
        event.id, require_user_id(update), leads
    )
    prefs = await services.preferences.get()
    when = format_local(event.start_at, prefs.timezone) if event.start_at else "time not resolved"
    text = formatters.event_confirmation(event.title, when, warning)
    await reply_html(update, text, keyboards.event_actions(approval_id, event.id))


async def _create_task(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    services = container_from(context)
    email_id = int(parts[0])
    title = await services.inbox.subject_of(email_id)
    task_id = await services.tasks.add(
        title=title, due_at=None, email_id=email_id, source="telegram"
    )
    await reply_html(update, formatters.plain(f"Task t{task_id} created."))


async def _mark_done(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    services = container_from(context)
    email_id = int(parts[0])
    await services.tasks.complete_for_email(email_id)
    await services.followups.complete_for_email(email_id)
    await reply_html(update, formatters.plain("Marked handled."))


async def _mute(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    services = container_from(context)
    sender = await services.inbox.sender_of(int(parts[0]))
    text = await services.contacts.set_muted(sender, True)
    await reply_html(update, formatters.plain(text))


async def _not_important(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    services = container_from(context)
    sender = await services.inbox.sender_of(int(parts[0]))
    await services.contacts.note_not_important(sender)
    await services.notifier.skip(int(parts[0]))
    await reply_html(update, formatters.plain("I'll treat that sender as less important."))


async def _send(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    result = await container_from(context).approvals.approve(
        int(parts[0]), telegram_user_id=require_user_id(update)
    )
    await reply_html(update, formatters.plain(result))


async def _edit(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    await container_from(context).replies.begin_edit(int(parts[0]), require_user_id(update))
    await reply_html(update, formatters.plain("Send the corrected reply as your next message."))


async def _revise(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    parts: list[str],
    instruction: str,
    tone: str,
) -> None:
    preview = await container_from(context).replies.revise(
        int(parts[0]), tone=tone, instruction=instruction
    )
    await reply_html(
        update, formatters.draft_preview(preview), keyboards.draft_actions(preview.approval_id)
    )


async def _regenerate(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    await _revise(update, context, parts, "", "")


async def _shorter(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    await _revise(update, context, parts, "shorter", "")


async def _formal(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    await _revise(update, context, parts, "", "formal")


async def _friendly(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    await _revise(update, context, parts, "", "friendly")


async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    await container_from(context).approvals.reject(
        int(parts[0]), telegram_user_id=require_user_id(update)
    )
    await reply_html(update, formatters.plain("Cancelled. Nothing was sent."))


async def _edit_event(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    await container_from(context).calendar.begin_edit(int(parts[0]), require_user_id(update))
    await reply_html(
        update, formatters.plain("Send the corrected time, for example next Tuesday 4pm.")
    )


async def _ignore(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    await container_from(context).calendar.ignore(int(parts[0]))
    await reply_html(update, formatters.plain("Ignored the meeting proposal."))


async def _approve_event(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    result = await container_from(context).approvals.approve(
        int(parts[0]), telegram_user_id=require_user_id(update)
    )
    await reply_html(update, formatters.plain(result))


async def _followup_draft(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    services = container_from(context)
    followups = await services.followups.list_open()
    match = next((item for item in followups if item.id == int(parts[0])), None)
    if match is None or match.email_id is None:
        await reply_html(update, formatters.plain("That follow-up is no longer open."))
        return
    preview = await services.replies.create_preview(
        match.email_id, require_user_id(update), instruction="follow up"
    )
    await reply_html(
        update, formatters.draft_preview(preview), keyboards.draft_actions(preview.approval_id)
    )


async def _dismiss(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    await container_from(context).followups.dismiss(int(parts[0]))
    await reply_html(update, formatters.plain("Dismissed."))


async def _snooze_followup(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    await container_from(context).followups.snooze_hours(int(parts[0]), 1)
    await reply_html(update, formatters.plain("Snoozed for one hour."))


async def _done_task(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    title = await container_from(context).tasks.mark_done(int(parts[0]))
    await container_from(context).reminders.cancel("task", int(parts[0]))
    await reply_html(update, formatters.plain(f"Completed: {title}"))


async def _snooze_target(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str], *, tomorrow: bool
) -> None:
    services = container_from(context)
    target_type, raw_id = parts[0], int(parts[1])
    prefs = await services.preferences.get()
    if target_type == "task" and tomorrow:
        title = await services.tasks.snooze_until_tomorrow(raw_id, prefs.timezone)
    elif target_type == "task":
        title = await services.tasks.snooze_hours(raw_id, 1)
    else:
        title = target_type
        await services.reminders.cancel(target_type, raw_id)
    await reply_html(update, formatters.plain(f"Snoozed: {title}"))


async def _category(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    services = container_from(context)
    email_id = int(parts[0])
    choice = parts[1] if len(parts) > 1 else ""
    if choice == "label":
        approval_id = await services.labels.request(email_id, require_user_id(update))
        await reply_html(
            update,
            formatters.plain("Apply this Gmail label?"),
            keyboards.confirm_actions(approval_id),
        )
        return
    if not choice:
        await reply_html(
            update, formatters.plain("Choose a category."), keyboards.category_actions(email_id)
        )
        return
    await services.pipeline.correct_category(email_id, choice)
    await reply_html(update, formatters.plain(f"Category set to {choice}."))


async def _tone(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    del parts
    current = (await container_from(context).preferences.get()).tone
    nxt = {"direct": "formal", "formal": "friendly", "friendly": "direct"}.get(current, "direct")
    await container_from(context).preferences.set_tone(nxt)
    await reply_html(update, formatters.plain(f"Tone set to {nxt}."))


async def _labels(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    del parts
    enabled = await container_from(context).preferences.toggle_labels()
    state = "on" if enabled else "off"
    await reply_html(update, formatters.plain(f"Gmail labels are {state}."))


async def _threshold(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    del parts
    value = await container_from(context).preferences.cycle_threshold()
    await reply_html(update, formatters.plain(f"Notify threshold is {value}."))


async def _signup_agree(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    del parts
    user = update.effective_user
    chat = update.effective_chat
    if user is None:
        return
    reply = await container_from(context).accounts.agree(
        user.id, user.username or "", chat.id if chat else None
    )
    await commands.send_flow(update, reply)


async def _signup_privacy(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    del parts
    await commands.send_flow(update, await container_from(context).accounts.privacy_text())


async def _signup_google(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    del parts
    user = update.effective_user
    chat = update.effective_chat
    if user is None:
        return
    reply = await container_from(context).accounts.connect_link(user.id, chat.id if chat else None)
    await commands.send_flow(update, reply)


async def _signup_choice(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    query = update.callback_query
    prefix = ""
    if query is not None and query.data:
        prefix = query.data.split(":", 1)[0]
    kind = {"tz": "timezone", "qh": "quiet", "rm": "reminders"}.get(prefix, "")
    if not kind or not parts:
        return
    reply = await container_from(context).accounts.choose(require_user_id(update), kind, parts[0])
    await commands.send_flow(update, reply)


async def _signup_disconnect(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    accounts = container_from(context).accounts
    if not parts or parts[0] == "ask":
        reply = await accounts.disconnect_prompt()
    else:
        reply = await accounts.disconnect(require_user_id(update), parts[0])
    await commands.send_flow(update, reply)


async def _signup_delete(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]
) -> None:
    if parts and parts[0] == "no":
        await container_from(context).preferences.set_extra("awaiting_delete", "")
        await reply_html(update, formatters.plain("Account delete cancelled."))
        return
    reply = await container_from(context).accounts.delete_prompt()
    await commands.send_flow(update, reply)


async def _how(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    del parts
    reply = await container_from(context).accounts.how_it_works()
    await commands.send_flow(update, reply)


async def _nav(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    if not parts:
        return
    action = parts[0]
    if action == "today":
        await commands.today(update, context)
    elif action == "important":
        await commands.important(update, context)
    elif action == "folders":
        from app.bot.handlers import folders

        await folders.menu(update, context)
    elif action == "meet":
        await commands.meet(update, context)
    elif action == "settings":
        await commands.settings(update, context)
    elif action == "help":
        await commands.help_command(update, context)


async def _settings(update: Update, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    if not parts:
        return
    await commands.settings_action(update, context, parts[0])


_HANDLERS = {
    CallbackPrefix.DRAFT.value: _draft,
    CallbackPrefix.SUMMARIZE.value: _summarize,
    CallbackPrefix.ADD_CALENDAR.value: _add_calendar,
    CallbackPrefix.CREATE_TASK.value: _create_task,
    CallbackPrefix.MARK_DONE.value: _mark_done,
    CallbackPrefix.MUTE.value: _mute,
    CallbackPrefix.NOT_IMPORTANT.value: _not_important,
    CallbackPrefix.SEND.value: _send,
    CallbackPrefix.EDIT.value: _edit,
    CallbackPrefix.REGENERATE.value: _regenerate,
    CallbackPrefix.SHORTER.value: _shorter,
    CallbackPrefix.FORMAL.value: _formal,
    CallbackPrefix.FRIENDLY.value: _friendly,
    CallbackPrefix.CANCEL.value: _cancel,
    CallbackPrefix.EDIT_EVENT.value: _edit_event,
    CallbackPrefix.IGNORE.value: _ignore,
    CallbackPrefix.APPROVE_EVENT.value: _approve_event,
    CallbackPrefix.FOLLOWUP_DRAFT.value: _followup_draft,
    CallbackPrefix.DISMISS.value: _dismiss,
    CallbackPrefix.SNOOZE_1H.value: _snooze_followup,
    CallbackPrefix.DONE_TASK.value: _done_task,
    CallbackPrefix.SNOOZE_TASK_1H.value: lambda update, context, parts: _snooze_target(
        update, context, parts, tomorrow=False
    ),
    CallbackPrefix.SNOOZE_TASK_TOMORROW.value: lambda update, context, parts: _snooze_target(
        update, context, parts, tomorrow=True
    ),
    CallbackPrefix.CATEGORY.value: _category,
    CallbackPrefix.PREF_TONE.value: _tone,
    CallbackPrefix.PREF_LABELS.value: _labels,
    CallbackPrefix.PREF_THRESHOLD.value: _threshold,
    CallbackPrefix.FOLDER_PAGE.value: folders.on_page,
    CallbackPrefix.OPP_STATUS.value: folders.on_status,
    CallbackPrefix.OTP_REVEAL.value: folders.on_reveal,
    CallbackPrefix.REPLY_VARIANT.value: folders.on_variant,
    CallbackPrefix.QUICK_REPLY.value: folders.on_quick,
    CallbackPrefix.SIGNUP_AGREE.value: _signup_agree,
    CallbackPrefix.SIGNUP_PRIVACY.value: _signup_privacy,
    CallbackPrefix.SIGNUP_GOOGLE.value: _signup_google,
    CallbackPrefix.SIGNUP_TIMEZONE.value: _signup_choice,
    CallbackPrefix.SIGNUP_QUIET.value: _signup_choice,
    CallbackPrefix.SIGNUP_REMINDERS.value: _signup_choice,
    CallbackPrefix.SIGNUP_DISCONNECT.value: _signup_disconnect,
    CallbackPrefix.SIGNUP_DELETE.value: _signup_delete,
    CallbackPrefix.HOW.value: _how,
    CallbackPrefix.NAV.value: _nav,
    CallbackPrefix.SETTINGS.value: _settings,
}
