# Setup

You need a Telegram bot token, a Google **Web application** OAuth client, a Gemini API key, and a Fernet key. People connect their own Google account from Telegram. The bot does not use a desktop login for that step.

## 1. Telegram bot

1. Open Telegram and talk to [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts.
3. Copy the token into `TELEGRAM_BOT_TOKEN`.
4. Send a message to your new bot once, then visit `https://api.telegram.org/bot<token>/getUpdates` and copy your numeric `id` from `"from"`.
5. Put that id in `TELEGRAM_ALLOWED_USER_IDS` if you want the original owner path. Separate extra ids with commas.

With `SIGNUP_MODE=open` (the default), a new person can still open the bot with `/start`, agree to the privacy note, and connect their own Google account.

## 2. Google Cloud

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the **Gmail API** and the **Google Calendar API**.
3. Configure the OAuth consent screen. Add yourself as a test user while the app is in testing. If the account is not a test user, Google shows **Access blocked**.
4. Create an OAuth client of type **Web application**. A Desktop client cannot accept the HTTPS callback and produces **Error 400: redirect_uri_mismatch**.
5. Under **Authorized redirect URIs**, add this exact value, with no extra slash:

   `https://<your-host>/oauth/google/callback`

6. Copy that client's id and secret into `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
7. Set `PUBLIC_BASE_URL` to `https://<your-host>` with no path. The bot builds the redirect from this value. It does not use `GOOGLE_REDIRECT_URI` for the Connect Google link.

`GOOGLE_REDIRECT_URI=http://localhost:8080/` remains only for the local developer script `scripts/authorize_google.py`. Users do not run that script.

The scopes requested, and why, are listed in [docs/scopes.md](docs/scopes.md).

### Trying this on your own PC

Google cannot redirect to `localhost` from a phone. For a local test, install [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/) and, while the bot is running, start a tunnel to the health port (`HEALTH_PORT`, default `8081`):

```bash
cloudflared tunnel --url http://localhost:8081
```

Copy the printed `https://....trycloudflare.com` hostname into `PUBLIC_BASE_URL`, and add `https://....trycloudflare.com/oauth/google/callback` on the same Web client. Restart the bot so it loads the new origin. That hostname changes every time the tunnel restarts, so update both places together. For real use, put the bot on a stable host such as `https://bot.example.com`.

## 3. Gemini

1. Create a key in [Google AI Studio](https://aistudio.google.com/apikey).
2. Set `GEMINI_API_KEY`.
3. `GEMINI_MODEL_CHAIN` is a comma-separated list. The bot tries each name in order when the API returns 429, 503, or 404, and keeps the last one that answered. Put the names only in `.env`, not in code.

## 4. Environment file

```bash
copy .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the printed value into `FERNET_KEY`. This key encrypts Google refresh tokens. If you lose it, each person connects Google again from Telegram.

Set `TIMEZONE` to your IANA zone, for example `Asia/Kolkata`. Briefing defaults to 08:00 in that zone. Quiet hours default to 22:00–07:00. Critical mail still alerts during quiet hours.

## 5. Install and run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

Then send `/start` from Telegram. Agree to the privacy note, tap **Connect Google**, and finish timezone, quiet hours, and reminder timing. That chat is the one used for scheduled alerts.

On Windows PowerShell, clear inherited `APP_MODE` and `FERNET_KEY` from the shell before starting so the values in `.env` are the ones that load. To open the log console for this run only:

```powershell
Remove-Item Env:APP_MODE -ErrorAction SilentlyContinue
Remove-Item Env:FERNET_KEY -ErrorAction SilentlyContinue
$env:CONSOLE_ENABLED = "true"
.\.venv\Scripts\python.exe -m app.main
```

## 6. Docker

Put the same values in `.env`, including `PUBLIC_BASE_URL`, then:

```bash
docker compose up --build
```

The database and encrypted tokens live in `./data`, which the compose file mounts into the container. People connect Google from Telegram. The container exposes `8081` for `GET /health` and for `/oauth/google/callback`.

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

The log console is off unless `CONSOLE_ENABLED=true`. When it is on, open `http://127.0.0.1:8081/` on this machine. It shows the redacted backend log: sync, Gemini, Telegram handler errors, and scheduler jobs. The page refreshes every few seconds and answers only from localhost. `GET /health` stays available either way and returns no mailbox data.
