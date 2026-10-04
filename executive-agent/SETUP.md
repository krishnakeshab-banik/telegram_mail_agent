# Setup

You need a Telegram bot token, a Google OAuth client, a Gemini API key, and a Fernet key. The bot will not answer anyone whose numeric Telegram user id is not listed in `TELEGRAM_ALLOWED_USER_IDS`.

## 1. Telegram bot

1. Open Telegram and talk to [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts.
3. Copy the token into `TELEGRAM_BOT_TOKEN`.
4. Send a message to your new bot once, then visit `https://api.telegram.org/bot<token>/getUpdates` and copy your numeric `id` from `"from"`.
5. Put that id in `TELEGRAM_ALLOWED_USER_IDS`. Separate extra ids with commas.

## 2. Google Cloud

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the **Gmail API** and the **Google Calendar API**.
3. Configure the OAuth consent screen. External is fine for a personal bot. Add yourself as a test user while the app is in testing.
4. Create an OAuth client of type **Desktop app**.
5. Copy the client id and secret into `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
6. Leave `GOOGLE_REDIRECT_URI` as `http://localhost:8080/`.

The scopes requested, and why, are listed in [docs/scopes.md](docs/scopes.md).

## 3. Gemini

1. Create a key in [Google AI Studio](https://aistudio.google.com/apikey).
2. Set `GEMINI_API_KEY`.
3. `GEMINI_MODEL_FAST` classifies mail. `GEMINI_MODEL_SMART` drafts replies and answers questions. The defaults are `gemini-3.8-flash` for both. Older names such as `gemini-2.5-flash` are rejected for new API keys.

## 4. Environment file

```bash
copy .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the printed value into `FERNET_KEY`. This key encrypts the Google refresh token. If you lose it, run the Google authorization again.

Set `TIMEZONE` to your IANA zone, for example `Asia/Kolkata`. Briefing defaults to 08:00 in that zone. Quiet hours default to 22:00–07:00. Critical mail still alerts during quiet hours.

## 5. Install and authorize

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/authorize_google.py
python -m app.main
```

`authorize_google.py` opens a browser on port 8080. Approve the requested scopes. If Google does not return a refresh token, remove the app's access at [Google Account permissions](https://myaccount.google.com/permissions) and run the script again.

Then send `/start` to the bot from the allowlisted account. That stores the chat used for scheduled alerts.

## 6. Docker

Put the same values in `.env`, then:

```bash
docker compose up --build
```

The database and encrypted tokens live in `./data`, which the compose file mounts into the container. Authorize Google on the host first (`python scripts/authorize_google.py`) so `data/executive_agent.db` already contains the token, or run the script inside the container with port 8080 published.

The container exposes `8081` for `GET /health`.

## 7. Demo without your inbox

```bash
# .env
APP_MODE=demo
```

```bash
python scripts/build_fixtures.py
python scripts/seed_sample_emails.py
python -m app.main
```

Demo mode reads `tests/fixtures` and records "sent" mail in `data/demo_outbox.jsonl` and events in `data/demo_calendar.json`. With no Gemini key, classification uses a small keyword fallback so the sample mailbox still flows through notifications, tasks, and approvals. Draft quality needs a real `GEMINI_API_KEY`.

## 8. Check the install

```bash
python -m pytest
python -m ruff check app tests scripts
python -m mypy app
python -m app.main --check
```

`--check` migrates the database, builds the bot and scheduler, and exits. It does not connect to Telegram.

## 9. Operations console

While the bot is running, open `http://127.0.0.1:8081/` on this machine. It shows the redacted backend log: sync, Gemini, Telegram handler errors, and scheduler jobs. The page refreshes every few seconds. It answers only from localhost. `GET /health` stays available for the Docker health check.
