import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from fredapi import Fred

START_DATE = "2005-01-01"
CHART_LINE_COLOR = "#2980B9"
GLOBAL_M2_LINE_COLOR = "#16A085"

# FRED 전용: 상위 10개국(요청 반영)
# fx_mode:
# - LCY_PER_USD: 현지통화/USD -> USD 환산 시 나눗셈
# - USD_PER_LCY: USD/현지통화 -> USD 환산 시 곱셈
COUNTRY_CONFIG = {
    "United States": {
        "m2": "WM2NS",
        "fx": None,
        "fx_mode": None,
    },
    "Euro Area": {
        "m2": "MYAGM2EZM196N",
        "fx": "DEXUSEU",
        "fx_mode": "USD_PER_LCY",
    },
    "Japan": {
        "m2": "MYAGM2JPM189S",
        "fx": "DEXJPUS",
        "fx_mode": "LCY_PER_USD",
    },
    "China": {
        "m2": "MYAGM2CNM189N",
        "fx": "DEXCHUS",
        "fx_mode": "LCY_PER_USD",
    },
    # "United Kingdom": {
    #     "m2": "MYAGM2GBM189N",
    #     "fx": "DEXUSUK",
    #     "fx_mode": "USD_PER_LCY",
    # },
    # "Turkey": {
    #     "m2": "MYAGM2TRM189N",
    #     "fx": "DEXTUUS",
    #     "fx_mode": "LCY_PER_USD",
    # },
    # "Korea": {
    #     "m2": "MYAGM2KRM189S",
    #     "fx": "DEXKOUS",
    #     "fx_mode": "LCY_PER_USD",
    # },
    # "Mexico": {
    #     "m2": "MYAGM2MXM189N",
    #     "fx": "DEXMXUS",
    #     "fx_mode": "LCY_PER_USD",
    # },
    # "Germany": {
    #     "m2": "MYAGM2DEM189S",
    #     "fx": "DEXUSEU",
    #     "fx_mode": "USD_PER_LCY",
    # },
    # "India": {
    #     "m2": "MYAGM2INM189N",
    #     "fx": "DEXINUS",
    #     "fx_mode": "LCY_PER_USD",
    # },
}


def _get_fred_client() -> Fred:
    load_dotenv(override=True)
    fred_api_key = os.getenv("FRED_API_KEY")
    if not fred_api_key:
        raise ValueError("FRED_API_KEY 환경 변수가 설정되어 있지 않습니다.")
    return Fred(api_key=fred_api_key)


def _fetch_series(fred: Fred, ticker: str) -> pd.Series:
    s = fred.get_series(ticker, observation_start=START_DATE).dropna()
    if s.empty:
        raise ValueError(f"series unavailable: {ticker}")
    return s


def _to_monthly_last(s: pd.Series) -> pd.Series:
    return s.dropna().sort_index().resample("ME").last()


@st.cache_data(ttl=3600)
def get_dfii10_data() -> pd.Series:
    fred = _get_fred_client()
    return fred.get_series("DFII10", observation_start=START_DATE).dropna()


