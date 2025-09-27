import pytz
import pandas as pd
from datetime import datetime, timedelta, time
from typing import List, Optional, Tuple
from config1 import US_MARKET_HOLIDAYS_2025

KST   = pytz.timezone("Asia/Seoul")
NY_TZ = pytz.timezone("America/New_York")

def now_times() -> Tuple[datetime, datetime, bool]:
    now_ny = datetime.now(NY_TZ)
    now_kst = datetime.now(KST)
    dst_active = now_ny.dst() != timedelta(0)
    return now_ny, now_kst, dst_active

def get_recent_next(ex_list: List[pd.Timestamp], today_kst: datetime.date) -> Tuple[Optional[datetime.date], Optional[datetime.date]]:
    if not ex_list:
        return None, None
    dates = [d.date() for d in ex_list]
    past = [d for d in dates if d < today_kst]
    future = [d for d in dates if d >= today_kst]
    recent = past[-1] if past else None
    nxt = future[0] if future else None
    return recent, nxt

def hold_deadline_kst(ex_date: datetime.date) -> Optional[datetime]:
    if not ex_date:
        return None
    ny_day = ex_date - timedelta(days=1)
    holidays = set(pd.to_datetime(US_MARKET_HOLIDAYS_2025).date)

    # 휴일·주말 보정
    while ny_day in holidays or ny_day.weekday() >= 5:
        ny_day -= timedelta(days=1)

    ny_close = datetime.combine(ny_day, time(16, 0))
    ny_close = NY_TZ.localize(ny_close)
    return ny_close.astimezone(KST)
