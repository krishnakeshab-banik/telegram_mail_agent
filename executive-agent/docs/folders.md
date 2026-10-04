# Folders

Folders are views in the local database. Gmail is not modified unless label application is turned on in `/preferences`, and even then a change waits for approval.

One email can sit in several folders. The first match is the primary folder. Cheap header and phrase rules run before any model call. Prompt field lists live in `app/ai/prompts/folder_classifier.txt`, `reply_variants.txt`, and `opportunity_extractor.txt`.

## Commands

| Command | What it shows |
| --- | --- |
| `/folders` or `/menu` | Button grid of every folder with its active count |
| `/meets` | Meetings and invites. Prev / Next pages of 5 |
| `/deadlines` | Upcoming and "Missed or overdue". A past due date is never described as hours left |
| `/tasks` | Explicit asks only. Newsletter buttons are dropped |
| `/waiting` | Mail that still needs a reply, with reply buttons 1, 2, and 3 |
| `/important` | Higher-importance mail |
| `/jobs` `/hackathons` `/events` `/scholarships` `/opportunities` | Opportunity cards with a fit score. Buttons: Interested, Applied, Not for me |
| `/bills` `/orders` `/travel` `/finance` `/academics` | Money and life views |
| `/otps` | Masked codes such as `•••• 03`. No push alert. Reveal shows the code and that Telegram message is deleted after 60 seconds. Bodies older than 24 hours are cleared |
| `/newsletters` `/filtered` | Digests and mail kept out of the main briefing |
| `/spam` | Suspected phishing, with reasons. These are not summarized as trustworthy |
| `/vip` `/saved` `/archive` | VIP senders, starred items, and overdue or dismissed mail |
| `/errors` | Recent sync and Gemini failures |
| `/suggest` | Three reply drafts, or one expanded instruction such as `reply yes and ask for the invoice`. Nothing is sent |
| `/templates` | Saved replies. `/templates save Name :: body` stores one. `{name}` and `{date}` are filled in when rendered |
| `/interests` | Skills and topics used for match scores |
| `/focus 2h` | Silences ordinary alerts. Critical items and phishing still come through. `/focus off` ends it |

Add a search after a folder command: `/jobs machine learning`.

## Buttons

- Folder pages have Prev and Next.
- An important-mail alert has Short, Detailed, and Decline, plus Yes, Thanks, and Later. Choosing one shows To, subject, and body. Send is a separate tap.
- A draft that says "attached" without a file shows a warning before that tap.
- Reveal on an OTP card posts the code and deletes that message after 60 seconds.

## Custom folders

Say `create folder Research for emails from my professor and arXiv`. The bot repeats the keywords and waits for `yes` before saving. Later matching mail is filed locally. Gmail itself stays unchanged.

## What is still local-only

Topics mode, resume upload, voice notes, a Sunday weekly review, scheduled send, and meeting prep at 24 hours / 1 hour / 10 minutes are not wired yet. Opportunity scores use the interest profile and phrase rules. The same posting is not yet collapsed across mailing lists.
