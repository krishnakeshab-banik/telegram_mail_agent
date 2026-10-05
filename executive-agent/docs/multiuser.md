# Multi-user

Each Telegram user is one row in `users` and one Google mailbox. Repositories refuse to run without that user's id. Tokens are encrypted with a key derived for that user.

Signup:

1. `/start` shows the privacy note, Connect Google, and How it works.
2. Agree, then open the one-time link. Google redirects to `{PUBLIC_BASE_URL}/oauth/google/callback`.
3. The same Google address cannot be linked to a second Telegram user.
4. Choose timezone, quiet hours, and reminder offsets.

`/disconnect` revokes Google. `/deleteme` asks you to type DELETE and then deletes only that user's rows.

These pairs are unique per user, not globally: `emails (user_id, gmail_message_id)`, `folders (user_id, slug)`, `preferences (user_id, key)`, `oauth_tokens (user_id, provider)`, `reply_templates (user_id, name)`, `contacts (user_id, email)`. The legacy `members` table is gone.

The database upgrades when the process starts. Head revision is `0006_user_uniques`. A copy at `data/executive_agent.copy.db` was upgraded on 5 October 2026 before the live file: two users could insert the same Gmail message id, and `members` was dropped. A later start applied the same revisions to the live database.
