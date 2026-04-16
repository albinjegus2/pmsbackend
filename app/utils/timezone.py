from datetime import datetime, date
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')

def now_ist() -> datetime:
    """Current datetime in IST (naive, for DB storage)."""
    return datetime.now(IST).replace(tzinfo=None)

def today_ist() -> date:
    """Current date in IST."""
    return datetime.now(IST).date()