@st.cache_data(ttl=3600)
def get_global_m2_top10_data():
    """
    계산식:
    1) 국가별 USD 환산
       - LCY_PER_USD: M2_USD_i(t) = M2_local_i(t) / FX_i(t)
       - USD_PER_LCY: M2_USD_i(t) = M2_local_i(t) * FX_i(t)
    2) 가중치(최신값 기준 자동 계산)
       w_i = M2_USD_i(t*) / Σ_j M2_USD_j(t*)
    3) Global M2 (가중평균)
       Global_M2(t) = Σ_i w_i * M2_USD_i(t)
    """
    fred = _get_fred_client()
    country_series = []
    failures = []

    for country, cfg in COUNTRY_CONFIG.items():
        try:
            m2 = _to_monthly_last(_fetch_series(fred, cfg["m2"]))

            if country == "United States":
                m2_usd = m2 * 1000000000  # 단위 조정 (billion -> USD)
            else:
                fx = _fetch_series(fred, cfg["fx"]).dropna().resample("ME").mean()
                merged = pd.concat([m2.rename("m2"), fx.rename("fx")], axis=1).dropna()
                if cfg["fx_mode"] == "LCY_PER_USD":
                    m2_usd = merged["m2"] / merged["fx"]
                else:
                    m2_usd = merged["m2"] * merged["fx"]

            country_series.append(m2_usd.rename(country))
        except Exception as e:
            failures.append(f"{country}: {e}")

    df = pd.concat(country_series, axis=1).sort_index().ffill(limit=2)

    latest = df.iloc[-1].dropna()
    weights = (latest / latest.sum()).rename("weight")

    aligned = df[weights.index].dropna(how="all")
    global_m2 = aligned.mul(weights, axis=1).sum(axis=1).rename("Global_M2_Top10_Weighted")

    weights_pct = (weights * 100).sort_values(ascending=False).rename("weight_pct")
    return global_m2, weights_pct, failures


def get_dfii10_data_from_session() -> pd.Series:
    key = pd.Timestamp.now().strftime("%Y-%m-%d-%H")
    if (
        "macro_dfii10_cache" not in st.session_state
        or st.session_state.get("macro_dfii10_cache_key") != key
    ):
        st.session_state.macro_dfii10_cache = get_dfii10_data()
        st.session_state.macro_dfii10_cache_key = key
    return st.session_state.macro_dfii10_cache


def get_global_m2_data_from_session():
    key = pd.Timestamp.now().strftime("%Y-%m-%d-%H")
    if (
        "macro_global_m2_cache" not in st.session_state
        or st.session_state.get("macro_global_m2_cache_key") != key
    ):
        st.session_state.macro_global_m2_cache = get_global_m2_top10_data()
        st.session_state.macro_global_m2_cache_key = key
    return st.session_state.macro_global_m2_cache


def render_dfii10_with_global_m2_chart(dfii10_data: pd.Series, global_m2: pd.Series):
    merged = pd.concat(
        [_to_monthly_last(dfii10_data).rename("DFII10"), global_m2],
        axis=1,
    ).dropna()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=merged.index,
            y=merged["DFII10"],
            mode="lines",
            name="DFII10",
            line=dict(color=CHART_LINE_COLOR, width=1.2),
            yaxis="y1",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=merged.index,
            y=merged["Global_M2_Top10_Weighted"],
            mode="lines",
            name="Global M2 (Top10 Weighted)",
            line=dict(color=GLOBAL_M2_LINE_COLOR, width=1.5),
            yaxis="y2",
        )
    )

    fig.update_layout(
        xaxis=dict(title="날짜", type="date"),
        yaxis=dict(title="DFII10 (%)", showgrid=False),
        yaxis2=dict(title="Global M2 (USD)", overlaying="y", side="right", showgrid=False),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02, x=0),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_macro_page():
    st.subheader("DFII10 + Global M2(Top10, FRED only)")
    st.markdown(
        """
- 계산식: `Global_M2(t) = Σ_i w_i * M2_USD_i(t)`
- 가중치: 최신 시점 `M2_USD` 비중으로 자동 계산
- 환산: `LCY_PER_USD -> 나눗셈`, `USD_PER_LCY -> 곱셈`
"""
    )

    try:
        dfii10_data = get_dfii10_data_from_session()
        global_m2, weights_pct, failures = get_global_m2_data_from_session()
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return

    col1, col2 = st.columns(2)
    col1.metric("DFII10 최신값", f"{dfii10_data.iloc[-1]:.2f}%")
    col2.metric("Global M2 최신값", f"{global_m2.iloc[-1]:,.2f}")

    render_dfii10_with_global_m2_chart(dfii10_data, global_m2)

    st.markdown("### Top10 가중치(최신 시점)")
    st.dataframe(weights_pct.to_frame().style.format("{:.2f}%"), use_container_width=True)

    if failures:
        st.caption("일부 티커는 제외됨: " + " | ".join(failures))
