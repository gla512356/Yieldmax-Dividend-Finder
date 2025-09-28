# main.py — 일드맥스 ETF 배당락일·배당일 조회 (최종: 그 당시 주가 대비 % 추가 + 기존 기능 유지)

import re
import yfinance as yf
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

from config1 import TICKER_TO_GROUP, SCHEDULE
from time_utils1 import now_times, get_recent_next, hold_deadline_kst, KST

# -----------------------------
# Streamlit 설정
# -----------------------------
st.set_page_config(page_title="일드맥스 ETF 배당락일/배당일 조회", page_icon="💹", layout="wide")
st.title("💹 일드맥스 ETF 배당락일/배당일 조회")

# -----------------------------
# 공통 유틸
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

def tz_to_kst(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    if pd.api.types.is_datetime64_any_dtype(df[col]):
        if df[col].dt.tz is None:
            df[col] = df[col].dt.tz_localize('UTC').dt.tz_convert(KST)
        else:
            df[col] = df[col].dt.tz_convert(KST)
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_latest_fx() -> float:
    try:
        d = yf.Ticker("USDKRW=X").history(period="1d")
        return float(d["Close"].iloc[-1])
    except Exception:
        return 1350.0

LATEST_FX = fetch_latest_fx()

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_dividends_df(ticker: str) -> pd.DataFrame:
    """yfinance 배당 시계열(달러)을 한국시간 배당락일로 변환하여 최신순 정렬"""
    try:
        s = yf.Ticker(ticker).dividends
        if s is None or s.empty:
            return pd.DataFrame(columns=["배당락일", "배당금(달러)"])
        df = s.reset_index()
        df.columns = ["배당락일", "배당금(달러)"]
        df["배당금(달러)"] = pd.to_numeric(df["배당금(달러)"], errors="coerce").astype(float)
        df = tz_to_kst(df, "배당락일")
        return df.sort_values("배당락일", ascending=False).reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["배당락일", "배당금(달러)"])

