# config1.py — 2025-10 업데이트 (Group 1 & 2 반영)

import pandas as pd
from typing import Dict, List, Tuple

# -----------------------------
# 그룹 정의
# -----------------------------
GROUP_1 = frozenset([
    'CHPY','FEAT','FIVY','GPTY','LFGY','QDTY','RDTY','SDTY',
    'SLTY','ULTY','YMAG','YMAX'
])

GROUP_2 = frozenset([
    'ABNY','AIYY','AMDY','AMZY','APLY','BABO','BRKC','CONY','CRCO','CRSH',
    'CVNY','DIPS','DISO','DRAY','FBY','FIAT','GDXY','GMEY','GOOY','HIYY',
    'HOOY','JPMO','MARO','MRNY','MSFO','MSTY','NFLY','NVDY','OARK','PLTY',
    'PYPY','RBLY','RDYY','SMCY','SNOY','TSLY','TSMY','WNTR','XOMO','XYZY',
    'YBIT','YQQQ'
])

GROUP_META = {
    'G1': ('Group 1 Weekly Cycle', '#e8f5e9'),
    'G2': ('Group 2 Weekly Cycle', '#e3f2fd'),
}

# -----------------------------
# ETF → 그룹 매핑
# -----------------------------
def build_ticker_map() -> Dict[str, Tuple[str, str, str]]:
    m = {}
    for t in GROUP_1:
        name, color = GROUP_META['G1']
        m[t] = ('G1', name, color)
    for t in GROUP_2:
        name, color = GROUP_META['G2']
        m[t] = ('G2', name, color)
    return m

TICKER_TO_GROUP = build_ticker_map()

# -----------------------------
# 스케줄 정의
# -----------------------------
def generate_weekly(start_decl, start_ex, start_pay, weeks=52):
    """주간 패턴 자동 생성"""
    base_decl = pd.to_datetime(start_decl)
    base_ex   = pd.to_datetime(start_ex)
    base_pay  = pd.to_datetime(start_pay)
    return {
        'dec_dates': [(base_decl + pd.Timedelta(weeks=i)).strftime('%Y-%m-%d') for i in range(weeks)],
        'ex_dates':  [(base_ex   + pd.Timedelta(weeks=i)).strftime('%Y-%m-%d') for i in range(weeks)],
        'pay_dates': [(base_pay  + pd.Timedelta(weeks=i)).strftime('%Y-%m-%d') for i in range(weeks)],
    }

SCHEDULE_RAW: Dict[str, Dict[str, List[str]]] = {
    # Group 1 — Tue/ Wed/ Thu cycle
    'G1': generate_weekly(
        start_decl='2025-10-14',  # Declaration (Tuesday)
        start_ex='2025-10-15',    # Ex/Record (Wednesday)
        start_pay='2025-10-16'    # Payment (Thursday)
    ),

    # Group 2 — Wed/ Thu/ Fri cycle
    'G2': generate_weekly(
        start_decl='2025-10-15',  # Declaration (Wednesday)
        start_ex='2025-10-16',    # Ex/Record (Thursday)
        start_pay='2025-10-17'    # Payment (Friday)
    ),
}

# -----------------------------
# Timestamp 파싱
# -----------------------------
def parse_schedule(raw: Dict[str, Dict[str, List[str]]]) -> Dict[str, Dict[str, List[pd.Timestamp]]]:
    parsed = {}
    for k, v in raw.items():
        ex_list  = [pd.to_datetime(s).normalize() for s in v.get('ex_dates',  [])]
        pay_list = [pd.to_datetime(s).normalize() for s in v.get('pay_dates', [])]
        dec_list = [pd.to_datetime(s).normalize() for s in v.get('dec_dates', [])]
        parsed[k] = {'ex_dates': ex_list, 'pay_dates': pay_list, 'dec_dates': dec_list}
    return parsed

SCHEDULE = parse_schedule(SCHEDULE_RAW)

# -----------------------------
# 2025 미국 증시 휴장일 (예시)
# -----------------------------
US_MARKET_HOLIDAYS_2025 = [
    '2025-01-01','2025-01-20','2025-02-17','2025-04-18',
    '2025-05-26','2025-07-04','2025-09-01','2025-11-27','2025-12-25'
]
