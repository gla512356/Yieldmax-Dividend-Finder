import pytz
import pandas as pd
from datetime import datetime, timedelta, time
from typing import List, Optional, Tuple
from config1 import US_MARKET_HOLIDAYS_2025

KST   = pytz.timezone("Asia/Seoul")
NY_TZ = pytz.timezone("America/New_York")

def now_times() -> Tuple[datetime, datetime, bool]:
    """현재 미국/한국 시각과 DST 여부 반환"""
    now_ny = datetime.now(NY_TZ)
    now_kst = datetime.now(KST)
    dst_active = now_ny.dst() != timedelta(0)
    return now_ny, now_kst, dst_active

def get_recent_next(ex_list: List, today_kst: datetime.date) -> Tuple[Optional[datetime.date], Optional[datetime.date]]:
    """
    ex_list(배당락일 리스트)에서 최근·다음 날짜 구하기 — 안전 변환 버전
    pandas.Timestamp, datetime, numpy.datetime64, int, str 모두 처리
    """
    if not ex_list:
        return None, None

    dates = []
    for d in ex_list:
        try:
            dt = pd.to_datetime(d)
            # Timestamp나 datetime이면 .date() 추출
            dates.append(dt.date())
        except Exception:
            # 변환 실패 시 건너뜀
            continue

    if not dates:
        return None, None

    past   = [d for d in dates if d <= today_kst]   # 👈 today 포함
    future = [d for d in dates if d > today_kst]

    recent = past[-1] if past else None
    nxt = future[0] if future else None
    return recent, nxt

def hold_deadline_kst(ex_date: datetime.date) -> Optional[datetime]:
    """배당락일 ex_date에 대해 한국시간 보유마감(전일 미국장 16:00) 계산"""
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
