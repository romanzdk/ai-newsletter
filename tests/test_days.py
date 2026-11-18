from datetime import UTC, date, datetime

from ai_newsletter.days import day_of, window, yesterday


def hours(day: date) -> float:
    start, end = window(day)
    return (end - start).total_seconds() / 3600


def test_a_day_is_a_prague_calendar_day():
    start, end = window(date(2026, 3, 10))
    assert start == datetime(2026, 3, 9, 23, tzinfo=UTC)  # CET is UTC+1
    assert end == datetime(2026, 3, 10, 23, tzinfo=UTC)


def test_clock_changes_make_days_23_or_25_hours_long():
    assert hours(date(2026, 3, 10)) == 24
    assert hours(date(2026, 3, 29)) == 23  # summer time starts
    assert hours(date(2026, 10, 25)) == 25  # summer time ends


def test_yesterday_follows_prague_not_utc():
    just_after_prague_midnight = datetime(2026, 3, 9, 23, 30, tzinfo=UTC)  # 00:30 on Mar 10 in Prague
    assert yesterday(just_after_prague_midnight) == date(2026, 3, 9)


def test_timestamps_are_placed_by_prague_time_bare_dates_as_they_are():
    assert day_of(datetime(2026, 3, 9, 23, 30, tzinfo=UTC)) == date(2026, 3, 10)
    assert day_of(date(2026, 3, 9)) == date(2026, 3, 9)
