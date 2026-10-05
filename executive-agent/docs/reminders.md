# Reminders

Reminders that are already stored fire from the scheduler every minute. This step does not change how they are created.

Each user has quiet hours. Ordinary mail alerts, newsletters, and opportunity digests wait until quiet hours end. Critical alerts and phishing alerts still arrive.

The per-user setting **Reminders override quiet hours** defaults to on. It is stored on the user row and in preferences. `/settings` then Reminders shows it and can turn it off. While it is on, later reminder work can let meeting reminders through quiet hours, and deadline reminders for items due within 6 hours. `/focus` still holds ordinary alerts. Critical items and phishing are not held.

Deadline reminders are planned for 6 hours before the due time. Meeting reminders are planned for 30 minutes before the start. Those lead times are stored. The cards that send them are a later step.
