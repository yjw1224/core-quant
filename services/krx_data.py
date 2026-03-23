import os

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()


try:
    from pykrx import stock
    from pykrx.website.comm import webio as pykrx_webio

    PYKRX_AVAILABLE = True
except ImportError:
    stock = None
    pykrx_webio = None
    PYKRX_AVAILABLE = False


_LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
_LOGIN_JSP = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
_LOGIN_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class _SessionRequestsProxy:
    def __init__(self, session: requests.Session):
        self._session = session

    def get(self, url, **kwargs):
        return self._session.get(url, **kwargs)

    def post(self, url, **kwargs):
        return self._session.post(url, **kwargs)


def _get_krx_credentials():
    load_dotenv(override=True)

    login_id = os.getenv("KRX_LOGIN_ID")
    login_pw = os.getenv("KRX_LOGIN_PW")

    if login_id and login_pw:
        return login_id, login_pw

    try:
        secrets = st.secrets.get("krx", {})
        sid = secrets.get("login_id")
        spw = secrets.get("login_pw")
        if sid and spw:
            return sid, spw
    except Exception:
        pass

    return None, None


def _login_krx_and_patch_pykrx(session: requests.Session, login_id: str, login_pw: str):
    if pykrx_webio is None:
        return False, "pykrx webio 모듈을 찾지 못했습니다."

    session.get(_LOGIN_PAGE, headers={"User-Agent": _UA}, timeout=15)
    session.get(
        _LOGIN_JSP,
        headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE},
        timeout=15,
    )

    payload = {
        "mbrNm": "",
        "telNo": "",
        "di": "",
        "certType": "",
        "mbrId": login_id,
        "pw": login_pw,
    }
    headers = {"User-Agent": _UA, "Referer": _LOGIN_PAGE}

    resp = session.post(_LOGIN_URL, data=payload, headers=headers, timeout=15)
    data = resp.json()
    error_code = data.get("_error_code", "")

    if error_code == "CD011":
        payload["skipDup"] = "Y"
        resp = session.post(_LOGIN_URL, data=payload, headers=headers, timeout=15)
        data = resp.json()
        error_code = data.get("_error_code", "")

    if error_code != "CD001":
        return False, f"KRX 로그인 실패({_LOGIN_URL}): {error_code or 'unknown'}"

    # pykrx의 requests.get/post를 로그인 세션으로 우회해 쿠키를 공유한다.
    pykrx_webio.requests = _SessionRequestsProxy(session)
    return True, None


@st.cache_data(ttl=60 * 60 * 6, show_spinner="PyKRX 전종목 목록 로딩 중...")
def load_stock_universe():
    if not PYKRX_AVAILABLE:
        return [], "pykrx 패키지가 설치되어 있지 않습니다.", None

    if stock is None:
        return [], "pykrx 모듈 초기화에 실패했습니다.", None

    try:
        login_status = "KRX 로그인: 미설정 (비로그인 모드)"
        login_id, login_pw = _get_krx_credentials()
        if login_id and login_pw:
            session = requests.Session()
            ok, login_error = _login_krx_and_patch_pykrx(session, login_id, login_pw)
            if not ok:
                return [], login_error, "KRX 로그인: 실패"
            login_status = "KRX 로그인: 성공"

        target = "20260323"
        tickers = stock.get_market_ticker_list(target, market="ALL")

        if not tickers:
            return [], f"{target} 기준 전종목 목록을 찾지 못했습니다.", login_status

        universe = []
        for ticker in tickers:
            name = stock.get_market_ticker_name(ticker)
            if name:
                universe.append({"code": ticker, "name": name})

        return universe, None, login_status
    except Exception as error:
        return [], f"PyKRX 데이터 로딩 실패: {error}", None


def find_stocks(universe, query: str):
    normalized = query.strip().lower()
    if not normalized:
        return universe

    return [
        item
        for item in universe
        if normalized in item["name"].lower() or normalized in item["code"]
    ]
