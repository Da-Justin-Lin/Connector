from datetime import datetime, time
import pandas_market_calendars as mcal
import pytz

_NYSE = mcal.get_calendar("NYSE")
_ET = pytz.timezone("America/New_York")

_MARKET_OPEN = time(9, 30)
_MARKET_CLOSE = time(16, 0)


def is_market_open() -> bool:
    now_et = datetime.now(_ET)
    today = now_et.date()

    schedule = _NYSE.schedule(start_date=str(today), end_date=str(today))
    if schedule.empty:
        return False  # holiday or weekend

    current_time = now_et.time().replace(second=0, microsecond=0)
    return _MARKET_OPEN <= current_time <= _MARKET_CLOSE


def seconds_until_market_open() -> int:
    """Return seconds until next market open, or 0 if already open."""
    now_et = datetime.now(_ET)
    today = now_et.date()

    # Look ahead up to 7 days for next trading day
    from datetime import timedelta
    for delta in range(7):
        check_date = today + timedelta(days=delta)
        schedule = _NYSE.schedule(
            start_date=str(check_date), end_date=str(check_date)
        )
        if schedule.empty:
            continue

        open_dt = schedule.iloc[0]["market_open"].to_pydatetime()
        if open_dt.tzinfo is None:
            open_dt = pytz.utc.localize(open_dt)
        open_dt_et = open_dt.astimezone(_ET)

        if open_dt_et > now_et:
            return int((open_dt_et - now_et).total_seconds())

    return 0
