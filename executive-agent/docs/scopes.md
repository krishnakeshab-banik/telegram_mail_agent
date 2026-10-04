# Google scopes

The consent screen requests only these scopes. The clients never call trash, delete-message, or settings endpoints.

| Scope | Why it is required |
| --- | --- |
| `https://www.googleapis.com/auth/gmail.readonly` | Read messages, threads, history, and attachment metadata for incremental sync. |
| `https://www.googleapis.com/auth/gmail.send` | Send a reply in the original thread after you tap Send. |
| `https://www.googleapis.com/auth/gmail.modify` | Add an `Agent/<category>` label to a message. This is the narrowest scope that can change labels on a message. It is used only after you confirm Apply Label. The client has no trash or delete method. |
| `https://www.googleapis.com/auth/calendar.events` | List events for conflict checks, then create, update, or delete an event after you confirm. |

Tokens are encrypted with Fernet before they are written to `oauth_tokens`. Logs pass through redaction and never include message bodies or tokens.
