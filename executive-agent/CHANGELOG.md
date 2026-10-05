# Changelog

## Progress

### Phase 1–9: the original agent

Completed and kept in place.

- Configuration, SQLite, Alembic, Telegram skeleton, Google OAuth.
- Incremental Gmail sync, MIME parsing, classification, Telegram alerts.
- Draft, edit, and send through an approval gate, with an audit log.
- Meeting detection, conflict warning, Calendar create after approval.
- Tasks, reminders, morning briefing, evening wrap-up, follow-ups.
- Attachments, thread summaries, categories, optional Gmail labels.
- Natural-language search and an intent router.
- Contacts, VIP, mute, tone, quiet hours, writing-style notes.
- Security tests, demo mode, Docker, and the operations console.

### Live repairs

Completed after the first run against a real inbox.

- The empty briefing came from a history cursor that skipped existing mail, and from a formatter that printed "None" for empty sections. Sync now backfills the last 7 days once, then continues with history. The briefing skips empty sections.
- Model names that returned 404 were removed from code. `GEMINI_MODEL_CHAIN` is tried in order on 429, 503, or 404. Failures include the status code. If the whole chain fails, admins are told once. `/errors` lists recent failures.
- Deadlines are resolved from the email's received time. A two-day-old "deadline today" is overdue, never "hours left".
- Newsletter phrases such as "unsubscribe" are not stored as tasks.

### Multi-user accounts

- Each mailbox is a row in `users`. Owned tables carry `user_id`.
- Google connect uses a web OAuth client, PKCE, and `{PUBLIC_BASE_URL}/oauth/google/callback`.
- `/deleteme` erases that user's rows only after they type DELETE.
- The Telegram menu lists twelve commands. Older commands remain as hidden aliases.
- The log console is off unless `CONSOLE_ENABLED=true`, and then only loopback can open it.

## Still open

Sunday weekly review, neglected-reply nudges at 4 hours, 24 hours, and 48 hours, and meeting scheduling from chat are not in this step. A single follow-up nudge interval already runs.
