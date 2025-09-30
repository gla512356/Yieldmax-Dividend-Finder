import re
import requests
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import sqlite3, time, json
import numpy as np
from config1 import US_MARKET_HOLIDAYS_2025
from datetime import datetime, date

from config1 import TICKER_TO_GROUP, SCHEDULE
from time_utils1 import now_times, get_recent_next, hold_deadline_kst, KST


# -----------------------------
# Polygon.io 설정
# -----------------------------
POLYGON_API_KEY = "yvaSLKkI93ppNuUxok8ZkrS6dclHPHZU"

def polygon_get(endpoint, params=None):
    url = f"https://api.polygon.io{endpoint}"
    params = params or {}
    params["apiKey"] = POLYGON_API_KEY
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

# -----------------------------
# DB 캐시 (SQLite) — 폴리곤 응답만 디스크 캐시
# -----------------------------
@st.cache_resource
def get_db():
    conn = sqlite3.connect("polygon_cache.db", check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS dividends_cache (
        ticker TEXT PRIMARY KEY,
        data TEXT,
        last_updated REAL
    )""")
    return conn

def tz_to_kst(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    if pd.api.types.is_datetime64_any_dtype(df[col]):
        if df[col].dt.tz is None:
            df[col] = df[col].dt.tz_localize('UTC').dt.tz_convert(KST)
        else:
            df[col] = df[col].dt.tz_convert(KST)
    return df

# -----------------------------
# Yahoo Finance (배당금 기본 소스)
# -----------------------------
@st.cache_data(ttl=7200, show_spinner=False)
def fetch_yf_dividends_df(ticker: str) -> pd.DataFrame:
    try:
        s = yf.Ticker(ticker).dividends  # index=ex-date (UTC-naive), values=USD cash
        if s is None or s.empty:
            return pd.DataFrame(columns=["배당락일", "배당금(달러)"])
        df = s.reset_index()
        df.columns = ["배당락일", "배당금(달러)"]
        df["배당락일"] = pd.to_datetime(df["배당락일"])
        # 야후는 tz 정보 없음 → UTC로 가정 후 KST 변환
        df["배당락일"] = df["배당락일"].dt.tz_localize("UTC").dt.tz_convert(KST)
        df = df.sort_values("배당락일", ascending=False).reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame(columns=["배당락일", "배당금(달러)"])

# -----------------------------
# Polygon (실시간 공시 — 있으면 덮어씀)
# -----------------------------
@st.cache_data(ttl=7200, show_spinner=False)
def fetch_polygon_dividends_df(ticker: str) -> pd.DataFrame:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT data,last_updated FROM dividends_cache WHERE ticker=?", (ticker,))
    row = cur.fetchone()
    now = time.time()

    if row and now - row[1] < 7200:
        try:
            df = pd.read_json(row[0], orient="split")
            return df
        except Exception:
            pass

    rows = []
    try:
        data = polygon_get("/v3/reference/dividends", {"ticker": ticker})
        if "results" in data:
            for item in data["results"]:
                exd = item.get("ex_dividend_date")
                if not exd:
                    continue
                ex_date = pd.to_datetime(exd)
                cash_amount = float(item.get("cash_amount", 0) or 0)
                rows.append((ex_date, cash_amount))
    except Exception:
        pass

    df = pd.DataFrame(rows, columns=["배당락일", "배당금(달러)"])
    if not df.empty:
        df["배당락일"] = pd.to_datetime(df["배당락일"]).dt.tz_localize("UTC").dt.tz_convert(KST)
        df = df.sort_values("배당락일", ascending=False).reset_index(drop=True)

    # 디스크 캐시 업데이트
    try:
        df_json = df.to_json(orient="split")
        conn.execute(
            "REPLACE INTO dividends_cache (ticker,data,last_updated) VALUES (?,?,?)",
            (ticker, df_json, now),
        )
        conn.commit()
    except Exception:
        pass

    return df

# -----------------------------
# 조립: 기본은 Yahoo, Polygon이 있으면 금액/날짜 덮어쓰기
# -----------------------------
def build_hist_dividends_df(ticker: str) -> pd.DataFrame:
    df_yf   = fetch_yf_dividends_df(ticker)      # 기본 금액 소스
    df_poly = fetch_polygon_dividends_df(ticker) # 실시간 덮어쓰기 소스

    # 날짜 기준 outer-merge 후, 금액은 polygon 값이 있으면 polygon으로 덮어씀
    df_all = pd.merge(
        df_yf, df_poly, on="배당락일", how="outer", suffixes=("_yf", "_poly")
    ).sort_values("배당락일", ascending=False)

    if "배당금(달러)_yf" not in df_all.columns:
        df_all["배당금(달러)_yf"] = np.nan
    if "배당금(달러)_poly" not in df_all.columns:
        df_all["배당금(달러)_poly"] = np.nan

    df_all["배당금(달러)"] = df_all["배당금(달러)_yf"]
    mask_poly = df_all["배당금(달러)_poly"].notna() & (df_all["배당금(달러)_poly"] > 0)
    df_all.loc[mask_poly, "배당금(달러)"] = df_all.loc[mask_poly, "배당금(달러)_poly"]

    df_all = df_all[["배당락일", "배당금(달러)"]].reset_index(drop=True)
    return df_all, df_poly  # df_poly는 '다음 배당락일' 오버라이드 판단용

# -----------------------------
# Streamlit 기본 설정
# -----------------------------
components.html("""
<div style="
    background: linear-gradient(135deg, #4cafef, #81c784);
    padding: 24px 16px;
    border-radius: 12px;
    text-align: center;
    color: white;
    box-shadow: 0 3px 8px rgba(0,0,0,0.12);
">
    <h1 style="margin:0; font-size:clamp(1.4em, 5vw, 2.2em);">
        💹 일드맥스 ETF 배당 조회
    </h1>
    <p style="margin:8px 0 0; font-size:clamp(0.9em, 3.5vw, 1.1em); opacity:0.9;">
        배당락일·배당일·배당금 정보를 한눈에 확인하세요
    </p>
</div>
""", height=150)



# -----------------------------
# 유틸
# -----------------------------
def normalize_ticker(raw: str) -> str:
    if raw is None:
        return ""
    return re.sub(r'[^A-Za-z]', '', raw).upper().strip()

def get_group_info(ticker: str):
    info = TICKER_TO_GROUP.get(ticker)
    if info:
        return info
    return None, '그룹 정보 없음', '#f5f5f5'

def adjust_color(hex_color: str, factor: float = 0.9) -> str:
    hex_color = (hex_color or "#e9f1ff").lstrip('#')
    try:
        rgb = [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
    except Exception:
        rgb = [233, 241, 255]
    adjusted = [max(0, min(255, int(c * factor))) for c in rgb]
    return '#{:02x}{:02x}{:02x}'.format(*adjusted)

def get_schedule(group_key: str):
    val = SCHEDULE.get(group_key, [])
    if isinstance(val, dict):
        ex_dates = val.get('ex_dates', [])
        pay_dates = val.get('pay_dates', [])
    else:
        ex_dates = val
        pay_dates = []
    return ex_dates, pay_dates

def fmt(d):
    if d is None or d == 0 or (isinstance(d, float) and pd.isna(d)):
        return '없음'
    try:
        dt = pd.to_datetime(d)
        if pd.isna(dt):
            return '없음'
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return '없음'

def fmt_dt(d):
    if d is None:
        return '정보 없음'
    try:
        dt = pd.to_datetime(d)
        if pd.isna(dt):
            return '정보 없음'
        return dt.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return '정보 없음'

# -----------------------------
# 환율(yfinance) · 당시 주가
# -----------------------------
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_latest_fx() -> float:
    try:
        hist = yf.Ticker("USDKRW=X").history(period="5d")
        if hist.empty:
            return 1350.0
        return float(hist["Close"][-1])
    except Exception:
        return 1350.0

LATEST_FX = fetch_latest_fx()

@st.cache_data(ttl=7200, show_spinner=False)
def get_price_on_date(ticker: str, date_ts: pd.Timestamp) -> float:
    try:
        start = (date_ts - pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        end   = (date_ts + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=False)
        if hist.empty:
            return None
        closes = hist["Close"]
        d_prev = (date_ts - pd.Timedelta(days=1)).date()
        mask_prev = closes.index.date == d_prev
        mask_curr = closes.index.date == date_ts.date()
        if mask_prev.any():
            return float(closes[mask_prev][0])
        if mask_curr.any():
            return float(closes[mask_curr][0])
        return float(closes.iloc[-1])
    except Exception:
        return None

# -----------------------------
# 세션 상태
# -----------------------------
tax_rate = 0.154
if "prev_ticker" not in st.session_state:
    st.session_state.prev_ticker = ""
if "shares" not in st.session_state:
    st.session_state.shares = 1

# -----------------------------
# 입력
# -----------------------------
raw_input = st.text_input("🔍 일드맥스 ETF 티커 입력", value="", placeholder="예: TSLY, NVDY, ULTY")
ticker = normalize_ticker(raw_input)

# 카드 3개는 티커 입력 없을 때만 표시
if not ticker:
    col1, col2, col3 = st.columns(3)

    with col1:
        now_kst = datetime.now(KST)
        components.html(f"""
        <div style="
            background: linear-gradient(135deg, #e3f2fd, #ffffff);
            padding: 16px; border-radius: 12px;
            text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        ">
            <h4 style="margin:0; color:#1e88e5;">📅 오늘 날짜</h4>
            <p style="margin:6px 0 0; font-size:1.1em; font-weight:bold; color:#333;">
                {now_kst.strftime("%Y-%m-%d")}
            </p>
        </div>
        """, height=120)

    with col2:
        hist = yf.Ticker("USDKRW=X").history(period="5d")
        fx_date = hist.index[-1].strftime("%Y-%m-%d") if not hist.empty else "알 수 없음"

        components.html(f"""
        <div style="
            background: linear-gradient(135deg, #e8f5e9, #ffffff);
            padding: 16px; border-radius: 12px;
            text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        ">
            <h4 style="margin:0; color:#43a047;">💱 환율</h4>
            <p style="margin:6px 0 0; font-size:1.1em; font-weight:bold; color:#333;">
                1 USD = {LATEST_FX:,.2f} 원
            </p>
            <p style="margin:4px 0 0; font-size:0.85em; color:#666;">
                기준일: {fx_date} 종가
            </p>
        </div>
        """, height=140)

with col3:
    now_ny, now_kst, dst_active = now_times()

    # 오늘 미국 날짜
    today_ny = now_ny.date()

    # 공휴일 리스트
    holidays = set(pd.to_datetime(US_MARKET_HOLIDAYS_2025).date)

    kst_hour = now_kst.hour + now_kst.minute/60

    if today_ny in holidays or today_ny.weekday() >= 5:  # 공휴일 or 주말
        market_status = "휴장"
    else:
        if dst_active:  # 서머타임 (EDT)
            if 18 <= kst_hour < 22.5:
                market_status = "프리마켓"
            elif 22.5 <= kst_hour or kst_hour < 5:
                market_status = "정규장"
            elif 5 <= kst_hour < 9:
                market_status = "애프터마켓"
            else:
                market_status = "휴장"
        else:  # 비서머타임 (EST)
            if 19 <= kst_hour < 23.5:
                market_status = "프리마켓"
            elif 23.5 <= kst_hour or kst_hour < 6:
                market_status = "정규장"
            elif 6 <= kst_hour < 10:
                market_status = "애프터마켓"
            else:
                market_status = "휴장"

    components.html(f"""
    <div style="background: linear-gradient(135deg, #fff3e0, #ffffff);
                padding: 16px; border-radius: 12px;
                text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">
        <h4 style="margin:0; color:#fb8c00;">🕒 미국 시장</h4>
        <p style="margin:6px 0 0; font-size:1.1em; font-weight:bold; color:#333;">
            {market_status}
        </p>
    </div>
    """, height=120)

if ticker != st.session_state.prev_ticker:
    st.session_state.prev_ticker = ticker
    st.session_state.shares = 1

if ticker:
    now_ny, now_kst, dst_active = now_times()
    st.info(
        f"🕒 현재 미국은 {'써머타임 적용 중' if dst_active else '표준시간'}입니다. "
        f"(🇺🇸 {now_ny.strftime('%Y-%m-%d %H:%M')} / 🇰🇷 {now_kst.strftime('%Y-%m-%d %H:%M')})"
    )
    today_kst = now_kst.date()
else:
    today_kst = pd.Timestamp.now(tz=KST).date()

# -----------------------------
# 메인 로직 — ⚠️ 우선순위: config1 ▶ Yahoo 금액 ▶ Polygon 덮어쓰기
# -----------------------------
if ticker:
    그룹키, 그룹명, 그룹색 = get_group_info(ticker)
    if not 그룹키:
        st.warning("⚠️ 일드맥스 ETF 목록에 없는 티커입니다.")
    else:
        # (1) 배당 이력: 기본(YF) + Polygon 덮어쓰기
        df_div_all, df_poly = build_hist_dividends_df(ticker)

        # (2) 날짜는 config1이 최우선
        ex_dates_cfg, pay_dates_cfg = get_schedule(그룹키)
        recent_ex_cfg, next_ex_cfg = get_recent_next(ex_dates_cfg, today_kst)

        # (3) Polygon에 '미래 공시'가 실제로 있으면 next_ex는 Polygon으로 덮어씌움
        next_ex = next_ex_cfg
        if not df_poly.empty:
            future_poly = df_poly[df_poly["배당락일"].dt.date > today_kst]
            if not future_poly.empty:
                next_ex = future_poly["배당락일"].min()  # tz-aware KST

        # 최근 배당락일은 config1 기준 유지
        recent_ex = recent_ex_cfg

        # 지급일은 config1
        recent_pay, next_pay = get_recent_next(pay_dates_cfg, today_kst)

        # 보유 마감 시각
        until_recent = hold_deadline_kst(recent_ex) if recent_ex else None
        until_next   = hold_deadline_kst(next_ex)   if next_ex   else None

        # 카드 색
        recent_card_color  = adjust_color(그룹색, 0.93)
        next_card_color    = adjust_color(그룹색, 1.05)
        compare_card_color = adjust_color(그룹색, 0.85)

        # (4) 최근 배당금: df_div_all(=YF 기본, Polygon 덮어쓰기)에서 recent_ex 날짜 매칭
        recent_cash_usd = None
        if not df_div_all.empty and recent_ex is not None:
            d_match = pd.to_datetime(df_div_all["배당락일"]).dt.date == pd.to_datetime(recent_ex).date()
            if d_match.any():
                v = df_div_all.loc[d_match, "배당금(달러)"].iloc[0]
                if pd.notna(v) and float(v) > 0:
                    recent_cash_usd = float(v)

        dividend_text = "공시 없음"
        if recent_cash_usd is not None:
            recent_cash_krw = recent_cash_usd * LATEST_FX
            dividend_text = f"{recent_cash_usd:.4f} 달러 ≈ {recent_cash_krw:,.2f} 원(세전)"

        fx_text = f"💱 현재 환율: 1 USD = {LATEST_FX:,.2f} 원 (전일/당일 종가)"

        # 최근 배당 카드 (연녹색)
        components.html(
            f"""
            <div style="
                background: linear-gradient(135deg, #e8f5e9, #ffffff);
                padding: 22px; border-radius: 16px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.12);
                margin-bottom: 16px;">
              <h3 style="color:#43a047; margin-top:0;">
                📌 {ticker} ({그룹명}) — 최근 배당
              </h3>
              <p>🔙 최근 배당락일: <b>{fmt(recent_ex)}</b></p>
              <p style="font-size: 0.9em;">
                📝 최근 배당을 받으려면 <b>{fmt_dt(until_recent)}</b> (한국시간)까지 보유해야 합니다.
              </p>
              <p>💵 최근 배당지급일: <b>{fmt(recent_pay)}</b></p>
              <p>💲 최근 배당금(세전): <b>{dividend_text}</b></p>
            </div>
            <p style="font-size: 0.8em; color:#666; margin-top:-8px; margin-bottom:20px;">
              {fx_text}
            </p>
            """, height=420)

        # 다음 배당 카드 (연파랑)
        components.html(
            f"""
            <div style="
                background: linear-gradient(135deg, #e3f2fd, #ffffff);
                padding: 22px; border-radius: 16px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.12);
                margin-bottom: 16px;">
              <h3 style="color:#1e88e5; margin-top:0;">
                📌 {ticker} ({그룹명}) — 다음 배당
              </h3>
              <p>📅 다음 배당락일: <b>{fmt(next_ex)}</b></p>
              <p style="font-size: 0.9em;">
                💡 다음 배당금을 받으려면 <b>{fmt_dt(until_next)}</b> (한국시간)까지 보유해야 합니다.
              </p>
              <p>💵 다음 배당지급일: <b>{fmt(next_pay)}</b></p>
            </div>
            """, height=360)



        # 직전 vs 최근 (df_div_all에서 과거 2건)
        prev_ex_date = None
        recent_ex_date_hist = None
        prev_div_before = None
        recent_div_before = None
        change_str = "정보 없음"

        if not df_div_all.empty:
            hist_past = df_div_all[df_div_all["배당락일"].dt.date <= today_kst].copy()
            hist_past = hist_past.sort_values("배당락일", ascending=False).reset_index(drop=True)
            if len(hist_past) >= 1:
                recent_ex_date_hist = hist_past.loc[0, "배당락일"]
                v = hist_past.loc[0, "배당금(달러)"]
                recent_div_before = (float(v) * LATEST_FX) if pd.notna(v) else None
            if len(hist_past) >= 2:
                prev_ex_date = hist_past.loc[1, "배당락일"]
                v = hist_past.loc[1, "배당금(달러)"]
                prev_div_before = (float(v) * LATEST_FX) if pd.notna(v) else None

            if (recent_div_before is not None) and (prev_div_before is not None) and prev_div_before > 0:
                delta = (recent_div_before - prev_div_before) / prev_div_before * 100
                arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "▶")
                label = "상승" if delta > 0 else ("하락" if delta < 0 else "변화없음")
                change_str = f"{arrow} {abs(delta):.2f}% {label}"

        components.html(
            f"""
            <div style="
                background: linear-gradient(135deg, #f3e5f5, #ffffff);
                padding: 22px; border-radius: 16px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.12);
                margin-top: 10px;">
              <h3 style="color:#8e24aa; margin-top:0;">
                📊 직전 vs 최근 배당 비교
              </h3>
              <p>📅 직전 배당락일: <b>{fmt(prev_ex_date)}</b></p>
              <p>📅 최근 배당락일: <b>{fmt(recent_ex_date_hist)}</b></p>
              <p>💵 직전 배당금(세전): <b>{(prev_div_before or 0):,.2f}원</b></p>
              <p>💵 최근 배당금(세전): <b>{(recent_div_before or 0):,.2f}원</b></p>
              <p>📈 변화율(세전): <b>{change_str}</b></p>
            </div>
            """, height=360)

        # 보유 주식 수 기준
        st.markdown("### 💰 보유주식 수 기준 최근 배당 수령액")
        shares = st.number_input("보유 주식 수 입력", min_value=1, step=1, key="shares")

        recent_div_krw_before = (recent_div_before or 0.0)
        recent_div_krw_after  = recent_div_krw_before * (1 - tax_rate)

        total_before = recent_div_krw_before * shares
        total_after  = recent_div_krw_after  * shares

        # 카드 4: 보유 주식 수 기준 배당액
        components.html(
            f"""
            <div style="background: linear-gradient(135deg, #fff3e0, #ffffff);
                        padding:22px; border-radius:16px;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.12); margin-top:10px;">
              <h4 style="color:#fb8c00; margin-top:0;">
                💰 보유 주식 수 기준 배당 수령액
              </h4>
              <p>📅 제일 최근 배당지급일: <b>{fmt(recent_pay)}</b></p>
              <p>보유 주식 수: <b>{shares}주</b></p>
              <p>세전 총액: <b>{total_before:,.2f}원</b></p>
              <p>세후 총액(15.4%): <b>{total_after:,.2f}원</b></p>

              <p style="font-size: 0.8em; color:#666; margin-top:12px;">
                💡 세후 금액은 생활비에 활용하거나 다른 ETF로 재투자할 수 있습니다.
              </p>
            </div>
            """, height=350)

        # =============================
        # 목표 배당금 역산 계산기
        # =============================
        st.markdown("### 🎯 목표 배당금 계산기")

        target_amount = st.number_input("목표 배당금 입력 (원화 기준)", min_value=0, step=1000, value=50000)

        # 버튼형 세그먼트 (세전 / 세후)
        mode = st.segmented_control("계산 기준 선택", ["세전", "세후"], default="세후")

        if recent_div_before and recent_div_before > 0:
            # 최근 1주당 배당금 (세전/세후)
            recent_div_per_share_before = recent_div_before
            recent_div_per_share_after  = recent_div_before * (1 - tax_rate)

            # 현재 선택된 모드에 따른 1주당 배당금
            per_share_div = recent_div_per_share_before if mode == "세전" else recent_div_per_share_after

            # 필요한 주식 수
            needed_shares = (target_amount / per_share_div) if per_share_div > 0 else None

            # 종가 데이터 가져오기
            price_date = pd.Timestamp(today_kst)
            price_latest = get_price_on_date(ticker, price_date)
            price_label = price_date.strftime("%Y-%m-%d") if price_date else "알 수 없음"

            if price_latest:
                total_invest = needed_shares * price_latest * LATEST_FX
            else:
                total_invest = None

            # 결과 카드
            components.html(f"""
                <div style="background: linear-gradient(135deg, #e0f7fa, #ffffff);
                            padding:22px; border-radius:16px;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.12); margin-top:10px;">
                  <h4 style="color:#00695c; margin-top:0;">
                    🎯 목표 배당금 달성을 위한 계산
                  </h4>
                  <p>목표 배당금 (<b>{mode}</b>): <b>{target_amount:,.0f}원</b></p>
                  <p>필요한 주식 수: <b>{needed_shares:,.0f}주</b></p>
                  <p>예상 총 투자금액: <b>{(total_invest or 0):,.0f}원</b></p>

                  <hr style="border:0; border-top:1px solid #ddd; margin:10px 0;" />
                  <p>📌 최근 1주당 배당금</p>
                  <ul style="margin:0; padding-left:18px; color:#333;">
                    <li>세전: <b>{recent_div_per_share_before:,.2f} 원</b></li>
                    <li>세후(15.4% 공제): <b>{recent_div_per_share_after:,.2f} 원</b></li>
                  </ul>

                  <p style="font-size:0.9em; color:#444; margin-top:8px;">
                    📅 기준가: {price_label} 종가 {price_latest:,.2f} USD × 환율 {LATEST_FX:,.2f}원
                  </p>
                </div>
            """, height=390)

            # ⚠️ 경고문 (카드 밖, 기본 Streamlit 컴포넌트 → 모바일 대응)
            st.markdown(
                """
                <p style="color:#d32f2f; font-size:0.9em; margin-top:10px;">
                ⚠️ 제일 최근 배당금 기준으로 계산된 값이므로, 다음번 배당은 달라질 수 있습니다.<br>
                ⚠️ 예상 총 투자금액은 전일 종가 기준이므로, 주가/환율 변동에 따라 매일 달라질 수 있습니다.
                </p>
                """,
                unsafe_allow_html=True
            )
        else:
            st.info("최근 배당금 정보가 없어 목표 배당금 계산기를 사용할 수 없습니다.")





        # 최근 배당 내역 표/차트 (df_div_all = YF 기본 + Polygon 덮어쓰기)
        if not df_div_all.empty:
            df5 = df_div_all.head(5).copy()
            prices = []
            for dt_ts in df5["배당락일"]:
                p = get_price_on_date(ticker, dt_ts)
                prices.append(p if p is not None else 0.0)
            df5["당시 주가(달러)"] = prices

            df5["배당금(달러)"] = pd.to_numeric(df5["배당금(달러)"], errors="coerce")
            df5["당시 주가(달러)"] = pd.to_numeric(df5["당시 주가(달러)"], errors="coerce")

            df5["배당금(원화,세전)"] = (df5["배당금(달러)"] * LATEST_FX).round(2)
            df5["배당금(원화,세후)"] = (df5["배당금(원화,세전)"] * (1 - tax_rate)).round(2)
            df5["배당락일(월일)"] = pd.to_datetime(df5["배당락일"]).dt.strftime("%Y-%m-%d")

            df5["주가 대비(%)"] = (
                df5["배당금(달러)"] / df5["당시 주가(달러)"].replace(0, np.nan) * 100
            ).round(3).fillna(0)

            df5.index = range(1, len(df5) + 1)

            st.subheader("📑 최근 5개 배당 내역 (세전/세후 + 그 당시 주가 대비 %)")
            st.dataframe(
                df5[[
                    "배당락일(월일)", "배당금(달러)", "당시 주가(달러)",
                    "배당금(원화,세전)", "배당금(원화,세후)", "주가 대비(%)"
                ]],
                use_container_width=True
            )
            st.caption(f"💱 환율 기준(USD→KRW): {LATEST_FX:.2f}원(전일/당일 종가), 세율 고정 15.4%")

            df10 = df_div_all.head(10).copy()
            # ⬇️ dtype 강제: 문자열/None → 숫자, 날짜도 datetime으로
            df10["배당금(달러)"] = pd.to_numeric(df10["배당금(달러)"], errors="coerce")
            df10["배당락일"] = pd.to_datetime(df10["배당락일"], errors="coerce")

            # 기존 계산 라인 (그대로 사용)
            df10["배당금(원화)"] = (df10["배당금(달러)"].fillna(0) * float(LATEST_FX)).round(2)
            df10["배당락일(라벨)"] = df10["배당락일"].dt.strftime("%m/%d")

            fig_div = px.bar(
                df10.sort_values("배당락일"),
                x="배당락일(라벨)", y="배당금(원화)", color="배당금(원화)",
                color_continuous_scale=px.colors.sequential.Tealgrn,
                title="최근 10개 배당금 (세전 원화 기준)"
            )
            fig_div.update_xaxes(tickangle=-45)
            fig_div.update_yaxes(showgrid=False)
            fig_div.update_layout(
                showlegend=False,
                plot_bgcolor="white",
                bargap=0.3,
                xaxis_title="배당락일 (월/일, 한국시간)",
                yaxis_title="배당금(원화)"
            )
            st.plotly_chart(fig_div, use_container_width=True)
        else:
            st.warning("배당 데이터가 없습니다.")
elif raw_input.strip():
    st.warning("영문 티커만 입력해 주세요. 예: TSLY, NVDY, ULTY")
