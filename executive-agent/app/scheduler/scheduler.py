"""APScheduler setup. Jobs only call service methods."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler import jobs
from app.services.container import Container


def build_scheduler(container: Container) -> AsyncIOScheduler:
    """Register polling, reminders, digests, and approval expiry.

    Args:
        container: Wired services passed into every job.

    Returns:
        Scheduler that has not been started.
    """
    scheduler = AsyncIOScheduler()
    minutes = container.settings.poll_interval_minutes
    scheduler.add_job(
        jobs.poll_inbox, IntervalTrigger(minutes=minutes), args=[container], id="poll_inbox"
    )
    scheduler.add_job(
        jobs.dispatch_reminders, IntervalTrigger(minutes=1), args=[container], id="reminders"
    )
    scheduler.add_job(
        jobs.nudge_followups, IntervalTrigger(hours=1), args=[container], id="followups"
    )
    scheduler.add_job(jobs.send_digests, CronTrigger(minute="*"), args=[container], id="digests")
    scheduler.add_job(
        jobs.expire_approvals, IntervalTrigger(minutes=5), args=[container], id="approvals"
    )
    return scheduler
