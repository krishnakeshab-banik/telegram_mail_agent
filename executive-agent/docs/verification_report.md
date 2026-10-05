# Verification report

Checked on this machine with Python 3.11, without Google, Gemini, or Telegram credentials.

## What passed

- `python -m pytest`: 21 tests.
- `python -m ruff check app tests scripts`: clean.
- `python -m mypy app`: clean.
- `python -m app.main --check` in demo mode: migration applied, scheduler started, process exited cleanly.

## How features were tested

| Feature | How |
| --- | --- |
| MIME parsing, HTML script removal, bulk headers | `tests/unit/test_parser.py` on the sample fixtures |
| Relative dates and quiet hours | `tests/unit/test_time.py` |
| Classifier schema limits | `tests/unit/test_schemas.py` |
| Token encryption and untrusted wrapping | `tests/unit/test_security.py` |
| Idempotent sync and single notification claim | `tests/integration/test_pipeline.py` |
| Reply is not sent until approval; expired approval cannot send | `tests/integration/test_approval_and_calendar.py` |
| Calendar event appears only after approval | same file, demo calendar file |
| Prompt injection does not create a send approval | `tests/security/test_prompt_injection.py` |
| Plain-English routing and preference edits | `tests/integration/test_query.py` |
| Bot command registration | `tests/integration/test_boot.py` |

Sample messages cover a meeting invite, an invoice with an attachment, a newsletter, a professor deadline, a follow-up, and an injection attempt. `scripts/seed_sample_emails.py` runs that mailbox through the real sync and pipeline in demo mode.

## Folder pass on 2026-10-05

`python -m pytest`: 35 passed. `python -m ruff check app tests`: clean. `python -m mypy app`: clean (126 files).

| Check | Result |
| --- | --- |
| Deadline "today" on a 2-day-old email is overdue, never "hours left" | `tests/unit/test_folder_rules.py` |
| Junk tasks such as "unsubscribe" are rejected | same file |
| A hackathon with a deadline is filed in both hackathons and deadlines | same file |
| OTP mask is `•••• 03`, reveal returns the code for 60 seconds, and the notifier skips it | `tests/integration/test_folders.py` |
| Job score is stored and status can move to applied | same file |
| Custom folder keywords match later mail | same file |
| Focus mode holds an ordinary alert; staging a reply does not send | same file |
| A draft that says "attached" without a file warns, and the three variants do not send | `tests/unit/test_folder_rules.py` |
| Prompt injection still cannot create a send | `tests/security/test_prompt_injection.py` (included in the 35) |

These were not run against the live inbox in this session: a real Reveal deletion in Telegram, a live phishing sample, and a tap on Send. The live process was restarted after the tests. Alembic applied `0003_folders`. Startup check passed for Gemini (after a 429, via the fallback model), Gmail, and Calendar.

## Live follow-up on 2026-10-05

The empty briefing came from two places: the formatter printed the word None for empty sections, and the first live sync followed an existing Gmail history cursor, so older mail was never loaded. Sync now backfills `newer_than:7d` once, then continues incrementally. Gemini `gemini-3.8-flash` works, but the API also returned 503 and 429; those errors are no longer silent, and the client tries `gemini-3.5-flash`, `gemini-flash-latest`, and `gemini-3.1-flash-lite` before giving up. `/signup` opens Google consent on this computer and stores that account.

These acceptance checks were not all run against a live inbox in this session: a real test send, a 24-hour nudge, auto-send of a typed draft, phishing labeling, and contextual research. Prompt-injection tests still pass in the unit suite.

## Not exercised here

- A live Gmail inbox, a live Google Calendar, Gemini, and Telegram. Those need the credentials in `SETUP.md`.
- The keyword classifier runs only when `APP_MODE=demo` and `GEMINI_API_KEY` is empty. Live mode requires Gemini for non-bulk mail and for drafts.
- Gmail Pub/Sub push is not wired. `SyncService.sync_inbox` is the place a push handler would call later.
- Demo sends are written to `data/demo_outbox.jsonl`. They are not delivered to a real recipient.

## Multi-user cleanup on 2026-10-05

`python -m pytest`: 56 passed. `python -m ruff check app tests scripts`: clean. `python -m mypy app`: clean (138 files).

| Check | Result |
| --- | --- |
| Menu is exactly `/start /today /brief /meet /deadlines /tasks /folders /waiting /mail /search /settings /help` | `tests/unit/test_bot_profile.py` |
| Hidden aliases resolve, and merged commands share one handler | same file |
| Two users can store the same Gmail id, folder slug, preference key, provider, template name, and contact email | `tests/integration/test_user_uniques.py` |
| Typing DELETE removes every `user_id` row for that user only. Any other word cancels | same file |
| `members` is not created by the finished migration | same file |
| With the console off, `/` and `/api/logs` are 404. `/health` has no mailbox data | `tests/integration/test_signup_oauth.py` |
| No model name string under `app/` | `tests/unit/test_model_chain.py` |
| A 404 then a success uses the next chain entry. A full failure alerts once | same file |

A copy of the live database, `data/executive_agent.copy.db`, was upgraded from `0003_folders` to `0006_user_uniques`. The six unique keys are `(user_id, natural key)`. `members` is gone. Two users inserted the same `gmail_message_id` on that copy, then the insert was rolled back. The live database upgrades when the process starts. A later start applied `0004` through `0006` to the live file.

Reminders and meeting scheduling were not changed. `/today` and `/meet` only read events that are already on the calendar.

## Safety that is in the code

- The bot ignores Telegram users who are not in `TELEGRAM_ALLOWED_USER_IDS`.
- `/pause` stops sync and notifications until `/resume`.
- OAuth tokens and approval payloads are Fernet-encrypted.
- Logs pass through redaction. Message bodies are not logged.
- Send, calendar changes, and label changes go through `ApprovalService` and then `audit_logs`.
