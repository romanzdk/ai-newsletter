"""The target day is a calendar day in Prague, not "the last 24 hours".

So a day can be 23 or 25 hours long when the clocks change.
"""

from datetime import UTC, date, datetime, time, timedelta

from ai_newsletter.config import TIMEZONE


def yesterday(now: datetime | None = None) -> date:
    now = now or datetime.now(UTC)
    return now.astimezone(TIMEZONE).date() - timedelta(days=1)


def window(day: date) -> tuple[datetime, datetime]:
    """Start (inclusive) and end (exclusive) of the Prague day, in UTC."""
    start = datetime.combine(day, time(), TIMEZONE)
    end = datetime.combine(day + timedelta(days=1), time(), TIMEZONE)
    return start.astimezone(UTC), end.astimezone(UTC)


def day_of(published: date | datetime) -> date:
    """A full timestamp is converted to Prague time. A bare date (sources that publish only
    the day) is taken as it is, because we don't know its time zone."""
    if isinstance(published, datetime):
        return published.astimezone(TIMEZONE).date()
    return published
