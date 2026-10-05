# Google scopes

The consent screen requests only these scopes. The clients never call trash, delete-message, or settings endpoints.

| Scope | Why it is required |
| --- | --- |
| `https://www.googleapis.com/auth/gmail.readonly` | Read messages, threads, history, and attachment metadata for incremental sync. |
| `https://www.googleapis.com/auth/gmail.send` | Send a reply in the original thread after you tap Send. |
| `https://www.googleapis.com/auth/gmail.modify` | Add an `Agent/<category>` label to a message. This is the narrowest scope that can change labels on a message. It is used only after you confirm Apply Label. The client has no trash or delete method. |
| `https://www.googleapis.com/auth/calendar.events` | List events for conflict checks, then create, update, or delete an event after you confirm. |

Tokens are encrypted with a per-user Fernet key before they are written to `oauth_tokens`. Logs pass through redaction and never include message bodies or tokens.

## Web client

People connect from Telegram. The bot sends a one-time HTTPS link. Google redirects to `{PUBLIC_BASE_URL}/oauth/google/callback`.

- Create the OAuth client as a **Web application**, not a desktop client.
- Authorized redirect URI: `https://<your-host>/oauth/google/callback`
- Set `PUBLIC_BASE_URL` to `https://<your-host>` with no path.
- The link uses PKCE (`S256`), `access_type=offline`, and `prompt=consent` so Google returns a refresh token.
- The `state` value is signed, bound to that Telegram user, expires after 10 minutes, and is rejected if it is used again.
- One Telegram user can link one Google account. A second Telegram user cannot link a mailbox that is already connected.
- `scripts/authorize_google.py` remains a local developer fallback. It is not the path users follow.

If Google later rejects a refresh token, sync stops for that user only and they receive a Reconnect Google button.
