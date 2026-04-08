import streamlit as st

import pandas as pd
import requests
import time


def _get_session_cached_value(key: str, ttl_seconds: int):
    """세션 상태에서 TTL이 유효한 캐시 값을 반환한다."""
    cached = st.session_state.get(key)
    if not cached:
        return None

    cached_at = cached.get("cached_at", 0)
    if time.time() - cached_at > ttl_seconds:
        return None

    return cached.get("value")


def _set_session_cached_value(key: str, value):
    """세션 상태에 캐시 값을 저장한다."""
    st.session_state[key] = {
        "value": value,
        "cached_at": time.time(),
    }


def get_market_caps():
    """CoinGecko에서 BTC, USDT, USDC 시가총액(USD)을 조회한다."""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": "bitcoin,tether,usd-coin",
        "order": "market_cap_desc",
        "per_page": 3,
        "page": 1,
        "sparkline": False,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()

    market_caps = {coin["id"]: coin.get("market_cap", 0) for coin in payload}
    return {
        "btc": market_caps.get("bitcoin", 0),
        "usdt": market_caps.get("tether", 0),
        "usdc": market_caps.get("usd-coin", 0),
    }


def get_ssr():
    market_caps = get_market_caps()
    btc_mc = market_caps["btc"]
    usdt_mc = market_caps["usdt"]
    usdc_mc = market_caps["usdc"]

    # SSR 공식: BTC 시총 / (USDT 시총 + USDC 시총)
    ssr = btc_mc / (usdt_mc + usdc_mc)

    return ssr


@st.cache_data(ttl=3600)
def _get_market_cap_history(coin_id: str, days: int = 365) -> pd.DataFrame:
    """CoinGecko market_chart에서 코인별 시가총액 일별 데이터를 조회한다."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": days,
        "interval": "daily",
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()

    market_caps = payload.get("market_caps", [])
    history_df = pd.DataFrame(market_caps, columns=["timestamp", "market_cap"])
    if history_df.empty:
        return pd.DataFrame(columns=["date", "market_cap"])

    history_df["date"] = pd.to_datetime(history_df["timestamp"], unit="ms").dt.date
    return history_df[["date", "market_cap"]]


def get_ssr_history(days: int = 365) -> pd.DataFrame:
    """SSR(BTC 시총 / (USDT+USDC 시총))의 일별 시계열을 계산한다."""
    btc_df = _get_market_cap_history("bitcoin", days=days).rename(
        columns={"market_cap": "btc_market_cap"}
    )
    usdt_df = _get_market_cap_history("tether", days=days).rename(
        columns={"market_cap": "usdt_market_cap"}
    )
    usdc_df = _get_market_cap_history("usd-coin", days=days).rename(
        columns={"market_cap": "usdc_market_cap"}
    )

    merged = btc_df.merge(usdt_df, on="date", how="inner").merge(
        usdc_df, on="date", how="inner"
    )
    merged["stable_total_market_cap"] = (
        merged["usdt_market_cap"] + merged["usdc_market_cap"]
    )
    merged = merged[merged["stable_total_market_cap"] > 0].copy()
    merged["ssr"] = merged["btc_market_cap"] / merged["stable_total_market_cap"]

    return merged.sort_values("date")

def render_crypto_page():
    st.subheader("SSR(Stablecoin Supply Ratio)")

    try:
        current_ssr = _get_session_cached_value("crypto_current_ssr", ttl_seconds=300)
        if current_ssr is None:
            current_ssr = get_ssr()
            _set_session_cached_value("crypto_current_ssr", current_ssr)
        st.metric(label="현재 SSR", value=f"{current_ssr:.2f}")
    except requests.RequestException as exc:
        st.error(f"현재 SSR 데이터를 불러오지 못했습니다: {exc}")
        return

    st.caption("지난 1년(365일) SSR 추이")

    try:
        ssr_history_df = _get_session_cached_value(
            "crypto_ssr_history_365", ttl_seconds=3600
        )
        if ssr_history_df is None:
            ssr_history_df = get_ssr_history(days=365)
            _set_session_cached_value("crypto_ssr_history_365", ssr_history_df)
    except requests.RequestException as exc:
        st.error(f"SSR 히스토리 데이터를 불러오지 못했습니다: {exc}")
        return

    if ssr_history_df.empty:
        st.warning("표시할 SSR 히스토리 데이터가 없습니다.")
        return

    st.line_chart(ssr_history_df.set_index("date")["ssr"])