import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.snapshot_service import prune_old_snapshots, snapshot_all_users

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    """Start the portfolio snapshot scheduler. Idempotent."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler(timezone=_ET)

    # Every 5 min, 9:30 AM - 3:55 PM ET, Mon-Fri
    scheduler.add_job(
        snapshot_all_users,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="*/5",
            timezone=_ET,
        ),
        id="portfolio_snapshot",
        max_instances=1,
        coalesce=True,
    )
    # Also one final snapshot at 4:00 PM ET (market close)
    scheduler.add_job(
        snapshot_all_users,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone=_ET),
        id="portfolio_snapshot_close",
        max_instances=1,
        coalesce=True,
    )
    # Daily 1 AM ET cleanup
    scheduler.add_job(
        prune_old_snapshots,
        CronTrigger(hour=1, minute=0, timezone=_ET),
        id="portfolio_snapshot_prune",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    _scheduler = scheduler
    logger.info("Portfolio snapshot scheduler started")
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Portfolio snapshot scheduler stopped")
