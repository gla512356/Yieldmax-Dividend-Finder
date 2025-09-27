# main.py — 일드맥스 ETF 배당락일·배당일 조회 (그룹별 파스텔톤 + 자동 카드색)

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

# -----------------------------
# 색상 조정 유틸 (HEX → 어둡게/밝게)
# -----------------------------
def adjust_color(hex_color: str, factor: float = 0.9) -> str:
    """HEX 색상을 factor만큼 어둡게/밝게 조정"""
    hex_color = hex_color.lstrip('#')
    rgb = [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
    adjusted = [max(0, min(255, int(c * factor))) for c in rgb]
    return '#{:02x}{:02x}{:02x}'.format(*adjusted)

# -----------------------------
# UI 입력
# -----------------------------
raw_input = st.text_input("🔍 일드맥스 ETF 티커 입력", value="", placeholder="예: TSLY, NVDY, YMAG")
ticker = normalize_ticker(raw_input)

# 써머타임 안내: 티커 입력 시에만 표시
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
        # -----------------------------
        # 그룹 스케줄 계산
        # -----------------------------
        ex_dates = SCHEDULE.get(그룹키, {}).get('ex_dates', [])
        pay_dates = SCHEDULE.get(그룹키, {}).get('pay_dates', [])
        recent_ex, next_ex = get_recent_next(ex_dates, today_kst)
        recent_pay, next_pay = get_recent_next(pay_dates, today_kst)
        until_recent = hold_deadline_kst(recent_ex) if recent_ex else None
        until_next   = hold_deadline_kst(next_ex) if next_ex else None

        def fmt(d):  return d.strftime('%Y-%m-%d') if d else '없음'
        def fmt_dt(d): return d.strftime('%Y-%m-%d %H:%M') if d else '정보 없음'

        # -----------------------------
        # 그룹색 → 최근/다음 카드색 자동 변환
        # -----------------------------
        recent_card_color = adjust_color(그룹색, 0.93)  # 어둡게
        next_card_color   = adjust_color(그룹색, 1.05)  # 밝게

        # -----------------------------
        # 카드 1️⃣ : 최근 배당
        # -----------------------------
        components.html(
            f"""
            <div style="background:{recent_card_color}; padding:18px; border-radius:12px; font-family:sans-serif;">
              <h3 style="margin:0 0 8px 0; color:black;">📌 {ticker} <span style='font-size:16px'>( {그룹명} ) — 최근 배당</span></h3>
              <p style="margin:0; color:black;">🔙 최근 배당락일: <b>{fmt(recent_ex)}</b></p>
              <p style="margin:2px 0 6px 0; font-size:13px; color:#555;">📝 최근 배당을 받으려면 <b>{fmt_dt(until_recent)}</b> (한국시간)까지 보유했어야 합니다.</p>
              <p style="margin:0; color:black;">💵 최근 배당지급일: <b>{fmt(recent_pay)}</b></p>
              <p style="margin-top:6px; font-size:11px; color:#777;">
                ※ 실제 입금 시점은 증권사·브로커마다 다를 수 있습니다.
              </p>
            </div>
            """,
            height=200
        )

        # -----------------------------
        # 카드 2️⃣ : 다음 배당
        # -----------------------------
        components.html(
            f"""
            <div style="background:{next_card_color}; padding:18px; border-radius:12px; font-family:sans-serif; margin-top:10px;">
              <h3 style="margin:0 0 8px 0; color:black;">📌 {ticker} <span style='font-size:16px'>( {그룹명} ) — 다음 배당</span></h3>
              <p style="margin:0; color:black;">📅 다음 배당락일: <b>{fmt(next_ex)}</b></p>
              <p style="margin:2px 0 6px 0; font-size:13px; color:#555;">💡 다음 배당금을 받으려면 <b>{fmt_dt(until_next)}</b> (한국시간)까지 보유해야 합니다.</p>
              <p style="margin:0; color:black;">💵 다음 배당지급일: <b>{fmt(next_pay)}</b></p>
              <p style="margin-top:6px; font-size:11px; color:#777;">
                ※ 실제 입금 시점은 증권사·브로커마다 다를 수 있습니다.
              </p>
            </div>
            """,
            height=200
        )

        # -----------------------------
        # 최근 배당내역 + 차트
        # -----------------------------
        df_div_all = fetch_dividends_df(ticker)
        if not df_div_all.empty:
            df5 = df_div_all.head(5).copy()
            df5["배당금(원화)"] = (df5["배당금(달러)"] * LATEST_FX).round(2)
            df5["배당락일(월일)"] = df5["배당락일"].dt.strftime("%Y-%m-%d")
            df5.index = range(1, len(df5) + 1)

            st.subheader("📑 최근 5개 배당 내역 (달러→원화 환산)")
            st.dataframe(df5[["배당락일(월일)", "배당금(달러)", "배당금(원화)"]], use_container_width=True)
            st.caption(f"💱 실시간 환율 (USD→KRW): {LATEST_FX:.2f}원 기준 환산")

            df10 = df_div_all.head(10).copy()
            df10["배당금(원화)"] = (df10["배당금(달러)"] * LATEST_FX).round(2)
            df10["배당락일(라벨)"] = df10["배당락일"].dt.strftime("%m/%d")
            fig_div = px.bar(
                df10.sort_values("배당락일"),
                x="배당락일(라벨)", y="배당금(원화)", color="배당금(원화)",
                color_continuous_scale=px.colors.sequential.Tealgrn,
                title="최근 10개 배당금 (원화 기준)")
            fig_div.update_xaxes(tickangle=-45)
            fig_div.update_yaxes(showgrid=False)
            fig_div.update_layout(showlegend=False, plot_bgcolor='white', bargap=0.3,
                                  xaxis_title="배당락일 (월/일, 한국시간)", yaxis_title="배당금(원화)")
            st.plotly_chart(fig_div, use_container_width=True)
        else:
            st.warning("배당 데이터가 없습니다.")

elif raw_input.strip():
    st.warning("영문 티커만 입력해 주세요. 예: TSLY, NVDY, YMAG")
