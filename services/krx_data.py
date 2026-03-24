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
    # 변경할 코드: 실제 웹 브라우저의 Ajax 요청과 똑같이 헤더를 보강합니다.
    headers = {
        "User-Agent": _UA,
        "Referer": _LOGIN_PAGE,
        "Origin": "https://data.krx.co.kr",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }

    resp = session.post(_LOGIN_URL, data=payload, headers=headers, timeout=15)

    # --- 여기서 터미널에 응답값을 출력해봅니다 ---
    print("STATUS CODE:", resp.status_code)
    print("RESPONSE TEXT:", resp.text[:2000])  # 최대 2000자까지만 출력
    # ---------------------------------------------

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

def login_krx(login_id: str = None, login_pw: str = None) -> bool:
    """
    KRX 정보데이터시스템에 로그인하고 pykrx 모듈이 로그인 세션을 사용하도록 패치합니다.
    """
    if not login_id or not login_pw:
        env_id, env_pw = _get_krx_credentials()
        login_id = login_id or env_id
        login_pw = login_pw or env_pw

    if not login_id or not login_pw:
        print("KRX 로그인 아이디 또는 비밀번호가 제공되지 않았습니다.")
        return False

    session = requests.Session()
    success, msg = _login_krx_and_patch_pykrx(session, login_id, login_pw)
    if not success:
        print(msg)
    return success

@st.cache_data(show_spinner="CSV 파일에서 전종목 목록 로딩 중...")
def load_stock_universe():
    """
    all_korea_stock_data.csv 파일에서 유니버스(종목코드/종목명)를 읽어옵니다.
    """
    universe = []
    file_path = "all_korea_stock_data.csv"
    
    if not os.path.exists(file_path):
        return [], f"'{file_path}' 파일을 찾을 수 없습니다. 프로젝트 최상위 폴더에 파일을 추가해주세요.", "데이터 소스: 파일 없음"
        
    try:
        import pandas as pd
        # 문자열로 읽어서 005930 등의 종목코드 앞자리 0이 증발하는 것을 방지합니다.
        # 인코딩이 cp949(EUC-KR)일 수 있으므로 인코딩 옵션을 지정합니다.
        try:
            df = pd.read_csv(file_path, dtype=str, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, dtype=str, encoding='cp949')
        
        # CSV 컬럼명 유연하게 처리 (코드/종목코드/code, 이름/종목명/name 등 자동 매칭)
        code_col = 'code' if 'code' in df.columns else ('종목코드' if '종목코드' in df.columns else df.columns[1])
        name_col = 'name' if 'name' in df.columns else ('종목명' if '종목명' in df.columns else df.columns[2])
        
        for _, row in df.iterrows():
            code = str(row[code_col]).strip()
            name = str(row[name_col]).strip()
            
            # 유효한 값인 경우에만 추가
            if pd.notna(row[code_col]) and code and code.lower() != 'nan':
                # 종목코드가 숫자로만 이루어져 있고 6자리가 안 되면 앞부분을 0으로 채움
                if code.isdigit() and len(code) < 6:
                    code = code.zfill(6)
                universe.append({"name": name, "code": code})
                
        return universe, None, "데이터 소스: 로컬 CSV"
        
    except Exception as error:
        return [], f"CSV 데이터 로딩 실패: {error}", "데이터 소스: 파일 오류"


def find_stocks(universe, query: str):
    normalized = query.strip().lower()
    if not normalized:
        return universe

    return [
        item
        for item in universe
        if normalized in item["name"].lower() or normalized in item["code"]
    ]