def adjust_color(hex_color: str, factor: float = 0.9) -> str:
    """HEX 색상을 factor만큼 어둡게/<1·밝게>1 조정"""
    hex_color = (hex_color or "#e9f1ff").lstrip('#')
    try:
        rgb = [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
    except Exception:
        rgb = [233, 241, 255]
    adjusted = [max(0, min(255, int(c * factor))) for c in rgb]
    return '#{:02x}{:02x}{:02x}'.format(*adjusted)

def get_schedule(group_key: str):
    """SCHEDULE 값이 dict(ex/pay) 또는 list(구형) 모두 대응"""
    val = SCHEDULE.get(group_key, [])
    if isinstance(val, dict):
        ex_dates = val.get('ex_dates', [])
        pay_dates = val.get('pay_dates', [])
    else:
        ex_dates = val
        pay_dates = []
    return ex_dates, pay_dates

# -----------------------------
# 세션 상태 (보유주식 자동 초기화)
# -----------------------------
tax_rate = 0.15  # 세율 고정 15%
if "prev_ticker" not in st.session_state:
    st.session_state.prev_ticker = ""
if "shares" not in st.session_state:
    st.session_state.shares = 1

# -----------------------------
# 배당락일 전날 당시 주가 가져오기
# -----------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def get_price_on_date(ticker: str, date: pd.Timestamp) -> float:
    """배당락일 전날 또는 당일 종가(달러) 가져오기"""
    try:
        hist = yf.Ticker(ticker).history(start=date - pd.Timedelta(days=2), end=date + pd.Timedelta(days=1))
        if hist.empty:
            return None
        dt_prev = date - pd.Timedelta(days=1)
        if dt_prev in hist.index:
            return hist.loc[dt_prev, "Close"]
        if date in hist.index:
            return hist.loc[date, "Close"]
        return hist["Close"].iloc[-1]
    except Exception:
        return None

# -----------------------------
# UI 입력
# -----------------------------
raw_input = st.text_input("🔍 일드맥스 ETF 티커 입력", value="", placeholder="예: TSLY, NVDY, YMAG")
ticker = normalize_ticker(raw_input)

# 티커 변경 시 보유주식 수 초기화
if ticker != st.session_state.prev_ticker:
    st.session_state.prev_ticker = ticker
    st.session_state.shares = 1

# DST 안내는 티커 입력 시에만
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
# 메인 로직
# -----------------------------
if not ticker:
    st.markdown(
        "<p style='background-color:yellow; color:black; padding:6px; border-radius:6px;'>"
        "⚠️ 일드맥스 ETF 외의 티커는 정보가 제공되지 않습니다."
        "</p>", unsafe_allow_html=True)

if ticker:
    그룹키, 그룹명, 그룹색 = get_group_info(ticker)
    if not 그룹키:
        st.warning("⚠️ 일드맥스 ETF 목록에 없는 티커입니다. 정보가 제공되지 않습니다.")
    else:
        ex_dates, pay_dates = get_schedule(그룹키)
        recent_ex, next_ex = get_recent_next(ex_dates, today_kst)
        recent_pay, next_pay = get_recent_next(pay_dates, today_kst)
        until_recent = hold_deadline_kst(recent_ex) if recent_ex else None
        until_next   = hold_deadline_kst(next_ex) if next_ex else None

        def fmt(d):  return d.strftime('%Y-%m-%d') if d else '없음'
        def fmt_dt(d): return d.strftime('%Y-%m-%d %H:%M') if d else '정보 없음'

        # 스타일 색상
        recent_card_color  = adjust_color(그룹색, 0.93)
        next_card_color    = adjust_color(그룹색, 1.05)
        compare_card_color = adjust_color(그룹색, 0.85)

        df_div_all = fetch_dividends_df(ticker)

        # ========= 1) 최근 배당 카드 =========
        components.html(
            f"""
            <div style="background:{recent_card_color}; padding:18px; border-radius:12px; font-family:sans-serif;">
              <h3 style="margin:0 0 8px 0; color:black;">📌 {ticker} <span style='font-size:16px'>( {그룹명} ) — 최근 배당</span></h3>
              <p style="margin:0; color:black;">🔙 최근 배당락일: <b>{fmt(recent_ex)}</b></p>
              <p style="margin:2px 0 6px 0; font-size:13px; color:#555;">
                📝 최근 배당을 받으려면 <b>{fmt_dt(until_recent)}</b> (한국시간)까지 보유했어야 합니다.
              </p>
              <p style="margin:0; color:black;">💵 최근 배당지급일: <b>{fmt(recent_pay)}</b></p>
              <p style="margin-top:6px; font-size:11px; color:#777;">
                ※ 실제 입금 시점은 증권사·브로커마다 다를 수 있습니다.
              </p>
            </div>
            """,
            height=200
        )

        # ========= 2) 다음 배당 카드 =========
        components.html(
            f"""
            <div style="background:{next_card_color}; padding:18px; border-radius:12px; font-family:sans-serif; margin-top:10px;">
              <h3 style="margin:0 0 8px 0; color:black;">📌 {ticker} <span style='font-size:16px'>( {그룹명} ) — 다음 배당</span></h3>
              <p style="margin:0; color:black;">📅 다음 배당락일: <b>{fmt(next_ex)}</b></p>
              <p style="margin:2px 0 6px 0; font-size:13px; color:#555;">
                💡 다음 배당금을 받으려면 <b>{fmt_dt(until_next)}</b> (한국시간)까지 보유해야 합니다.
              </p>
              <p style="margin:0; color:black;">💵 다음 배당지급일: <b>{fmt(next_pay)}</b></p>
              <p style="margin-top:6px; font-size:11px; color:#777;">
                ※ 실제 입금 시점은 증권사·브로커마다 다를 수 있습니다.
              </p>
            </div>
            """,
            height=200
        )

        # ========= 3) 직전 vs 최근 배당 비교 =========
        prev_ex_date = None
        recent_ex_date = None
        prev_div_before = None
        recent_div_before = None
        change_str = "정보 없음"

        if not df_div_all.empty:
            if len(df_div_all) >= 1:
                recent_ex_date   = df_div_all.loc[0, "배당락일"]
                recent_div_before = df_div_all.loc[0, "배당금(달러)"] * LATEST_FX
            if len(df_div_all) >= 2:
                prev_ex_date     = df_div_all.loc[1, "배당락일"]
                prev_div_before   = df_div_all.loc[1, "배당금(달러)"] * LATEST_FX
            if (recent_div_before is not None) and (prev_div_before is not None) and prev_div_before > 0:
                delta = (recent_div_before - prev_div_before) / prev_div_before * 100
                arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "▶")
                label = "상승" if delta > 0 else ("하락" if delta < 0 else "변화없음")
                change_str = f"{arrow} {abs(delta):.2f}% {label}"

        components.html(
            f"""
            <div style="background:{compare_card_color}; padding:18px; border-radius:12px; font-family:sans-serif; margin-top:10px;">
              <h3 style="margin:0 0 8px 0; color:black;">📊 직전 vs 최근 배당 비교</h3>
              <p style="margin:0; color:black;">📅 직전 배당락일: <b>{fmt(prev_ex_date.date() if isinstance(prev_ex_date, pd.Timestamp) else prev_ex_date)}</b></p>
              <p style="margin:0; color:black;">📅 최근 배당락일: <b>{fmt(recent_ex_date.date() if isinstance(recent_ex_date, pd.Timestamp) else recent_ex_date)}</b></p>
              <p style="margin:0; color:black;">💵 직전 배당금(세전): <b>{(prev_div_before or 0):,.2f}원</b></p>
              <p style="margin:0; color:black;">💵 최근 배당금(세전): <b>{(recent_div_before or 0):,.2f}원</b></p>
              <p style="margin:0; color:black;">📈 변화율(세전): <b>{change_str}</b></p>
              <p style="margin-top:6px; font-size:11px; color:#777;">
                ※ 실제 배당금은 환율·브로커 정책에 따라 다를 수 있습니다.
              </p>
            </div>
            """,
            height=230
        )

        # ========= 4) 보유주식 수 기준 최근 배당 수령액 =========
        st.markdown("### 💰 보유주식 수 기준 최근 배당 수령액")
        shares = st.number_input("보유 주식 수 입력", min_value=1, step=1, key="shares")

        # 최근 배당금(세전/세후) 원화
        recent_div_krw_before = (recent_div_before or 0.0)
        recent_div_krw_after  = recent_div_krw_before * (1 - tax_rate)

        total_before = recent_div_krw_before * shares
        total_after  = recent_div_krw_after  * shares

        components.html(
            f"""
            <div style="background:{next_card_color}; padding:18px; border-radius:12px; font-family:sans-serif; margin-top:10px;">
              <h4 style="margin:0 0 8px 0; color:black;">📅 제일 최근 배당지급일: <b>{fmt(recent_pay)}</b></h4>
              <p style="margin:0; color:black;">보유 주식 수: <b>{shares}주</b></p>
              <p style="margin:0; color:black;">세전 총액: <b>{total_before:,.2f}원</b></p>
              <p style="margin:0; color:black;">세후 총액(15%): <b>{total_after:,.2f}원</b></p>
              <p style="margin-top:6px; font-size:11px; color:#777;">
                ※ 실제 세후금액은 환율·브로커 정책에 따라 다를 수 있습니다.
              </p>
            </div>
            """,
            height=180
        )

        # ========= 5) 최근 배당 내역(표) + 차트 (그 당시 주가 대비 %) =========
        if not df_div_all.empty:
            df5 = df_div_all.head(5).copy()
            # 당시 주가(달러)
            prices = []
            for dt in df5["배당락일"]:
                p = get_price_on_date(ticker, dt)
                prices.append(p)
            df5["당시 주가(달러)"] = prices
            df5["배당금(원화,세전)"] = (df5["배당금(달러)"] * LATEST_FX).round(2)
            df5["배당금(원화,세후)"] = (df5["배당금(원화,세전)"] * (1 - tax_rate)).round(2)
            df5["배당락일(월일)"] = df5["배당락일"].dt.strftime("%Y-%m-%d")

            df5["주가 대비(%)"] = (df5["배당금(달러)"] / df5["당시 주가(달러)"] * 100).round(3)

            df5.index = range(1, len(df5) + 1)

            st.subheader("📑 최근 5개 배당 내역 (세전/세후 + 그 당시 주가 대비 %)")
            st.dataframe(df5[["배당락일(월일)", "배당금(달러)", "당시 주가(달러)", "배당금(원화,세전)", "배당금(원화,세후)", "주가 대비(%)"]],
                         use_container_width=True)
            st.caption(f"💱 환율 기준(USD→KRW): {LATEST_FX:.2f}원, 세율 고정 15%")

            df10 = df_div_all.head(10).copy()
            df10["배당금(원화)"] = (df10["배당금(달러)"] * LATEST_FX).round(2)
            df10["배당락일(라벨)"] = df10["배당락일"].dt.strftime("%m/%d")
            fig_div = px.bar(
                df10.sort_values("배당락일"),
                x="배당락일(라벨)", y="배당금(원화)", color="배당금(원화)",
                color_continuous_scale=px.colors.sequential.Tealgrn,
                title="최근 10개 배당금 (세전 원화 기준)"
            )
            fig_div.update_xaxes(tickangle=-45)
            fig_div.update_yaxes(showgrid=False)
            fig_div.update_layout(showlegend=False, plot_bgcolor='white', bargap=0.3,
                                  xaxis_title="배당락일 (월/일, 한국시간)", yaxis_title="배당금(원화)")
            st.plotly_chart(fig_div, use_container_width=True)
        else:
            st.warning("배당 데이터가 없습니다.")

elif raw_input.strip():
    st.warning("영문 티커만 입력해 주세요. 예: TSLY, NVDY, YMAG")
