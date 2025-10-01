import pytz
import pandas as pd
from datetime import datetime, timedelta, time
from typing import List, Optional, Tuple
from config1 import US_MARKET_HOLIDAYS_2025, ex_dates_cfg   # ⬅️ ex_dates_cfg 가져오기

KST   = pytz.timezone("Asia/Seoul")
NY_TZ = pytz.timezone("America/New_York")

def now_times() -> Tuple[datetime, datetime, bool]:
    """현재 미국/한국 시각과 DST 여부 반환"""
    now_ny = datetime.now(NY_TZ)
    now_kst = datetime.now(KST)
    dst_active = now_ny.dst() != timedelta(0)
    return now_ny, now_kst, dst_active


def get_recent_next(
    ex_list: List,
    today_kst: datetime.date,
    ann_list: Optional[List] = None
) -> Tuple[Optional[datetime.date], Optional[datetime.date]]:
    """
    ex_list(배당락일 리스트)에서 최근·다음 날짜 구하기
    + 오늘 발표가 있으면 '다음' 대신 '최근'으로 분류
    + next가 None이면 config1 기준 ex_dates_cfg에서 fallback
    """
    if not ex_list:
        return None, None

    dates = []
    for d in ex_list:
        try:
            dt = pd.to_datetime(d)
            dates.append(dt.date())
        except Exception:
            continue

    if not dates:
        return None, None

    past = [d for d in dates if d < today_kst]
    future = [d for d in dates if d >= today_kst]

    recent = past[-1] if past else None
    nxt = future[0] if future else None

    # ⬇️ 오늘 발표된 공시가 있으면 next → recent 로 이동
    if ann_list:
        ann_dates = [pd.to_datetime(a).date() for a in ann_list]
        if today_kst in ann_dates and nxt:
            recent, nxt = nxt, None

    # ⬇️ NEXT가 비었으면 config1 기준으로 fallback
    if nxt is None and ex_dates_cfg:
        future_cfg = [d for d in ex_dates_cfg if d >= today_kst]
        if future_cfg:
            nxt = min(future_cfg)

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
