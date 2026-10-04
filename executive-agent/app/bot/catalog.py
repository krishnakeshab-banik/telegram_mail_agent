"""Telegram profile text and the command menu. One list feeds /help and the bot profile."""

COMMAND_MENU: tuple[tuple[str, str], ...] = (
    ("start", "Open the assistant and how to connect Gmail"),
    ("signup", "Connect Gmail and Calendar in the browser on this computer"),
    ("help", "Show every command and what it does"),
    ("brief", "Morning briefing: top items and a plan for today"),
    ("wrapup", "Evening summary of what is still open"),
    ("important", "Ranked mail that is still relevant"),
    ("unread", "Unread messages in the mailbox"),
    ("tasks", "Explicit asks only, with the source email"),
    ("deadlines", "Upcoming dates and missed or overdue ones"),
    ("followups", "Replies you owe, and replies you are waiting on"),
    ("calendar", "Today's events. Use /calendar week for seven days"),
    ("search", "Find mail in plain language"),
    ("suggest", "Draft reply options. Nothing is sent until you tap Send"),
    ("mail", "Write a new email from an address and a note. Send waits for approval"),
    ("compose", "Same as /mail: structure the note, then send only after approval"),
    ("folders", "Folder grid with an active count on each"),
    ("menu", "Same folder grid as /folders"),
    ("meets", "Meetings and invites, with calendar actions"),
    ("waiting", "Unreplied mail, and mail you sent with no response"),
    ("jobs", "Job and internship postings with a fit score"),
    ("hackathons", "Hackathons and competitions with deadlines"),
    ("events", "Webinars, workshops, conferences, and college events"),
    ("scholarships", "Scholarships, fellowships, and grants"),
    ("opportunities", "Jobs, hackathons, events, and scholarships, ranked"),
    ("interests", "Edit skills and topics used for match scores"),
    ("bills", "Invoices, amounts, and payment due dates"),
    ("orders", "Purchases, tracking, deliveries, and refunds"),
    ("travel", "Flights, trains, hotels, and tickets"),
    ("finance", "Bank, tax, and statement summaries"),
    ("academics", "College, professors, assignments, exams, and results"),
    ("otps", "Masked login codes. No alert. Reveal deletes after 60 seconds"),
    ("newsletters", "Newsletters and digests, one line each"),
    ("spam", "Suspected phishing, with the reasons"),
    ("filtered", "Mail the agent hid, so nothing is lost"),
    ("vip", "Mail from people you marked VIP"),
    ("saved", "Items you starred"),
    ("archive", "Expired and dismissed items"),
    ("templates", "List or save a reusable reply"),
    ("focus", "Silence ordinary alerts. Critical and phishing still arrive"),
    ("preferences", "Timezone, tone, quiet hours, briefing time, and labels"),
    ("categories", "How many messages sit in each category"),
    ("history", "Audit log of actions you approved"),
    ("status", "Mode, Google link, sync, and the last Gemini result"),
    ("errors", "Recent sync and Gemini failures"),
    ("pause", "Stop sync and notifications"),
    ("resume", "Start sync and notifications again"),
    ("done", "Mark a task or deadline done, for example /done t12"),
    ("snooze", "Snooze a task or deadline, for example /snooze d3"),
)

SHORT_DESCRIPTION = (
    "Gmail assistant: folders, deadlines, and reply drafts. Nothing sends until you tap Send."
)

DESCRIPTION = (
    "Gmail assistant. Folders, deadlines, and reply drafts. "
    "Nothing is sent until you approve it.\n\n"
    "/start /signup /help /brief /wrapup /important /unread /waiting /folders /menu "
    "/tasks /deadlines /followups /meets /calendar /search /jobs /hackathons /events "
    "/scholarships /opportunities /interests /bills /orders /travel /finance /academics "
    "/otps /spam /newsletters /filtered /vip /saved /archive /suggest /mail /compose "
    "/templates /focus /preferences /categories /pause /resume /status /errors /history "
    "/done /snooze"
)
