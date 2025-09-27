import pandas as pd
from typing import Dict, List, Tuple

WEEKLY = frozenset(['CHPY','GPTY','LFGY','QDTY','RDTY','SDTY','SLTY','ULTY','YMAG','YMAX','TSMY','XOMO','YBIT'])
GRP_A  = frozenset(['BRKC','CRSH','FEAT','FIVY','GOOY','OARK','RBLY','RDYY','SNOY','TSLY'])
GRP_B  = frozenset(['BABO','DIPS','FBY','GDXY','JPMO','MARO','MRNY','NVDY','PLTY','NFLY','PYPY'])
GRP_C  = frozenset(['ABNY','AMDY','CONY','CVNY','DRAY','FIAT','GMEY','HOOY','MSFO'])
GRP_D  = frozenset(['AIYY','AMZY','APLY','DISO','HIYY','MSTY','SMCY','WNTR','XYZY','YQQQ'])

GROUP_META = {
    '주배당': ('주배당', '#e8f5e9'),
    '월A': ('월배당 A그룹', '#e3f2fd'),
    '월B': ('월배당 B그룹', '#fff3e0'),
    '월C': ('월배당 C그룹', '#fce4ec'),
    '월D': ('월배당 D그룹', '#ede7f6'),
}

def build_ticker_map() -> Dict[str, Tuple[str, str, str]]:
    m: Dict[str, Tuple[str, str, str]] = {}
    for t in WEEKLY:
        name, color = GROUP_META['주배당']
        m[t] = ('주배당', name, color)
    for t in GRP_A:
        name, color = GROUP_META['월A']
        m[t] = ('월A', name, color)
    for t in GRP_B:
        name, color = GROUP_META['월B']
        m[t] = ('월B', name, color)
    for t in GRP_C:
        name, color = GROUP_META['월C']
        m[t] = ('월C', name, color)
    for t in GRP_D:
        name, color = GROUP_META['월D']
        m[t] = ('월D', name, color)
    return m

TICKER_TO_GROUP = build_ticker_map()

SCHEDULE_RAW: Dict[str, List[str]] = {
    '주배당': ['2025-09-25','2025-10-02'],
    '월A': ['2025-09-04','2025-10-02'],
    '월B': ['2025-09-11','2025-10-09'],
    '월C': ['2025-09-18','2025-10-16'],
    '월D': ['2025-09-25','2025-10-23']
}

def parse_schedule(raw: Dict[str, List[str]]) -> Dict[str, List[pd.Timestamp]]:
    parsed: Dict[str, List[pd.Timestamp]] = {}
    for k, arr in raw.items():
        dates: List[pd.Timestamp] = []
        for s in arr:
            try:
                d = pd.to_datetime(s).normalize()
                dates.append(d)
            except Exception:
                pass
        parsed[k] = sorted(set(dates))
    return parsed

SCHEDULE = parse_schedule(SCHEDULE_RAW)

# 2025년 미국 증시 휴장일(예시)
US_MARKET_HOLIDAYS_2025 = [
    '2025-01-01','2025-01-20','2025-02-17','2025-04-18',
    '2025-05-26','2025-07-04','2025-09-01','2025-11-27','2025-12-25'
]
